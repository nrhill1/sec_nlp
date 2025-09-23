import os
import time
import json
import argparse
import logging
import shutil
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from .pipeline import run_pipeline

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")


def parse_args() -> argparse.Namespace:
    today = datetime.today()
    one_year_ago = today - timedelta(days=365)

    parser = argparse.ArgumentParser(
        description="Run summarization pipeline on SEC filings."
    )

    parser.add_argument(
        "symbols", nargs="+", help="Stock symbols to fetch SEC filings for (space-separated)",
        default=["AAPL", "TSLA", "GOOG"])
    parser.add_argument("--start_date", default=one_year_ago.strftime("%Y-%m-%d"),
                        help="Start date (YYYY-MM-DD). Defaults to one year ago.")
    parser.add_argument("--end_date", default=today.strftime("%Y-%m-%d"),
                        help="End date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--keyword", default="revenue",
                        help="Keyword to search in filings (default: revenue)")
    parser.add_argument("--prompt_file", default="./prompts/sample_prompt.yml",
                        help="Path to a .yml file containing the LLM prompt")
    parser.add_argument("--model_name", default="google/flan-t5-base",
                        help="The name of the LLM to use")

    args = parser.parse_args()

    return args


def setup_folders() -> (Path, Path):
    base_folder = Path(__file__).parent.parent.resolve()
    output_folder = base_folder / "outputs"
    downloads_folder = base_folder / "downloads"

    output_folder.mkdir(parents=True, exist_ok=True)
    downloads_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Output folder: {output_folder.resolve()}")
    logger.info(f"Downloads folder: {downloads_folder.resolve()}")

    return output_folder, downloads_folder


def cleanup_downloads(downloads_folder: Path):
    try:
        logger.info("Cleaning up downloaded files...")
        shutil.rmtree(downloads_folder / "sec-edgar-filings")
    except Exception as e:
        logger.error(f"Cleanup failed: {type(e).__name__}: {e}")


def main():
    args = parse_args()
    load_dotenv()

    output_folder, downloads_folder = setup_folders()

    start_time = time.perf_counter()

    for symbol in args.symbols:
        logger.info(
            f"Starting pipeline for {symbol} ({args.start_date} → {args.end_date})")
        run_pipeline(symbol, args.start_date, args.end_date,
                     args.keyword, args.prompt_file, args.model_name,
                     out_path=output_folder, dl_path=downloads_folder)

    cleanup_downloads(downloads_folder)
    elapsed_time = time.perf_counter() - start_time
    logger.info(f"Pipeline complete in {elapsed_time:.2f} seconds.")


if __name__ == "__main__":
    main()
