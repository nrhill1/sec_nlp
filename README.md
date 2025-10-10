# SEC Filing Summarization Pipeline

A CLI tool to **download**, **parse**, **filter**, and **summarize** SEC filings (e.g., 10-K, 10-Q) using a local Hugging Face T5 model.

---

## Features

- Download SEC filings directly from [EDGAR](https://www.sec.gov/edgar.shtml).
- Parse and chunk filings into text segments.
- Filter chunks by keyword (or run in keyword-agnostic mode).
- Summarize text using a local Hugging Face LLM (default: `google/flan-t5-base`).
- Output JSON summaries with filing metadata for traceability.

---

## Requirements

- **Python 3.11.3 (exact version)**
  Other versions (e.g. 3.11.5, 3.12, 3.13) are not supported.
- [`uv`](https://github.com/astral-sh/uv) — fast Python package manager and build tool.

---

## Setup

```bash
# clone this repo
git clone https://github.com/nrhill1/sec_nlp.git
cd sec_nlp

# create a strict 3.11.3 environment
uv venv --python 3.11.3
source .venv/bin/activate

# install in editable mode
uv pip install -e .
```

## Configuration

This project uses environment variables for configuration. Create a `.env` file in the project root:

```env
EMAIL=your_email@example.com
PINECONE_API_KEY=your-pinecone-api-key-here
```

## Usage

After setup and configuration, you can run the pipeline from the command line.

```bash
# Basic usage (with default settings)
uv run cli

# Multiple symbols at once
uv run cli AAPL MSFT TSLA

# Specify a custom date range and keyword
uv run cli AAPL --start_date 2024-01-01 --end_date 2024-12-31 --keyword "liquidity"

# Use a custom prompt file and a larger Hugging Face model
uv run cli AAPL --prompt_file ./prompts/financial_risk.yml --model_name google/flan-t5-large

