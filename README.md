# SEC Filing Summarization Pipeline

A CLI tool to **download**, **parse**, **filter**, and **summarize** SEC filings (e.g., 10-K, 10-Q) using a local Hugging Face T5 model.

---

## Features

- 📥 Downloads SEC filings directly from EDGAR.  
- 📝 Parses and chunks filings into text segments.  
- 🔍 Filters chunks by keyword (or runs full summarization in keyword-agnostic mode).  
- 🤖 Summarizes text using a local Hugging Face LLM (default: `google/flan-t5-base`).  
- 📂 Outputs JSON summaries with metadata for traceability.  

---

## Requirements

- **Python 3.11.3 (exact)**  
  This project will not install on other Python versions (e.g., 3.12 or 3.13).  

- [`uv`](https://github.com/astral-sh/uv) for fast installs and builds.  

---

## Setup

```bash
git clone https://github.com/nrhill1/sec_nlp.git
cd sec_nlp

# create a strict 3.11.3 environment
uv venv --python 3.11.3
source .venv/bin/activate

# install in editable mode
uv pip install -e .
