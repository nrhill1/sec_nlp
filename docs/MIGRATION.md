# Terminal workspace migration

The workspace replaces the all-command Pydantic root, analyze wizard, generic flow compiler/runner, and HTML dashboard. CLI and terminal actions share typed application results. Original research data and specialist serializers remain available.

## Commands

| Previous command | Current entry point |
| --- | --- |
| `sec-nlp` | Cached terminal workspace; help for non-interactive input |
| `analyze` | `research analyze` with existing presets/settings |
| `chat` | `research ask` |
| `retrieve` | `search` for metadata, `scan run` for bounded evidence, or `research retrieve` for the retained specialist |
| `efts` | `search` |
| `exb`, `warranty`, `financials`, `holdings`, `insider`, `events` | `research NAME` |
| `news` | `refresh --source news`, terminal headlines, and exports |
| `market` | `refresh --source market` and cached terminal market context |
| `invest init` | `workspace init` / `workspace configure` |
| `invest brief` | Explicit `refresh --source all` and `export` |
| `invest note` / `invest review` | `journal add` / `journal review` |
| `flow` | `research recipe --settings FILE.yaml` |
| `runs` | `workspace jobs`; specialist run registry remains in the Python observability API |
| `qdrant` | Configure your own vector service; use `research index` explicitly |
| `clean` | Inspect `workspace status`; manage chosen workspace directories yourself |
| `version` | `--version` |

Old command names return migration guidance rather than importing their former implementations. Ordinary specialist flags remain available after `research NAME`; positional ticker lists still work. Workspace paths and `--json` may follow the action. Help/version create no run or workspace.

## Data

Run `sec-nlp workspace migrate --workspace DESTINATION --from ORIGINAL` explicitly. Migration validates the input first, preserves originals, and imports known profiles, immutable journals, brief JSON snapshots, and authored recipes. Repeating it does not duplicate existing records. Conflicting IDs or different destination profiles are reported instead of overwriting user data.

SQLite owns filing identity, entity associations, manifests, read/bookmark state, notes and their filing links, scans, source checkpoints, news identity, and job history. `config.json` remains editable and contains the profile, source feeds, watchlist names/aliases/theses, and topics. Downloaded originals and readable content are cached separately.

Recognized SEC submission headers provide cache identity and declared company information. Files without sufficient trustworthy metadata remain registered external cache references with warnings; no issuer is inferred from the accession prefix. Migration reports what was imported and where expanded recipe settings were saved. Specialist output files are retained at their original paths.

The old HTML report renderer is retired. Saved `brief.json` evidence remains importable, and Markdown/JSON exports preserve timestamps, source URLs, notes, filing links, scan definitions, and coverage. Existing HTML files are not deleted.

## Authored jobs and profiling

The 80 repository jobs retain their original paths as compact catalog references. `jobs/catalog.yaml` holds shared data profiles and explicit per-job overrides. All expanded settings were fingerprinted before conversion; `tests/fixtures/recipe_hashes.json` verifies exact preservation. The catalog is configuration data, with five explicit step types: retrieve, chat, exhibit, analyze, and warranty.

`load_recipe()` also accepts standalone legacy JSON/YAML job shapes. `run_recipe()` uses ordinary calls and typed evidence dictionaries, preserves failure conditions and answer/output metadata, and writes an expanded settings snapshot. No registration plugin, compile layer, Runnable adapter, or new workflow framework is involved.

Profiling callers now load recipes directly, and command benchmarks dispatch through `research`. Labels such as `flow_run_id` remain in result envelopes for existing benchmark artifact compatibility.

## Imports

| Previous import | Owning module now |
| --- | --- |
| Package-level CLI/core/pipeline re-exports | Import the concrete config, pipeline, result, or utility module |
| `sec_nlp.app.investing.*` / `InvestingSettings` | `sec_nlp.app.pulse.*` / `PulseSettings` |
| `langchain_core.documents.Document` in ingestion/ranking/extraction | `sec_nlp.core.documents.DocumentRecord` |
| Direct LangChain conversion throughout runtime | `sec_nlp.adapters.documents` inside selected AI/vector adapters |
| `sec_nlp.cli.commands.root.Root` | `sec_nlp.cli.catalog.COMMANDS` and `sec_nlp.cli.__main__.main` |
| `sec_nlp.cli.presets` | `sec_nlp.pipelines.presets.analyze.profiles` |
| `sec_nlp.app.flows.models.FlowSpec` | `sec_nlp.app.workspace.recipes.ResearchRecipe` |
| `FlowDefaults`, `FlowStageSpec`, `FlowStageInputBinding` | `RecipeDefaults`, `RecipeStep`, `EvidenceInput` in that module |
| `FlowRunResult`, `FlowStageResult` | `RecipeRunResult`, `RecipeStepResult` |
| `load_flow_spec()` / `FlowRunner(...).run()` | `load_recipe()` / `run_recipe()` |
| `sec_nlp.app.flows.contracts` | `sec_nlp.app.workspace.evidence` |
| Native EFTS HTTP/search entry points | `sec_nlp.core.edgar.efts.EFTSClient`; native parsing/ranking remains |
| Separate SEC request implementations | `sec_nlp.core.edgar.transport` |
| Repository-relative runtime path discovery | `platformdirs`, explicit workspace paths, and `SEC_NLP_CACHE_DIR` / `SEC_NLP_DATA_DIR` |
| Generated `types/sec_nlp/*.pyi` | Annotated application source plus `sec_nlp/py.typed` |
| `types/<native>/__init__.pyi` | Native wheel-owned `.pyi` / `py.typed` files |

Pulse is the new name for the investing module and the terminal's former News & market pane. Update imports directly; no compatibility package is retained. Saved JSON formats, workspace paths, and existing investing data directories are unchanged, so the rename requires no data migration.

Unused async-support and StructuredTool wrappers, unwired analyze add-ons, unused flow contracts, duplicated warranty helpers, Questionary, and application-generated stubs are removed. Active asynchronous operations and statistical/native algorithms remain.

## Installation and validation

`make install-local PYTHON_BIN=/path/to/venv/bin/python` builds and installs the root application/market wheel and five sibling native wheels. There is no independently owned market distribution. Base installation does not require AI/vector extras. Development sync selects extras and uses `--inexact` to retain locally built siblings.

Use `make build-ext` after Rust changes, then the offline Python suite and `ty`/Ruff checks. Fresh-process tests prohibit optional imports, network attempts, and run creation on help/version and cached terminal startup. Research tests exercise the extras separately; they never call live models.
