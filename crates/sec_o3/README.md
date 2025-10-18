# sec_o3

A fast, minimal SEC/EDGAR helper crate with optional Python bindings.

## Build

```bash
cargo build --release
cargo test --release
cargo bench
maturin develop -m sec_o3/Cargo.toml -F python --release
python -c "import edga_rs_py; print(edga_rs_py.parse_html('<html><title>Hi</title></html>'))"
```
