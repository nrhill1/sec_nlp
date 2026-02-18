# corr

Rust/PyO3 extension for statistical correlation and return/event-study utilities.

## Exported Python API

Functions:
- `pearson`
- `spearman`
- `simple_returns`
- `cumulative_return`
- `car`
- `rolling_returns`
- `std_dev`
- `volume_spike`
- `average_true_range`
- `garman_klass`
- `beta`
- `event_study`

Types:
- `EventStudyResult`

## Build

```bash
maturin develop -m crates/corr/Cargo.toml
```

Or from repo root:

```bash
make build-ext
```
