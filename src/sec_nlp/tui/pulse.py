# src/sec_nlp/tui/pulse.py
"""Present daily Pulse activity, market context, and authored review actions.

The pane reads compact workspace projections in cancellable workers. Its
messages request navigation or explicit refresh from the owning application;
selecting evidence never acknowledges it or starts provider work.
"""

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Literal

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from sec_nlp.app.pulse.models import WatchItem
from sec_nlp.app.workspace.pulse import (
    acknowledge,
    pulse_overview,
    pulse_page,
    record_review,
    remove_watch_item,
    save_watch_item,
    undo_acknowledgement,
)
from sec_nlp.app.workspace.pulse_models import (
    DueReview,
    PulseFilters,
    PulseItem,
    PulsePage,
    ReviewAction,
)
from sec_nlp.app.workspace.store import WorkspaceStore


async def _persist[**P, T](
    operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Finish a local write before propagating cancellation during shutdown."""
    pending = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        await pending
        raise


class PulsePane(Vertical):
    """Render cached daily review and request explicit evidence navigation.

    Shared workspace services own evidence and review state. This container
    coordinates lazy cached views, preserves authored drafts, and sends explicit
    navigation and refresh requests to the owning application.

    Attributes:
        store: Shared local evidence and review ledger.
        page: Most recently displayed immutable activity page.
    """

    DEFAULT_CSS = """
    PulsePane { height: 1fr; }
    PulsePane .pulse-scroll { padding: 0 1; }
    PulsePane .pulse-scroll Input { margin-bottom: 1; }
    #pulse-activity { min-height: 8; height: 12; }
    #pulse-detail { min-height: 6; height: auto; padding: 1; background: $boost; }
    #pulse-market { height: 10; }
    #pulse-sources { height: auto; }
    #pulse-watchlist, #pulse-reviews { height: 8; }
    #pulse-review-note { height: 5; }
    #pulse-page-label { height: 1; }
    """

    class Navigate(Message):
        """Carry selected cached evidence to another workspace pane.

        The immutable selection gives the owning application enough provenance
        to prepare research or notes without launching a provider request.

        Attributes:
            action: Destination requested by the user.
            item: Selected evidence with stable identity and source provenance.
        """

        def __init__(
            self,
            action: Literal["open", "journal", "search", "research"],
            item: PulseItem,
        ) -> None:
            """Retain the explicit destination and immutable evidence selection.

            Args:
                action: Destination chosen through a Pulse evidence action.
                item: Cached evidence and source provenance for that action.
            """
            super().__init__()
            self.action = action
            self.item = item

    class Refresh(Message):
        """Request an explicit refresh from the application's shared service.

        The application owns provider workers and their cancellation; the pane
        only identifies the source family that the user selected.

        Attributes:
            source: Provider family selected by the user.
        """

        def __init__(self, source: Literal["news", "market"]) -> None:
            """Retain the selected provider family without starting work."""
            super().__init__()
            self.source = source

    class Status(Message):
        """Report a human-readable local operation outcome.

        Status travels through the application message queue so local review
        operations use the same footer as provider and research actions.

        Attributes:
            text: Plain text status for the workspace footer.
        """

        def __init__(self, text: str) -> None:
            """Retain a status message without interpreting source markup."""
            super().__init__()
            self.text = text

    class ProfileChanged(Message):
        """Notify other panes that explicitly authored watchlist settings changed.

        The application invalidates hidden settings controls when it receives
        this message, while the originating pane refreshes its cached views.
        """

    def __init__(self, store: WorkspaceStore) -> None:
        """Bind local persistence and initialize navigation without reading history.

        Args:
            store: Existing workspace ledger shared with the owning application.
        """
        super().__init__()
        self.store = store
        self.page = PulsePage(items=())
        self._cursors: list[str | None] = [None]
        self._undo: list[str] = []
        self._edit_lock = asyncio.Lock()
        self._selected: PulseItem | None = None
        self._watchlist: tuple[WatchItem, ...] = ()
        self._reviews: tuple[DueReview, ...] = ()
        self._review: DueReview | None = None
        self._ready = False
        self._activated = False
        self._loaded: set[str] = set()

    def compose(self) -> ComposeResult:
        """Compose keyboard-accessible activity, context, watchlist, and review panes.

        Yields:
            Explicit refresh controls and tabs containing cached evidence and
            authored watchlist and review editors.
        """
        with Horizontal(classes="controls"):
            yield Button(
                "Refresh headlines", id="pulse-refresh-news", variant="primary"
            )
            yield Button("Refresh market", id="pulse-refresh-market")
        with TabbedContent(initial="pulse-activity-tab", id="pulse-tabs"):
            with TabPane("Activity", id="pulse-activity-tab"):
                with VerticalScroll(classes="pulse-scroll"):
                    with Horizontal(classes="controls"):
                        yield Select[str](
                            [("Focused", "focused"), ("All activity", "all")],
                            value="focused",
                            allow_blank=False,
                            id="pulse-scope",
                        )
                        yield Checkbox("New only", value=True, id="pulse-new")
                        yield Input(placeholder="Symbol", id="pulse-symbol")
                        yield Input(placeholder="Topic", id="pulse-topic")
                    with Horizontal(classes="controls"):
                        yield Input(placeholder="Source", id="pulse-source")
                        yield Input(placeholder="Form: 10-K", id="pulse-form")
                        yield Button("Apply filters", id="pulse-filter")
                    yield DataTable(
                        id="pulse-activity",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                    with Horizontal(classes="controls"):
                        yield Button(
                            "Previous", id="pulse-previous", disabled=True
                        )
                        yield Button("Next", id="pulse-next", disabled=True)
                        yield Button(
                            "Mark selected", id="pulse-mark", disabled=True
                        )
                        yield Button(
                            "Mark visible page",
                            id="pulse-mark-page",
                            disabled=True,
                        )
                        yield Button("Undo", id="pulse-undo", disabled=True)
                    yield Static(
                        "Page 1 · 0 items", id="pulse-page-label", markup=False
                    )
                    yield Static(
                        "Select evidence to inspect its dates, matches, and source.",
                        id="pulse-detail",
                        markup=False,
                    )
                    with Horizontal(classes="controls"):
                        yield Button(
                            "Open evidence", id="pulse-open", disabled=True
                        )
                        yield Button(
                            "Add note", id="pulse-journal", disabled=True
                        )
                        yield Button("Search", id="pulse-search", disabled=True)
                        yield Button(
                            "Research", id="pulse-research", disabled=True
                        )
            with TabPane("Market & sources", id="pulse-market-tab"):
                with VerticalScroll(classes="pulse-scroll"):
                    yield Static(
                        "Latest successful observations remain available after failed or news-only refreshes.",
                        markup=False,
                    )
                    yield DataTable(
                        id="pulse-market", cursor_type="row", zebra_stripes=True
                    )
                    yield Static(id="pulse-sources", markup=False)
            with TabPane("Watchlist", id="pulse-watchlist-tab"):
                with VerticalScroll(classes="pulse-scroll"):
                    yield DataTable(
                        id="pulse-watchlist",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                    yield Input(placeholder="Symbol", id="watch-symbol")
                    yield Input(
                        placeholder="Company / asset name", id="watch-name"
                    )
                    yield Input(
                        placeholder="Aliases (comma separated)",
                        id="watch-aliases",
                    )
                    yield Input(placeholder="Thesis", id="watch-thesis")
                    yield Input(
                        placeholder="Invalidation criteria",
                        id="watch-invalidation",
                    )
                    yield Input(
                        placeholder="Review on YYYY-MM-DD", id="watch-review"
                    )
                    with Horizontal(classes="controls"):
                        yield Button(
                            "Save watch item",
                            id="watch-save",
                            variant="primary",
                        )
                        yield Button("New item", id="watch-new")
                        yield Button("Remove item", id="watch-remove")
            with TabPane("Due reviews", id="pulse-reviews-tab"):
                with VerticalScroll(classes="pulse-scroll"):
                    yield DataTable(
                        id="pulse-reviews",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                    yield Static(
                        "Select a due thesis or journal review.",
                        id="pulse-review-detail",
                        markup=False,
                    )
                    yield TextArea(id="pulse-review-note")
                    yield Input(
                        placeholder="Next review YYYY-MM-DD (required to defer)",
                        id="pulse-review-date",
                    )
                    with Horizontal(classes="controls"):
                        yield Button(
                            "Complete review",
                            id="pulse-review-complete",
                            disabled=True,
                            variant="primary",
                        )
                        yield Button(
                            "Defer review",
                            id="pulse-review-defer",
                            disabled=True,
                        )

    def on_mount(self) -> None:
        """Initialize table columns without querying hidden projections."""
        for selector, columns in (
            (
                "#pulse-activity",
                ("State", "Discovered", "Kind", "Evidence", "Source"),
            ),
            (
                "#pulse-market",
                (
                    "Symbol",
                    "Observed",
                    "Close",
                    "1 session %",
                    "5 sessions %",
                    "Freshness",
                ),
            ),
            ("#pulse-watchlist", ("Symbol", "Name", "Review", "Thesis")),
            ("#pulse-reviews", ("Due", "Kind", "Symbol", "Review")),
        ):
            self.query_one(selector, DataTable).add_columns(*columns)
        self._ready = True

    def activate(self, *, changed: bool = False) -> None:
        """Load the visible local projection after navigation or an explicit action.

        Args:
            changed: Invalidate previously loaded projections after evidence or
                authored settings changed, then reload only the visible tab.
        """
        if not self._ready:
            return
        self._activated = True
        if changed:
            self._loaded.clear()
        active = self.query_one("#pulse-tabs", TabbedContent).active
        if active not in self._loaded:
            if active == "pulse-activity-tab":
                self._load_activity()
            else:
                self._load_context()

    def invalidate(self) -> None:
        """Discard hidden projection freshness without loading the pane."""
        self._loaded.clear()

    @on(TabbedContent.TabActivated, "#pulse-tabs")
    def activate_tab(self, event: TabbedContent.TabActivated) -> None:
        """Read hidden panes only when they become visible."""
        event.stop()
        if self._activated:
            self.activate()

    def _filters(self) -> PulseFilters:
        """Validate visible filters using the same model as scriptable commands."""
        scope = self.query_one("#pulse-scope", Select).value
        return PulseFilters(
            scope="all" if scope == "all" else "focused",
            new_only=self.query_one("#pulse-new", Checkbox).value,
            symbol=self.query_one("#pulse-symbol", Input).value.strip(),
            topic=self.query_one("#pulse-topic", Input).value.strip(),
            source=self.query_one("#pulse-source", Input).value.strip(),
            form=self.query_one("#pulse-form", Input).value.strip(),
        )

    @work(exclusive=True, group="pulse-page", exit_on_error=False)
    async def _load_activity(self) -> None:
        """Read a bounded activity page outside the UI event loop."""
        self.page = await asyncio.to_thread(
            pulse_page,
            self.store,
            self._filters(),
            cursor=self._cursors[-1],
            limit=50,
        )
        self._loaded.add("pulse-activity-tab")
        self._selected = None
        table = self.query_one("#pulse-activity", DataTable)
        table.clear()
        for item in self.page.items:
            table.add_row(
                "reviewed" if item.reviewed else "new",
                str(item.discovered_at.date()),
                item.kind,
                Text(item.title),
                Text(item.source),
                key=item.identity,
            )
        self.query_one("#pulse-page-label", Static).update(
            f"Page {len(self._cursors)} · {len(self.page.items)} items · Ordered by discovery time"
        )
        self.query_one("#pulse-previous", Button).disabled = (
            len(self._cursors) < 2
        )
        self.query_one("#pulse-next", Button).disabled = (
            self.page.next_cursor is None
        )
        self.query_one("#pulse-mark-page", Button).disabled = not any(
            not item.reviewed for item in self.page.items
        )
        self._show_selection(None)
        if not self.page.items:
            self.query_one("#pulse-detail", Static).update(
                "No matching activity. Use All activity or change filters to inspect other cached evidence."
            )

    @work(exclusive=True, group="pulse-context", exit_on_error=False)
    async def _load_context(self) -> None:
        """Load current market, source, watchlist, and due-review projections."""
        overview, settings = await asyncio.gather(
            asyncio.to_thread(pulse_overview, self.store),
            asyncio.to_thread(self.store.load_settings),
        )
        self._watchlist = settings.watchlist
        self._reviews = overview.due_reviews
        selected_review = self._review
        market = self.query_one("#pulse-market", DataTable)
        market.clear()
        for quote in overview.market:
            market.add_row(
                quote.symbol,
                str(quote.quote_date or "Unknown"),
                str(quote.close if quote.close is not None else "—"),
                str(
                    quote.change_1d_pct
                    if quote.change_1d_pct is not None
                    else "—"
                ),
                str(
                    quote.change_5d_pct
                    if quote.change_5d_pct is not None
                    else "—"
                ),
                "Stale" if quote.stale else "Current",
            )
        source_lines = [
            f"{item.status.name} · {item.status.kind} · {item.status.status} · {item.observed_at.isoformat()}\n{item.status.detail} ({item.status.records} records)"
            for item in overview.sources
        ]
        source_lines.extend(
            f"{item.symbol} → CIK {item.cik} · {'Stale mapping' if item.stale else 'Confirmed mapping'} · {item.checked_at.isoformat()}\n{item.name} · {item.source_url}\n{item.detail}"
            for item in overview.mappings
        )
        self.query_one("#pulse-sources", Static).update(
            "\n\n".join(source_lines) or "No source refreshes recorded."
        )
        table = self.query_one("#pulse-watchlist", DataTable)
        table.clear()
        for item in self._watchlist:
            table.add_row(
                item.symbol,
                Text(item.name),
                str(item.review_on or "Unscheduled"),
                Text(item.thesis),
                key=item.symbol,
            )
        reviews = self.query_one("#pulse-reviews", DataTable)
        reviews.clear()
        for item in self._reviews:
            reviews.add_row(
                str(item.review_on),
                item.target_kind,
                item.symbol or "General",
                Text(item.title),
                key=f"{item.target_kind}:{item.target_id}",
            )
        self._review = next(
            (
                item
                for item in self._reviews
                if selected_review is not None
                and item.target_kind == selected_review.target_kind
                and item.target_id == selected_review.target_id
            ),
            None,
        )
        self.query_one("#pulse-review-complete", Button).disabled = (
            self._review is None
        )
        self.query_one("#pulse-review-defer", Button).disabled = (
            self._review is None
        )
        if self._review is not None:
            reviews.move_cursor(row=self._reviews.index(self._review))
        else:
            self.query_one("#pulse-review-detail", Static).update(
                "Select a due thesis or journal review."
                if self._reviews
                else "No reviews due."
            )
        self._loaded.update(
            ("pulse-market-tab", "pulse-watchlist-tab", "pulse-reviews-tab")
        )

    def _show_selection(self, item: PulseItem | None) -> None:
        """Render evidence provenance without opening or dismissing it."""
        self._selected = item
        for identifier in (
            "pulse-mark",
            "pulse-open",
            "pulse-journal",
            "pulse-search",
            "pulse-research",
        ):
            self.query_one(f"#{identifier}", Button).disabled = item is None
        if item is None:
            return
        self.query_one("#pulse-mark", Button).disabled = item.reviewed
        self.query_one("#pulse-detail", Static).update(
            f"{item.title}\nDiscovered: {item.discovered_at.isoformat()}\nPublished: {item.published_at.isoformat() if item.published_at else 'Unavailable'} · Filed: {item.filing_date or '—'}\nSource: {item.source} · {item.url}\nMatches: {'; '.join(item.reasons) or 'All cached activity'}\n{'Reviewed' if item.reviewed else 'New — opening evidence does not mark it reviewed'}"
        )

    @on(DataTable.RowHighlighted, "#pulse-activity")
    @on(DataTable.RowSelected, "#pulse-activity")
    def select_activity(
        self, event: DataTable.RowHighlighted | DataTable.RowSelected
    ) -> None:
        """Inspect a highlighted row without triggering provider activity."""
        self._show_selection(
            next(
                (
                    item
                    for item in self.page.items
                    if item.identity == event.row_key.value
                ),
                None,
            )
        )

    @on(DataTable.RowSelected, "#pulse-watchlist")
    def select_watch(self, event: DataTable.RowSelected) -> None:
        """Copy the selected authored watchlist item into its editor."""
        item = next(
            (
                item
                for item in self._watchlist
                if item.symbol == event.row_key.value
            ),
            None,
        )
        if item:
            for selector, value in (
                ("watch-symbol", item.symbol),
                ("watch-name", item.name),
                ("watch-aliases", ", ".join(item.aliases)),
                ("watch-thesis", item.thesis),
                ("watch-invalidation", item.invalidation),
                ("watch-review", str(item.review_on or "")),
            ):
                self.query_one(f"#{selector}", Input).value = value

    @on(DataTable.RowHighlighted, "#pulse-reviews")
    @on(DataTable.RowSelected, "#pulse-reviews")
    def select_review(
        self, event: DataTable.RowHighlighted | DataTable.RowSelected
    ) -> None:
        """Choose a review target while preserving its original authored entry."""
        selected = next(
            (
                item
                for item in self._reviews
                if f"{item.target_kind}:{item.target_id}" == event.row_key.value
            ),
            None,
        )
        if selected is None:
            return
        self._review = selected
        self.query_one("#pulse-review-detail", Static).update(
            f"{self._review.title}\nThesis: {self._review.thesis}\nInvalidation: {self._review.invalidation}"
        )
        self.query_one("#pulse-review-complete", Button).disabled = False
        self.query_one("#pulse-review-defer", Button).disabled = False

    @work(group="pulse-edit", exit_on_error=False)
    async def _mark(self, identities: tuple[str, ...]) -> None:
        """Acknowledge only explicitly selected evidence and retain an undo token."""
        async with self._edit_lock:
            if not identities:
                return
            self._undo.append(
                await _persist(acknowledge, self.store, identities)
            )
            self.query_one("#pulse-undo", Button).disabled = False
            self._load_activity()
            self.post_message(
                self.Status(
                    f"Marked {len(identities)} activity items reviewed."
                )
            )

    @work(group="pulse-edit", exit_on_error=False)
    async def _undo_mark(self) -> None:
        """Restore the review state captured by the most recent local acknowledgement."""
        async with self._edit_lock:
            if not self._undo:
                return
            count = await _persist(
                undo_acknowledgement, self.store, self._undo[-1]
            )
            self._undo.pop()
            self.query_one("#pulse-undo", Button).disabled = not self._undo
            self._load_activity()
            self.post_message(
                self.Status(f"Restored {count} activity review states.")
            )

    @work(group="pulse-edit", exit_on_error=False)
    async def _save_watch(self, item: WatchItem) -> None:
        """Save authored watchlist details and recompute relevance locally."""
        async with self._edit_lock:
            await _persist(save_watch_item, self.store, item)
            self.activate(changed=True)
            self.post_message(self.ProfileChanged())
            self.post_message(
                self.Status(
                    f"Saved {item.symbol}. Cached relevance updated; refresh remains manual."
                )
            )

    @work(group="pulse-edit", exit_on_error=False)
    async def _remove_watch(self, symbol: str) -> None:
        """Remove a watchlist target while retaining historical evidence and notes."""
        async with self._edit_lock:
            await _persist(remove_watch_item, self.store, symbol)
            self.activate(changed=True)
            self.post_message(self.ProfileChanged())
            self.post_message(
                self.Status(
                    f"Removed {symbol} from the watchlist. Historical evidence and notes are retained."
                )
            )

    def _clear_watch(self) -> None:
        """Prepare an empty editor for a new independently authored watchlist item."""
        for identifier in (
            "watch-symbol",
            "watch-name",
            "watch-aliases",
            "watch-thesis",
            "watch-invalidation",
            "watch-review",
        ):
            self.query_one(f"#{identifier}", Input).value = ""
        self.query_one("#watch-symbol", Input).focus()

    @work(group="pulse-edit", exit_on_error=False)
    async def _record_review(self, action: ReviewAction) -> None:
        """Append an immutable completion or deferral and refresh the due queue."""
        async with self._edit_lock:
            await _persist(record_review, self.store, action)
            note = self.query_one("#pulse-review-note", TextArea)
            scheduled = self.query_one("#pulse-review-date", Input)
            if note.text == action.note:
                note.load_text("")
            if scheduled.value == str(action.next_review_on or ""):
                scheduled.value = ""
            self.activate(changed=True)
            self.post_message(
                self.Status(
                    "Review completed."
                    if action.action == "complete"
                    else "Review deferred."
                )
            )

    @on(Button.Pressed)
    def press_button(self, event: Button.Pressed) -> None:
        """Translate explicit buttons into shared local actions or navigation messages."""
        identifier = event.button.id or ""
        if not identifier.startswith(("pulse-", "watch-")):
            return
        event.stop()
        try:
            match identifier:
                case "pulse-refresh-news" | "pulse-refresh-market":
                    self.post_message(
                        self.Refresh(
                            "news" if identifier.endswith("news") else "market"
                        )
                    )
                case "pulse-filter":
                    self._cursors = [None]
                    self._load_activity()
                case "pulse-next":
                    if self.page.next_cursor:
                        self._cursors.append(self.page.next_cursor)
                        self._load_activity()
                case "pulse-previous":
                    if len(self._cursors) > 1:
                        self._cursors.pop()
                        self._load_activity()
                case "pulse-mark":
                    if self._selected:
                        self._mark((self._selected.identity,))
                case "pulse-mark-page":
                    self._mark(
                        tuple(
                            item.identity
                            for item in self.page.items
                            if not item.reviewed
                        )
                    )
                case "pulse-undo":
                    self._undo_mark()
                case (
                    "pulse-open"
                    | "pulse-journal"
                    | "pulse-search"
                    | "pulse-research"
                ):
                    if self._selected:
                        action: Literal[
                            "open", "journal", "search", "research"
                        ] = "open"
                        if identifier == "pulse-journal":
                            action = "journal"
                        elif identifier == "pulse-search":
                            action = "search"
                        elif identifier == "pulse-research":
                            action = "research"
                        self.post_message(self.Navigate(action, self._selected))
                case "watch-new":
                    self._clear_watch()
                case "watch-save":
                    review = self.query_one(
                        "#watch-review", Input
                    ).value.strip()
                    self._save_watch(
                        WatchItem(
                            symbol=self.query_one("#watch-symbol", Input).value,
                            name=self.query_one("#watch-name", Input).value,
                            aliases=tuple(
                                value.strip()
                                for value in self.query_one(
                                    "#watch-aliases", Input
                                ).value.split(",")
                                if value.strip()
                            ),
                            thesis=self.query_one("#watch-thesis", Input).value,
                            invalidation=self.query_one(
                                "#watch-invalidation", Input
                            ).value,
                            review_on=date.fromisoformat(review)
                            if review
                            else None,
                        )
                    )
                case "watch-remove":
                    symbol = (
                        self.query_one("#watch-symbol", Input)
                        .value.strip()
                        .upper()
                    )
                    if symbol:
                        self._remove_watch(symbol)
                case "pulse-review-complete" | "pulse-review-defer":
                    if self._review:
                        next_date = self.query_one(
                            "#pulse-review-date", Input
                        ).value.strip()
                        self._record_review(
                            ReviewAction(
                                target_kind=self._review.target_kind,
                                target_id=self._review.target_id,
                                action="complete"
                                if identifier.endswith("complete")
                                else "defer",
                                note=self.query_one(
                                    "#pulse-review-note", TextArea
                                ).text,
                                next_review_on=date.fromisoformat(next_date)
                                if next_date
                                else None,
                            )
                        )
        except ValueError as exc:
            self.post_message(self.Status(str(exc)))
