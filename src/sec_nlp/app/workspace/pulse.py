# src/sec_nlp/app/workspace/pulse.py
"""Serve daily activity, acknowledgements, watchlists, and research reviews.

All operations use cached evidence and return frozen records. Terminal workers
and scriptable commands share these services; opening evidence or changing a
profile never acknowledges an item or starts a provider request implicitly.
"""

import base64
import binascii
import sqlite3
from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import uuid4

from sec_nlp.app.pulse.models import (
    JournalEntry,
    MarketObservation,
    WatchItem,
    normalize_symbol,
)
from sec_nlp.app.workspace.pulse_models import (
    DueReview,
    PulseFilters,
    PulseItem,
    PulseOverview,
    PulsePage,
    PulseSource,
    PulseState,
    ReviewAction,
    ScanMatch,
    SymbolMapping,
)
from sec_nlp.app.workspace.pulse_schema import text_field
from sec_nlp.app.workspace.store import SqlValue, WorkspaceStore

_SYMBOL_MATCH = "SELECT 1 FROM entities e JOIN pulse_symbols s ON s.cik=e.cik JOIN pulse_watchlist w ON w.symbol=s.symbol WHERE e.accession=a.reference"
_SCAN_MATCH = "SELECT 1 FROM pulse_scan_matches m JOIN scans s ON s.key=m.scan_id WHERE m.accession=a.reference"


def _cursor(value: str) -> tuple[str, str]:
    """Decode and validate a stable discovery cursor."""
    try:
        stamp, identity = (
            base64.urlsafe_b64decode(value.encode()).decode().split("\n", 1)
        )
        timestamp = datetime.fromisoformat(stamp)
        if timestamp.tzinfo is None or not identity.startswith(
            ("filing:", "news:")
        ):
            raise ValueError("Invalid cursor fields")
        return stamp, identity
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Invalid Pulse page cursor") from exc


def _item(connection: sqlite3.Connection, row: sqlite3.Row) -> PulseItem:
    """Join current relevance and explicit acknowledgement to one evidence row."""
    item = PulseItem.model_validate_json(text_field(row, "payload"))
    matches = [
        (
            text_field(match, "kind"),
            text_field(match, "value"),
            text_field(match, "reason"),
        )
        for match in connection.execute(
            "SELECT kind,value,reason FROM pulse_matches WHERE identity=? ORDER BY kind,value,reason",
            (item.identity,),
        )
    ]
    if item.accession_number:
        for mapping_row in connection.execute(
            "SELECT s.symbol,s.payload,e.role FROM entities e JOIN pulse_symbols s ON s.cik=e.cik JOIN pulse_watchlist w ON w.symbol=s.symbol WHERE e.accession=? ORDER BY s.symbol,e.role",
            (item.accession_number,),
        ):
            mapping = SymbolMapping.model_validate_json(
                text_field(mapping_row, "payload")
            )
            reason = f"{mapping.symbol}: SEC entity {mapping.cik} ({text_field(mapping_row, 'role')})"
            if mapping.stale:
                reason += f"; stale registry mapping: {mapping.detail}"
            matches.append(("symbol", mapping.symbol, reason))
        for scan in connection.execute(
            "SELECT json_extract(s.payload,'$.name') AS name FROM pulse_scan_matches m JOIN scans s ON s.key=m.scan_id WHERE m.accession=? ORDER BY s.key",
            (item.accession_number,),
        ):
            name = text_field(scan, "name")
            matches.append(("topic", name, f"Saved scan: {name}"))
    return item.model_copy(
        update={
            "reviewed": bool(row["reviewed"]),
            "discovered_at": datetime.fromisoformat(
                text_field(row, "discovered_at")
            ),
            "symbols": tuple(
                dict.fromkeys(
                    value for kind, value, _ in matches if kind == "symbol"
                )
            ),
            "topics": tuple(
                dict.fromkeys(
                    value for kind, value, _ in matches if kind == "topic"
                )
            ),
            "reasons": tuple(dict.fromkeys(reason for _, _, reason in matches)),
        }
    )


def pulse_item(store: WorkspaceStore, identity: str) -> PulseItem:
    """Return cached evidence with current relevance and review state.

    Args:
        store: Open local workspace.
        identity: Stable evidence identity, including a retired deduplication alias.

    Returns:
        The canonical evidence item without fetching or acknowledging it.

    Raises:
        ValueError: If the identity is not in this workspace.
    """
    with store._connect() as connection:
        redirect = connection.execute(
            "SELECT canonical FROM pulse_identity_redirect WHERE identity=?",
            (identity,),
        ).fetchone()
        if redirect is not None:
            identity = text_field(redirect, "canonical")
        row = connection.execute(
            "SELECT * FROM pulse_activity WHERE identity=?", (identity,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Activity is not in this workspace: {identity}")
        return _item(connection, row)


def pulse_page(
    store: WorkspaceStore,
    filters: PulseFilters | None = None,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> PulsePage:
    """Return a keyset page of locally cached activity.

    Args:
        store: Open local workspace.
        filters: Current relevance and acknowledgement filters.
        cursor: Continuation returned by the preceding page.
        limit: Visible row count, between one and fifty.

    Returns:
        At most ``limit`` immutable items and an optional continuation.

    Raises:
        ValueError: If the cursor or requested page size is invalid.
    """
    if not 1 <= limit <= 50:
        raise ValueError("Pulse page size must be between 1 and 50")
    selected = filters or PulseFilters()
    clauses: list[str] = []
    parameters: list[SqlValue] = []
    if selected.new_only:
        clauses.append("a.reviewed=0")
    if selected.scope == "focused":
        clauses.append(
            "(EXISTS(SELECT 1 FROM pulse_matches p WHERE p.identity=a.identity) OR (a.kind='filing' AND (EXISTS("
            + _SYMBOL_MATCH
            + ") OR EXISTS("
            + _SCAN_MATCH
            + "))))"
        )
    if selected.symbol:
        clauses.append(
            "a.identity IN (SELECT identity FROM pulse_matches WHERE kind='symbol' AND value=? UNION SELECT 'filing:'||e.accession FROM pulse_symbols s JOIN pulse_watchlist w ON w.symbol=s.symbol JOIN entities e ON e.cik=s.cik WHERE s.symbol=?)"
        )
        parameters.extend(
            (
                normalize_symbol(selected.symbol),
                normalize_symbol(selected.symbol),
            )
        )
    if selected.topic:
        clauses.append(
            "a.identity IN (SELECT identity FROM pulse_matches WHERE kind='topic' AND value=? UNION SELECT 'filing:'||m.accession FROM pulse_scan_matches m JOIN scans s ON s.key=m.scan_id WHERE json_extract(s.payload,'$.name')=?)"
        )
        parameters.extend((selected.topic, selected.topic))
    if selected.source:
        clauses.append(
            "(a.source=? OR instr(' | '||a.source||' | ',' | '||?||' | ')>0)"
        )
        parameters.extend((selected.source, selected.source))
    if selected.form:
        clauses.append("a.form_type=?")
        parameters.append(selected.form)
    if cursor:
        stamp, identity = _cursor(cursor)
        clauses.append("(a.discovered_at,a.identity)<(?,?)")
        parameters.extend((stamp, identity))
    condition = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.append(limit + 1)
    with store._connect() as connection:
        if selected.scope == "focused":
            relevant = connection.execute(
                "SELECT EXISTS(SELECT 1 FROM pulse_matches) OR EXISTS(SELECT 1 FROM pulse_symbols s JOIN pulse_watchlist w ON w.symbol=s.symbol JOIN entities e ON e.cik=s.cik) OR EXISTS(SELECT 1 FROM pulse_scan_matches m JOIN scans s ON s.key=m.scan_id)"
            ).fetchone()
            if relevant is not None and not relevant[0]:
                return PulsePage()
        rows = connection.execute(
            "SELECT a.* FROM pulse_activity a"
            + condition
            + " ORDER BY a.discovered_at DESC,a.identity DESC LIMIT ?",
            tuple(parameters),
        ).fetchall()
        items = tuple(_item(connection, row) for row in rows[:limit])
    continuation = None
    if len(rows) > limit and items:
        continuation = base64.urlsafe_b64encode(
            (
                text_field(rows[limit - 1], "discovered_at")
                + "\n"
                + items[-1].identity
            ).encode()
        ).decode()
    return PulsePage(items=items, next_cursor=continuation)


def acknowledge(store: WorkspaceStore, identities: Sequence[str]) -> str:
    """Mark exactly the selected evidence reviewed and return an undo token.

    Args:
        store: Open local workspace.
        identities: Stable identities from a visible page or selection.

    Returns:
        A durable token accepted by ``undo_acknowledgement``.

    Raises:
        ValueError: If any selected identity is absent; no state is changed.
    """
    token = uuid4().hex
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO pulse_ack_operations(token) VALUES (?)", (token,)
        )
        for identity in dict.fromkeys(identities):
            redirect = connection.execute(
                "SELECT canonical FROM pulse_identity_redirect WHERE identity=?",
                (identity,),
            ).fetchone()
            if redirect:
                identity = text_field(redirect, "canonical")
            row = connection.execute(
                "SELECT reviewed,review_token FROM pulse_activity WHERE identity=?",
                (identity,),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"Activity is not in this workspace: {identity}"
                )
            connection.execute(
                "INSERT OR IGNORE INTO pulse_acknowledgements VALUES (?,?,?,?)",
                (
                    token,
                    identity,
                    int(row["reviewed"]),
                    text_field(row, "review_token"),
                ),
            )
            connection.execute(
                "UPDATE pulse_activity SET reviewed=1,review_token=? WHERE identity=?",
                (token, identity),
            )
    return token


def undo_acknowledgement(store: WorkspaceStore, token: str) -> int:
    """Undo one acknowledgement without replacing later independent decisions.

    Args:
        store: Open local workspace.
        token: Token returned by ``acknowledge``.

    Returns:
        Number of items restored. Repeating a completed undo returns zero.

    Raises:
        ValueError: If the token was not issued by this workspace.
    """
    restored = 0
    with store._connect() as connection:
        operation = connection.execute(
            "SELECT undone FROM pulse_ack_operations WHERE token=?", (token,)
        ).fetchone()
        if operation is None:
            raise ValueError("Unknown Pulse acknowledgement token")
        if operation["undone"]:
            return 0
        for row in connection.execute(
            "SELECT * FROM pulse_acknowledgements WHERE token=?", (token,)
        ).fetchall():
            result = connection.execute(
                "UPDATE pulse_activity SET reviewed=?,review_token=? WHERE identity=? AND review_token=?",
                (
                    int(row["previous"]),
                    text_field(row, "previous_token"),
                    text_field(row, "identity"),
                    token,
                ),
            )
            restored += result.rowcount
        connection.execute(
            "UPDATE pulse_ack_operations SET undone=1 WHERE token=?", (token,)
        )
    return restored


def save_watch_item(store: WorkspaceStore, item: WatchItem) -> None:
    """Save all editable watchlist fields and recompute cached relevance.

    Args:
        store: Open local workspace.
        item: Complete validated replacement or new watchlist entry.
    """
    settings = store.load_settings()
    found = any(
        previous.symbol == item.symbol for previous in settings.watchlist
    )
    items = tuple(
        item if previous.symbol == item.symbol else previous
        for previous in settings.watchlist
    )
    store.save_settings(
        settings.model_copy(
            update={"watchlist": items if found else (*items, item)}
        )
    )


def remove_watch_item(store: WorkspaceStore, symbol: str) -> None:
    """Remove a current target while preserving evidence, notes, and review history.

    Args:
        store: Open local workspace.
        symbol: Watched market symbol, normalized before matching.

    Raises:
        ValueError: If the symbol is invalid or absent from the watchlist.
    """
    normalized = normalize_symbol(symbol)
    settings = store.load_settings()
    if not any(item.symbol == normalized for item in settings.watchlist):
        raise ValueError("Symbol is not in the watchlist")
    store.save_settings(
        settings.model_copy(
            update={
                "watchlist": tuple(
                    item
                    for item in settings.watchlist
                    if item.symbol != normalized
                )
            }
        )
    )


def record_review(store: WorkspaceStore, action: ReviewAction) -> None:
    """Append a review decision without rewriting its original thesis or journal.

    Args:
        store: Open local workspace.
        action: Validated completion or deferral decision.

    Raises:
        ValueError: If the target is unknown or its review identity conflicts.
    """
    if action.target_kind == "watchlist":
        action = action.model_copy(
            update={"target_id": normalize_symbol(action.target_id)}
        )
    with store._connect() as connection:
        if action.target_kind == "watchlist":
            found = connection.execute(
                "SELECT 1 FROM pulse_watchlist WHERE symbol=?",
                (action.target_id,),
            ).fetchone()
        else:
            found = connection.execute(
                "SELECT 1 FROM notes WHERE key=?", (action.target_id,)
            ).fetchone()
        if found is None:
            raise ValueError("Review target is not in this workspace")
        existing = connection.execute(
            "SELECT payload FROM pulse_reviews WHERE key=?", (action.review_id,)
        ).fetchone()
        if existing is not None:
            if text_field(existing, "payload") != action.model_dump_json():
                raise ValueError("Conflicting immutable review identity")
            return
        connection.execute(
            "INSERT INTO pulse_reviews VALUES (?,?,?,?,?)",
            (
                action.review_id,
                action.target_kind,
                action.target_id,
                action.created_at.astimezone(UTC).isoformat(),
                action.model_dump_json(),
            ),
        )


def review_due(
    store: WorkspaceStore, *, on: date | None = None
) -> tuple[DueReview, ...]:
    """Return due watchlist and journal schedules after applying review history.

    Args:
        store: Open local workspace.
        on: Inclusive review date; defaults to the current UTC date.

    Returns:
        Due targets ordered by effective review date, category, and identity.
        Explicitly edited watchlist dates override earlier review actions.
    """
    today = on or datetime.now(UTC).date()
    candidates: list[DueReview] = []
    with store._connect() as connection:
        targets: list[
            tuple[str, str, str | None, str, date | None, str, str]
        ] = [
            (
                "watchlist",
                item.symbol,
                item.symbol,
                item.name or item.symbol,
                item.review_on,
                item.thesis,
                item.invalidation,
            )
            for item in store.load_settings().watchlist
        ]
        targets.extend(
            (
                "journal",
                entry.entry_id,
                entry.symbol,
                entry.observation,
                entry.review_on,
                entry.thesis,
                entry.invalidation,
            )
            for entry in (
                JournalEntry.model_validate_json(text_field(row, "payload"))
                for row in connection.execute("SELECT payload FROM notes")
            )
        )
        for (
            kind,
            target,
            symbol,
            title,
            review_on,
            thesis,
            invalidation,
        ) in targets:
            latest = connection.execute(
                "SELECT payload,timestamp FROM pulse_reviews WHERE kind=? AND target=? ORDER BY timestamp DESC,key DESC LIMIT 1",
                (kind, target),
            ).fetchone()
            schedule = (
                connection.execute(
                    "SELECT changed_at FROM pulse_watch_schedule WHERE symbol=?",
                    (target,),
                ).fetchone()
                if kind == "watchlist"
                else None
            )
            if latest is not None and (
                schedule is None
                or text_field(latest, "timestamp")
                >= text_field(schedule, "changed_at")
            ):
                review_on = ReviewAction.model_validate_json(
                    text_field(latest, "payload")
                ).next_review_on
            if review_on is not None and review_on <= today:
                candidates.append(
                    DueReview(
                        target_kind="watchlist"
                        if kind == "watchlist"
                        else "journal",
                        target_id=target,
                        symbol=symbol,
                        title=title,
                        review_on=review_on,
                        thesis=thesis,
                        invalidation=invalidation,
                    )
                )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (item.review_on, item.target_kind, item.target_id),
        )
    )


def pulse_overview(store: WorkspaceStore) -> PulseOverview:
    """Return current-profile quotes, independent outcomes, and due research.

    Returns:
        Latest successful watched and benchmark quotes with recomputed freshness,
        separately dated provider attempts, registry provenance, and due reviews.
    """
    settings = store.load_settings()
    watched = {item.symbol for item in settings.watchlist}
    symbols = watched | set(settings.benchmarks)
    today = datetime.now(UTC).date()
    with store._connect() as connection:
        market = tuple(
            observation.model_copy(
                update={
                    "stale": observation.quote_date is None
                    or (today - observation.quote_date).days
                    > settings.stale_after_days
                }
            )
            for observation in (
                MarketObservation.model_validate_json(
                    text_field(row, "payload")
                )
                for row in connection.execute(
                    "SELECT payload FROM pulse_market ORDER BY symbol"
                )
            )
            if observation.symbol in symbols
        )
        sources = tuple(
            PulseSource.model_validate_json(text_field(row, "payload"))
            for row in connection.execute(
                "SELECT payload FROM pulse_sources ORDER BY kind,name"
            )
        )
        mappings = tuple(
            mapping
            for mapping in (
                SymbolMapping.model_validate_json(text_field(row, "payload"))
                for row in connection.execute(
                    "SELECT payload FROM pulse_symbols ORDER BY symbol"
                )
            )
            if mapping.symbol in watched
        )
    return PulseOverview(
        market=market,
        sources=sources,
        mappings=mappings,
        due_reviews=review_due(store),
    )


def export_pulse_state(store: WorkspaceStore) -> PulseState:
    """Return durable Pulse identities, acknowledgements, provenance, and reviews.

    Returns:
        An unbounded portable snapshot for explicit workspace export, including
        removed-symbol history and stable activity identities.
    """
    with store._connect() as connection:
        return PulseState(
            activity=tuple(
                _item(connection, row)
                for row in connection.execute(
                    "SELECT * FROM pulse_activity ORDER BY discovered_at,identity"
                ).fetchall()
            ),
            reviews=tuple(
                ReviewAction.model_validate_json(text_field(row, "payload"))
                for row in connection.execute(
                    "SELECT payload FROM pulse_reviews ORDER BY timestamp,key"
                )
            ),
            mappings=tuple(
                SymbolMapping.model_validate_json(text_field(row, "payload"))
                for row in connection.execute(
                    "SELECT payload FROM pulse_symbols ORDER BY symbol"
                )
            ),
            market=tuple(
                MarketObservation.model_validate_json(
                    text_field(row, "payload")
                )
                for row in connection.execute(
                    "SELECT payload FROM pulse_market ORDER BY symbol"
                )
            ),
            sources=tuple(
                PulseSource.model_validate_json(text_field(row, "payload"))
                for row in connection.execute(
                    "SELECT payload FROM pulse_sources ORDER BY kind,name"
                )
            ),
            scan_matches=tuple(
                ScanMatch(
                    scan_id=text_field(row, "scan_id"),
                    accession_number=text_field(row, "accession"),
                )
                for row in connection.execute(
                    "SELECT * FROM pulse_scan_matches ORDER BY scan_id,accession"
                )
            ),
        )
