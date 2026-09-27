# src/sec_nlp/tui/app.py
"""Present cached evidence and explicit research actions in a terminal workspace.

The interface performs no network activity on mount. Cancellable workers call
shared application services only after the user requests refresh, search,
reading an uncached document, or specialist research.
"""

import asyncio
import re
import webbrowser
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import HttpUrl, TypeAdapter
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual.worker import Worker, WorkerState

from sec_nlp.app.pulse.models import JournalEntry, WatchItem
from sec_nlp.app.workspace.models import ScanSpec
from sec_nlp.app.workspace.pulse_models import RefreshProgress
from sec_nlp.app.workspace.service import WorkspaceService
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import FilingRecord
from sec_nlp.tui.pulse import PulsePane
from sec_nlp.types import JsonDict


class ResearchWorkspace(App[None]):
    """Own terminal presentation while shared services own persistent research.

    Provider and specialist work starts only after an explicit action. Cached
    panes load independently in workers, and Pulse messages prepare evidence
    handoff without changing review state or starting research implicitly.

    Attributes:
        store: Durable metadata, reading state, source coverage, and notes.
        service: Explicit provider actions shared with scriptable commands.
        accession: Filing currently selected in the reader.
    """

    TITLE = "sec-nlp · Research workspace"
    SUB_TITLE = "Evidence first · Refresh on request"
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh SEC"),
        Binding("ctrl+f", "search", "Search"),
        Binding("escape", "cancel", "Cancel work"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    CSS = """
    Screen { background: $surface; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 0 1; }
    .controls { height: auto; min-height: 3; align-vertical: middle; }
    .controls Input { width: 1fr; }
    .controls Button { width: auto; min-width: 10; margin-right: 1; }
    .controls Select { width: 24; }
    .controls Checkbox { width: auto; }
    DataTable { height: 1fr; }
    #reader-text { height: 1fr; min-height: 8; }
    #reader-related { height: 6; border-top: solid $primary; }
    #status { height: 2; background: $boost; padding: 0 1; }
    #coverage { height: 4; overflow-y: auto; color: $text-muted; }
    #advanced-settings { height: 6; }
    #observation { height: 5; }
    RichLog { height: 1fr; }
    .field-label { margin-top: 1; color: $text-muted; }
    #settings-scroll { padding: 1 2; }
    #settings-scroll Input { margin-bottom: 1; }
    """

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        store: WorkspaceStore | None = None,
    ) -> None:
        """Bind the terminal to a local store without contacting providers.

        Args:
            workspace: Optional directory used when constructing a new ledger.
            store: Existing ledger to reuse instead of opening ``workspace``.
        """
        super().__init__()
        self.store = store if store is not None else WorkspaceStore(workspace)
        self.service = WorkspaceService(self.store)
        self.accession: str | None = None
        self._source_url = ""
        self._sections: dict[str, int] = {}
        self._find_position = 0
        self._loaded_panes: set[str] = set()
        self._note_sources: tuple[HttpUrl, ...] = ()

    def compose(self) -> ComposeResult:
        """Compose inbox, search, reader, research, journal, and settings panes.

        Yields:
            The workspace header, cached evidence and editing panes, shared
            status line, and keyboard shortcut footer.
        """
        yield Header()
        with TabbedContent(initial="inbox-tab", id="workspace-tabs"):
            with TabPane("Inbox", id="inbox-tab"):
                with Horizontal(classes="controls"):
                    yield Input(
                        placeholder="Filter cached company, form, or accession",
                        id="inbox-filter",
                    )
                    yield Checkbox("Unread", id="unread-filter")
                    yield Checkbox("Saved", id="saved-filter")
                    yield Button("Refresh", id="refresh-sec", variant="primary")
                    yield Button(
                        "Continue SEC", id="continue-sec", disabled=True
                    )
                yield DataTable(
                    id="inbox", cursor_type="row", zebra_stripes=True
                )
                yield Static(id="coverage", markup=False)
            with TabPane("Search & scans", id="search-tab"):
                with Horizontal(classes="controls"):
                    yield Input(
                        placeholder="Search SEC filing text", id="search-query"
                    )
                    yield Button(
                        "Search", id="search-submit", variant="primary"
                    )
                with Horizontal(classes="controls"):
                    yield Input(
                        placeholder="Forms: 10-K, 10-Q, 8-K", id="search-forms"
                    )
                    yield Input(
                        placeholder="Tickers (optional)", id="search-symbols"
                    )
                    yield Input(
                        placeholder="From YYYY-MM-DD", id="search-start"
                    )
                    yield Input(placeholder="To YYYY-MM-DD", id="search-end")
                with Horizontal(classes="controls"):
                    yield Input(placeholder="Saved scan name", id="scan-name")
                    yield Button("Save scan", id="scan-save")
                    yield Select[str](
                        [], prompt="Saved scans", id="scan-select"
                    )
                    yield Button("Run scan", id="scan-run")
                yield Static(
                    "Search retrieves metadata. A scan caches up to 20 selected primary documents; neither runs automatically.",
                    markup=False,
                )
                yield DataTable(
                    id="search-results", cursor_type="row", zebra_stripes=True
                )
            with TabPane("Reader", id="reader-tab"):
                yield Static(
                    "Select a filing from the inbox or search results.",
                    id="reader-heading",
                    markup=False,
                )
                with Horizontal(classes="controls"):
                    yield Select[str](
                        [], prompt="Document", id="reader-document"
                    )
                    yield Button("Read document", id="reader-open")
                    yield Button("Bookmark", id="reader-bookmark")
                    yield Button("Source ↗", id="reader-source")
                with Horizontal(classes="controls"):
                    yield Select[str]([], prompt="Section", id="reader-section")
                    yield Input(
                        placeholder="Find in this document", id="reader-find"
                    )
                    yield Button("Find next", id="reader-find-next")
                yield TextArea(
                    read_only=True, id="reader-text", show_line_numbers=False
                )
                yield RichLog(id="reader-related", wrap=True, markup=False)
            with TabPane("Pulse", id="news-tab"):
                yield PulsePane(self.store)
            with TabPane("Research", id="research-tab"):
                with Horizontal(classes="controls"):
                    yield Select[str](
                        [
                            (label, name)
                            for label, name in (
                                ("Financial statements", "financials"),
                                ("Insider activity", "insider"),
                                ("13F holdings", "holdings"),
                                ("Warranty", "warranty"),
                                ("Exhibits", "exb"),
                                ("Events", "events"),
                                ("AI analysis", "analyze"),
                                ("Ask evidence", "ask"),
                                ("Index evidence", "index"),
                            )
                        ],
                        value="financials",
                        allow_blank=False,
                        id="research-kind",
                    )
                    yield Input(
                        placeholder="Symbols: AAPL, MSFT", id="research-symbols"
                    )
                    yield Button(
                        "Run research", id="research-run", variant="primary"
                    )
                yield Input(
                    placeholder="Question or topic (for optional AI research)",
                    id="research-question",
                )
                yield Label(
                    "Advanced specialist settings (JSON; optional)",
                    classes="field-label",
                )
                yield TextArea("{}", id="advanced-settings")
                yield RichLog(id="research-log", wrap=True, markup=False)
            with TabPane("Journal", id="journal-tab"):
                with Horizontal(classes="controls"):
                    yield Input(
                        placeholder="Symbol (optional)", id="note-symbol"
                    )
                    yield Input(
                        placeholder="Review on YYYY-MM-DD", id="note-review"
                    )
                    yield Checkbox(
                        "Attach selected filing", value=True, id="note-link"
                    )
                yield TextArea(id="observation")
                yield Input(placeholder="Thesis", id="note-thesis")
                yield Input(
                    placeholder="What would invalidate this view?",
                    id="note-invalidation",
                )
                with Horizontal(classes="controls"):
                    yield Button("Save note", id="note-save", variant="primary")
                    yield Button("Due for review", id="note-due")
                    yield Button("All notes", id="note-all")
                yield RichLog(id="journal-log", wrap=True, markup=False)
            with TabPane("Settings", id="settings-tab"):
                with VerticalScroll(id="settings-scroll"):
                    yield Label("Workspace", classes="field-label")
                    yield Static(str(self.store.path), markup=False)
                    yield Label("Name", classes="field-label")
                    yield Input(id="profile-name")
                    yield Label(
                        "SEC identity: your name and contact email",
                        classes="field-label",
                    )
                    yield Input(id="profile-contact")
                    yield Label(
                        "Investing / observation goal", classes="field-label"
                    )
                    yield Input(id="profile-goal")
                    yield Label(
                        "Watchlist symbols (comma separated)",
                        classes="field-label",
                    )
                    yield Input(id="profile-symbols")
                    yield Static(
                        "Profiles retain feed definitions, theses, and aliases in config.json. Nothing refreshes until requested.",
                        markup=False,
                    )
                    with Horizontal(classes="controls"):
                        yield Button(
                            "Save settings",
                            id="profile-save",
                            variant="primary",
                        )
                        yield Button("Export Markdown", id="export-markdown")
                        yield Button("Export JSON", id="export-json")
        yield Static(
            "Cached workspace · No network activity on launch",
            id="status",
            markup=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        """Populate cached state without initializing external capabilities."""
        for identifier in ("#inbox", "#search-results"):
            table = self.query_one(identifier, DataTable)
            table.add_columns("State", "Filed", "Form", "Company", "Accession")
        self._reload_inbox()
        self.query_one("#inbox", DataTable).focus()

    @on(TabbedContent.TabActivated, "#workspace-tabs")
    def activate_pane(self, event: TabbedContent.TabActivated) -> None:
        """Load cached state only when its workspace pane becomes visible."""
        identifier = event.pane.id or ""
        if identifier == "news-tab":
            self.query_one(PulsePane).activate()
        elif identifier not in self._loaded_panes:
            if identifier == "search-tab":
                self._reload_scans()
            elif identifier == "journal-tab":
                self._reload_journal()
            elif identifier == "settings-tab":
                self._reload_profile()
            self._loaded_panes.add(identifier)

    @work(exclusive=True, group="profile-cache", exit_on_error=False)
    async def _reload_profile(self) -> None:
        """Populate editable profile controls without blocking terminal interaction."""
        profile = await asyncio.to_thread(self.store.load_settings)
        for selector, value in (
            ("#profile-name", profile.name),
            ("#profile-contact", profile.user_agent),
            ("#profile-goal", profile.goal),
            (
                "#profile-symbols",
                ", ".join(item.symbol for item in profile.watchlist),
            ),
        ):
            self.query_one(selector, Input).value = value

    @on(PulsePane.Status)
    def pulse_status(self, event: PulsePane.Status) -> None:
        """Display shared Pulse action results in the workspace status line."""
        self._status(event.text)

    @on(PulsePane.Refresh)
    def pulse_refresh(self, event: PulsePane.Refresh) -> None:
        """Run a provider operation explicitly requested from Pulse."""
        self._refresh(event.source)

    @on(PulsePane.ProfileChanged)
    def pulse_profile_changed(self) -> None:
        """Invalidate hidden profile controls after an authored watchlist edit."""
        self._loaded_panes.discard("settings-tab")

    @on(PulsePane.Navigate)
    def pulse_navigate(self, event: PulsePane.Navigate) -> None:
        """Open evidence or prepare a note or research action without auto-running it."""
        item = event.item
        tabs = self.query_one("#workspace-tabs", TabbedContent)
        symbols = ", ".join(item.symbols)
        match event.action:
            case "open":
                if item.accession_number:
                    self._read_filing(item.accession_number)
                else:
                    webbrowser.open(item.url)
            case "journal":
                self.accession = item.accession_number
                self._note_sources = (HttpUrl(item.url),)
                self.query_one("#note-symbol", Input).value = (
                    item.symbols[0] if item.symbols else ""
                )
                self.query_one("#note-link", Checkbox).value = (
                    item.accession_number is not None
                )
                self.query_one("#observation", TextArea).load_text(
                    f"Evidence: {item.title}\nSource: {item.url}\nObservation: "
                )
                tabs.active = "journal-tab"
                self.query_one("#observation", TextArea).focus()
            case "search":
                self.query_one("#search-query", Input).value = item.title
                self.query_one("#search-symbols", Input).value = symbols
                tabs.active = "search-tab"
                self.query_one("#search-query", Input).focus()
            case "research":
                self.query_one("#research-symbols", Input).value = symbols
                self.query_one("#research-question", Input).value = item.title
                tabs.active = "research-tab"
                self.query_one("#research-question", Input).focus()

    def _status(self, message: str) -> None:
        """Display plain text status without interpreting retrieved markup."""
        if self.query("#status"):
            self.query_one("#status", Static).update(message)

    @work(exclusive=True, group="inbox-cache", exit_on_error=False)
    async def _reload_inbox(self) -> None:
        """Populate the table and coverage indicator from local storage."""
        table = self.query_one("#inbox", DataTable)
        items = await asyncio.to_thread(
            self.store.list_filings,
            query=self.query_one("#inbox-filter", Input).value,
            unread_only=self.query_one("#unread-filter", Checkbox).value,
            bookmarked_only=self.query_one("#saved-filter", Checkbox).value,
            limit=500,
        )
        table.clear()
        for item in items:
            filing = item.filing
            table.add_row(
                ("! " if item.source_withdrawn else "")
                + ("★" if item.bookmarked else "·" if item.is_read else "new"),
                str(filing.filed_date or "—"),
                filing.form_type,
                Text(
                    "; ".join(
                        entity.name or entity.cik for entity in filing.entities
                    )
                ),
                filing.accession_number,
                key=filing.accession_number,
            )
        checkpoints = await asyncio.to_thread(self.store.list_checkpoints)
        self.query_one("#continue-sec", Button).disabled = not any(
            item.source in {"sec-atom", "sec-coverage"}
            and not item.scope
            and item.status != "complete"
            for item in checkpoints
        )
        coverage = "\n".join(
            f"{item.source}: {item.status} · {item.detail}"
            for item in checkpoints
            if item.source in {"sec-atom", "sec-coverage"}
        )
        self.query_one("#coverage", Static).update(
            coverage
            or "No filings fetched yet. Refresh explicitly to discover current filings."
        )

    @work(exclusive=True, group="scan-cache", exit_on_error=False)
    async def _reload_scans(self) -> None:
        """Populate saved scan choices from their durable identifiers."""
        self.query_one("#scan-select", Select).set_options(
            [
                (item.name, item.scan_id)
                for item in await asyncio.to_thread(self.store.list_scans)
            ]
        )

    @work(exclusive=True, group="journal-cache", exit_on_error=False)
    async def _reload_journal(self) -> None:
        """Display saved observations and review dates without model interpretation."""
        log = self.query_one("#journal-log", RichLog)
        log.clear()
        for entry in await asyncio.to_thread(self.store.list_notes, limit=100):
            log.write(
                f"{entry.created_at.date()} · {entry.symbol or 'General'} · Review {entry.review_on or 'unscheduled'}\n{entry.observation}\nThesis: {entry.thesis}\nInvalidation: {entry.invalidation}\n"
            )

    def _reload_news(self) -> None:
        """Invalidate Pulse projections after explicit evidence changes."""
        pane = self.query_one(PulsePane)
        if (
            self.query_one("#workspace-tabs", TabbedContent).active
            == "news-tab"
        ):
            pane.activate(changed=True)
        else:
            pane.invalidate()

    def _scan_spec(self) -> ScanSpec:
        """Validate the explicit query controls as one shared scan definition."""
        start = self.query_one("#search-start", Input).value.strip()
        end = self.query_one("#search-end", Input).value.strip()
        query = self.query_one("#search-query", Input).value
        return ScanSpec(
            name=self.query_one("#scan-name", Input).value
            or query
            or "SEC search",
            query=query,
            forms=tuple(
                self.query_one("#search-forms", Input)
                .value.replace(",", " ")
                .split()
            ),
            symbols=tuple(
                self.query_one("#search-symbols", Input)
                .value.upper()
                .replace(",", " ")
                .split()
            ),
            start_date=date.fromisoformat(start) if start else None,
            end_date=date.fromisoformat(end) if end else None,
        )

    @on(Input.Changed, "#inbox-filter")
    @on(Checkbox.Changed, "#unread-filter")
    @on(Checkbox.Changed, "#saved-filter")
    def filter_inbox(self) -> None:
        """Apply local inbox filters without refreshing providers."""
        self._reload_inbox()

    @on(DataTable.RowSelected, "#inbox")
    @on(DataTable.RowSelected, "#search-results")
    def select_filing(self, event: DataTable.RowSelected) -> None:
        """Open the filing explicitly selected by keyboard or mouse."""
        accession = event.row_key.value
        if accession:
            self.accession = accession
            self._read_filing(accession)

    @work(exclusive=True, group="evidence", exit_on_error=False)
    async def _refresh(self, source: Literal["sec", "news", "market"]) -> None:
        """Fetch only the source family explicitly selected by the user."""
        self._status(
            f"Refreshing {source}… Escape cancels; completed pages are retained."
        )
        result = await self.service.refresh(
            source=source, on_progress=self._refresh_progress
        )
        self._reload_inbox()
        self._reload_news()
        self._status(
            result.message
            + (" " + "; ".join(result.errors) if result.errors else "")
        )

    async def _refresh_progress(self, progress: RefreshProgress) -> None:
        """Render durable source progress without interpreting provider content."""
        self._status(
            f"Refresh {progress.completed}/{progress.total} · {progress.source}: {progress.status} · Escape cancels"
        )

    @work(exclusive=True, group="evidence", exit_on_error=False)
    async def _search(self, spec: ScanSpec) -> None:
        """Populate search results from an explicitly submitted SEC query."""
        self._status("Searching SEC filing text…")
        result = await self.service.search(spec)
        self._show_search(result.filings)
        self._status(result.message)

    def _show_search(self, filings: Sequence[FilingRecord]) -> None:
        """Render returned filing evidence without re-querying the network."""
        table = self.query_one("#search-results", DataTable)
        table.clear()
        for filing in filings:
            table.add_row(
                "",
                str(filing.filed_date or "—"),
                filing.form_type,
                Text("; ".join(entity.name for entity in filing.entities)),
                filing.accession_number,
                key=filing.accession_number,
            )
        self._reload_inbox()

    @work(exclusive=True, group="evidence", exit_on_error=False)
    async def _run_scan(self, identifier: str) -> None:
        """Run the selected saved scan and retain bounded downloaded evidence."""
        self._status("Running saved scan… Escape cancels.")
        result = await self.service.run_scan(identifier)
        self._show_search(result.filings)
        self._status(
            result.message
            + (" Results are partial." if result.partial else "")
            + (" " + "; ".join(result.errors) if result.errors else "")
        )

    @work(exclusive=True, group="evidence", exit_on_error=False)
    async def _read_filing(
        self, accession: str, filename: str | None = None
    ) -> None:
        """Load a cached or explicitly selected filing document into the reader."""
        self._status("Opening filing evidence…")
        self.accession = accession
        self._source_url = ""
        self._find_position = 0
        self.query_one("#reader-text", TextArea).load_text("")
        self.query_one("#reader-related", RichLog).clear()
        self.query_one("#reader-section", Select).set_options([])
        self.query_one("#reader-document", Select).set_options([])
        self.query_one("#workspace-tabs", TabbedContent).active = "reader-tab"
        manifest = await self.service.manifest(accession)
        self._source_url = str(manifest.filing.filing_url)
        self.query_one("#reader-document", Select).set_options(
            [
                (f"{item.document_type}: {item.filename}", item.filename)
                for item in manifest.documents
            ]
        )
        self.query_one("#reader-heading", Static).update(
            f"{accession} · {manifest.filing.form_type} · Choose a document"
        )
        content = await self.service.read(accession, filename=filename)
        self._source_url = str(content.document.url)
        self.query_one(
            "#reader-document", Select
        ).value = content.document.filename
        self.query_one("#reader-heading", Static).update(
            f"{accession} · {manifest.filing.form_type} · {content.document.filename}"
        )
        self.query_one("#reader-text", TextArea).load_text(content.text)
        self._sections = {
            f"{number}: {line.strip()[:70]}": number
            for number, line in enumerate(content.text.splitlines())
            if re.match(
                r"^\s*(?:ITEM\s+\d|PART\s+[IVX]|CONSOLIDATED\s+)",
                line,
                re.IGNORECASE,
            )
        }
        self.query_one("#reader-section", Select).set_options(
            [(label, label) for label in self._sections]
        )
        related = self.query_one("#reader-related", RichLog)
        related.clear()
        from sec_nlp.app.workspace.headlines import related_headlines

        headlines, settings, notes = await asyncio.gather(
            asyncio.to_thread(self.store.list_news),
            asyncio.to_thread(self.store.load_settings),
            asyncio.to_thread(
                self.store.list_notes, accession_number=accession
            ),
        )
        for headline, reason in related_headlines(
            manifest.filing,
            headlines,
            settings.watchlist,
        ):
            related.write(
                f"{headline.published_at or 'Undated'} · {headline.source} · {headline.title}\n{headline.url}\n{reason}"
            )
        for note in notes:
            related.write(f"Note: {note.observation}")
        self.query_one("#workspace-tabs", TabbedContent).active = "reader-tab"
        self._reload_inbox()
        self._status(
            "Evidence cached locally. Source links and related notes remain attached."
        )

    @on(Select.Changed, "#reader-section")
    def jump_section(self, event: Select.Changed) -> None:
        """Jump to a detected filing heading in the full-text reader."""
        if isinstance(event.value, str) and event.value in self._sections:
            self.query_one("#reader-text", TextArea).move_cursor(
                (self._sections[event.value], 0)
            )

    @work(exclusive=True, group="evidence", exit_on_error=False)
    async def _research(self, capability: str, values: JsonDict) -> None:
        """Run selected optional research with cancellable process ownership."""
        from sec_nlp.app.workspace.research import execute_research

        self._status(f"Running {capability}… Escape cancels.")
        result = await execute_research(self.store, capability, values)
        self.query_one("#research-log", RichLog).write(
            result.model_dump_json(indent=2)
        )
        self._status(
            result.error
            or f"Research completed: {len(result.outputs)} output files."
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Surface errors and cancellation without closing the workspace."""
        if event.state == WorkerState.ERROR:
            if event.worker.group == "evidence":
                self._reload_inbox()
                self._reload_news()
            self._status(f"Action failed: {event.worker.error}")
        elif (
            event.state == WorkerState.CANCELLED
            and event.worker.group == "evidence"
        ):
            self._reload_inbox()
            self._reload_news()
            self._status(
                "Cancelled. Previously saved evidence remains available."
            )

    @on(Button.Pressed)
    def press_button(self, event: Button.Pressed) -> None:
        """Translate explicit button actions into shared service calls."""
        identifier = event.button.id
        try:
            match identifier:
                case "refresh-sec" | "continue-sec":
                    self._refresh("sec")
                case "refresh-news":
                    self._refresh("news")
                case "refresh-market":
                    self._refresh("market")
                case "search-submit":
                    self._search(self._scan_spec())
                case "scan-save":
                    self._save_scan(self._scan_spec())
                case "scan-run":
                    selected = self.query_one("#scan-select", Select).value
                    if isinstance(selected, str):
                        self._run_scan(selected)
                case "reader-open":
                    selected = self.query_one("#reader-document", Select).value
                    if self.accession and isinstance(selected, str):
                        self._read_filing(self.accession, selected)
                case "reader-bookmark":
                    if self.accession:
                        self._bookmark(self.accession)
                case "reader-source":
                    if self._source_url:
                        webbrowser.open(self._source_url)
                case "reader-find-next":
                    self._find_next()
                case "note-save":
                    self._save_note()
                case "note-due":
                    self.query_one(
                        "#workspace-tabs", TabbedContent
                    ).active = "news-tab"
                    self.query_one(PulsePane).query_one(
                        "#pulse-tabs", TabbedContent
                    ).active = "pulse-reviews-tab"
                case "note-all":
                    self._reload_journal()
                case "profile-save":
                    self._save_profile()
                case "research-run":
                    selected = self.query_one("#research-kind", Select).value
                    if isinstance(selected, str):
                        values = TypeAdapter(JsonDict).validate_json(
                            self.query_one("#advanced-settings", TextArea).text
                        )
                        symbols = (
                            self.query_one("#research-symbols", Input)
                            .value.upper()
                            .replace(",", " ")
                            .split()
                        )
                        if symbols:
                            values["symbols"] = symbols
                        question = self.query_one(
                            "#research-question", Input
                        ).value
                        if question:
                            if selected == "ask":
                                values["question"] = question
                            elif selected == "index":
                                values["queries"] = [question]
                            else:
                                values["topics"] = [question]
                        self._research(selected, values)
                case "export-markdown" | "export-json":
                    self._export(
                        "json" if identifier == "export-json" else "markdown"
                    )
        except (ValueError, OSError) as exc:
            self._status(str(exc))

    @work(exclusive=True, group="scan-save", exit_on_error=False)
    async def _save_scan(self, spec: ScanSpec) -> None:
        """Save explicitly authored scan settings without blocking keyboard input."""
        await asyncio.to_thread(self.store.save_scan, spec)
        self._reload_scans()
        self._status(
            "Scan saved. Run it explicitly when you want new evidence."
        )

    @work(exclusive=True, group="bookmark-save", exit_on_error=False)
    async def _bookmark(self, accession: str) -> None:
        """Persist a selected bookmark independently from review acknowledgement."""
        await asyncio.to_thread(self.store.set_bookmarked, accession)
        self._reload_inbox()
        self._status("Filing bookmarked.")

    @work(exclusive=True, group="export", exit_on_error=False)
    async def _export(self, output_format: Literal["json", "markdown"]) -> None:
        """Export cached evidence outside the UI event loop after an explicit action."""
        from sec_nlp.app.workspace.export import export_workspace

        extension = "json" if output_format == "json" else "md"
        destination = (
            self.store.path
            / "exports"
            / f"workspace-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.{extension}"
        )
        await asyncio.to_thread(
            export_workspace,
            self.store,
            destination,
            output_format=output_format,
        )
        self._status(f"Exported {destination}")

    def _find_next(self) -> None:
        """Select the next case-insensitive occurrence in the full document."""
        query = self.query_one("#reader-find", Input).value.casefold()
        area = self.query_one("#reader-text", TextArea)
        if not query:
            return
        position = area.text.casefold().find(query, self._find_position)
        if position < 0:
            position = area.text.casefold().find(query)
        if position < 0:
            self._status("No match in this document.")
            return
        prefix = area.text[:position]
        area.move_cursor((prefix.count("\n"), len(prefix.rsplit("\n", 1)[-1])))
        self._find_position = position + len(query)
        self._status("Match found; Find next wraps to the beginning.")

    @work(exclusive=True, group="journal-save", exit_on_error=False)
    async def _save_note(self) -> None:
        """Append an authored note with optional filing and review links."""
        review = self.query_one("#note-review", Input).value.strip()
        entry = JournalEntry(
            entry_id=uuid4().hex,
            created_at=datetime.now(UTC),
            symbol=self.query_one("#note-symbol", Input).value or None,
            observation=self.query_one("#observation", TextArea).text,
            thesis=self.query_one("#note-thesis", Input).value,
            invalidation=self.query_one("#note-invalidation", Input).value,
            review_on=date.fromisoformat(review) if review else None,
            sources=self._note_sources,
        )
        await asyncio.to_thread(
            self.store.save_note,
            entry,
            related_accession=self.accession
            if self.query_one("#note-link", Checkbox).value
            else None,
        )
        observation = self.query_one("#observation", TextArea)
        if observation.text == entry.observation:
            observation.load_text("")
        if self._note_sources == entry.sources:
            self._note_sources = ()
        self._reload_news()
        self._reload_journal()
        self._status("Research note saved.")

    @work(exclusive=True, group="profile-save", exit_on_error=False)
    async def _save_profile(self) -> None:
        """Save user preferences while preserving existing thesis and feed details."""
        profile = await asyncio.to_thread(self.store.load_settings)
        existing = {item.symbol: item for item in profile.watchlist}
        symbols = (
            self.query_one("#profile-symbols", Input)
            .value.upper()
            .replace(",", " ")
            .split()
        )
        watchlist = tuple(
            existing.get(symbol, WatchItem(symbol=symbol))
            for symbol in dict.fromkeys(symbols)
        )
        updated = profile.model_copy(
            update={
                "name": self.query_one("#profile-name", Input).value,
                "user_agent": self.query_one("#profile-contact", Input).value,
                "goal": self.query_one("#profile-goal", Input).value,
                "watchlist": watchlist,
            }
        )
        await asyncio.to_thread(
            self.store.save_settings,
            type(profile).model_validate_json(updated.model_dump_json()),
        )
        self._reload_news()
        self._status("Settings saved. Refresh remains manual.")

    def action_refresh(self) -> None:
        """Refresh SEC metadata explicitly from the keyboard shortcut."""
        self._refresh("sec")

    def action_search(self) -> None:
        """Focus the search pane without issuing a query."""
        self.query_one("#workspace-tabs", TabbedContent).active = "search-tab"
        self.query_one("#search-query", Input).focus()

    def action_cancel(self) -> None:
        """Cancel active provider or research work while preserving saved evidence."""
        self.workers.cancel_group(self, "evidence")


def launch_workspace(workspace: Path | None = None) -> None:
    """Launch the terminal interface for an explicit or default workspace."""
    ResearchWorkspace(workspace).run()
