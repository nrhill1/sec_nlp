# entity

Rust/PyO3 extension for entity tagging and event mention extraction primitives.

## Exported Python API

Classes:
- `EntityTagger`
- `Entity`
- `EventMention`

## Build

```bash
maturin develop -m crates/entity/Cargo.toml
```

Or from repo root:

```bash
make build-ext
```

## Notes

See `crates/entity/data/README.md` for entity data assets used by the crate.
