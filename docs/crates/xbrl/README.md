# xbrl

Rust/PyO3 extension for XBRL parsing and fact extraction.

## Exported Python API

Classes:
- `PyXbrlParser`
- `PyXbrlFact`

Functions:
- `extract_facts`
- `extract_facts_from_file`

## Build

```bash
maturin develop -m crates/xbrl/Cargo.toml
```

Or from repo root:

```bash
make build-ext
```
