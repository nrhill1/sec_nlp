# edgars

A fast, minimal SEC/EDGAR helper crate with optional Python bindings.

## Build

```bash
cargo build --release
cargo test --release
cargo bench
maturin develop -m edgars/Cargo.toml -F python --release
python -c "import edga_rs_py; print(edga_rs_py.parse_html('<html><title>Hi</title></html>'))"
```
