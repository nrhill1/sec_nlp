# SEC Filing Summarization Pipeline

A CLI tool to **download**, **parse**, **filter**, and **summarize** SEC filings (e.g., 10-K, 10-Q) using a local Hugging Face T5 model.

---

## Features

- Downloads SEC filings from EDGAR.
- Parses and chunks filings into text segments.
- Filters chunks by keyword (or runs full summarization).
- Summarizes using a local LLM (default is `flan-t5-base`).
- Outputs JSON summaries to disk.

---

## Setup

```bash
git clone https://github.com/nrhill1/sec_nlp.git
cd sec_nlp

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

***(This program exclusively requires the use of Python v3.11.3)***

---

## Basic Command Format

### Example command

```bash
python main.py SYMBOL START_DATE END_DATE KEYWORD

python main.py AAPL 2023-01-01 2024-01-01 revenue
```

### Example .env file

```env
EMAIL=your_email@example.com
DOWNLOADS_FOLDER=downloads
OUTPUT_FOLDER=output
```
