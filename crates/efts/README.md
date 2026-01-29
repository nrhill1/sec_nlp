# efts

Python extension module (pyo3) for SEC EDGAR Full-Text Search (EFTS).

## Build (maturin)

maturin develop -m crates/efts/Cargo.toml

## Usage

from efts import EFTSClient

client = EFTSClient(user_agent="SEC NLP Tool (me@example.com)")
response = client.search("warranty accrual", forms=["10-K"], limit=5)

# response is a dict with keys: query, total, hits, start, limit
hits = client.search_all("warranty accrual", forms=["10-K"], max_results=25)

## Smoke check

EFTS_USER_AGENT="SEC NLP Tool (me@example.com)" make -C crates/efts smoke
