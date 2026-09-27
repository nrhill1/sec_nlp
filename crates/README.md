# Crate Docs

Rust extension documentation:

- `corr/README.md`
- `efts/README.md`
- `entity/README.md`
- `market/README.md`
- `newswatch/README.md`
- `xbrl/README.md`

`efts` provides offline response parsing and keyword ranking. SEC HTTP requests
are owned by the Python `core.edgar.transport` layer. `newswatch` returns upstream
news records; date-aware identity normalization is owned by `core.news` in Python.

All crates can be built together from repo root with:

```bash
make build-ext
```
