# main.py
import os
import time
import json
import argparse
import logging
import shutil
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from tqdm import tqdm

from langchain.prompts import load_prompt

from chains.sec import SECFilingSummaryChain
from utils.llms.local_t5_wrapper import LocalT5Wrapper
from utils.fetch import SECFilingDownloader
from utils.parse import PreProcessor

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")


def run_pipeline(symbol: str, start_date: str, end_date: str,
                 keyword: str, prompt_file: str, model_name: str) -> Optional[Path]:

    load_dotenv()

    email = os.getenv("EMAIL", "xxxxxx_xxxx@gmail.com")
    downloads_folder = os.getenv("DOWNLOADS_FOLDER", "downloads")
    output_folder = os.getenv("OUTPUT_FOLDER", "output")

    dl_path = Path(downloads_folder)
    out_path = Path(output_folder)

    logger.info(
        f"Starting pipeline for symbol: {symbol} from {start_date} to {end_date}")

    downloader = SECFilingDownloader(email, dl_path)
    downloader.add_symbol(symbol)
    downloader.download_filings(start_date=start_date, end_date=end_date)

    preprocessor = PreProcessor(dl_path)
    html_paths = preprocessor.html_paths_for_symbol(symbol)

    if not html_paths:
        logger.warning(f"No filings found for {symbol}.")
        return None

    html_path = html_paths[0]
    chunks = preprocessor.transform_html(html_path)

    relevant_chunks = [
        chunk for chunk in chunks if keyword.lower() in chunk.page_content.lower()]

    if not relevant_chunks:
        logger.warning(f"No chunks matched keyword '{keyword}' for {symbol}.")
        return None

    logger.info(
        f"{len(relevant_chunks)} relevant chunks found. Summarizing...")

    prompt_path = Path(prompt_file)
    prompt = load_prompt(prompt_path)

    llm = LocalT5Wrapper(model_name, max_new_tokens=1024)
    chain = SECFilingSummaryChain(prompt=prompt, llm=llm)

    summaries = []
    for chunk in tqdm(relevant_chunks, desc="Summarizing chunks"):
        try:
            result = chain.invoke({
                "symbol": symbol,
                "chunk": chunk.page_content,
                "search_term": keyword
            })
            if not result["summary"]:
                logger.warning(f"Failed to parse output for symbol {symbol}.")
            summaries.append(result.get(
                "summary", {"n/a": "No summary produced."}))
        except Exception as e:
            logger.error(f"Model invocation failed: {type(e).__name__}: {e}")
            traceback.print_exc()

    output_path = out_path / \
        f"{symbol.lower()}_{keyword.lower()}_{start_date}_to_{end_date}_summary.json"
    with open(output_path, "w") as f:
        json.dump({"symbol": symbol, "summaries": summaries}, f, indent=2)

    try:
        logger.info("Cleaning up downloaded files...")
        shutil.rmtree(dl_path / "sec-edgar-filings")
    except Exception as e:
        logger.error(
            f"Something went wrong while removing downloaded files: {type(e).__name__}: {e}")

    logger.info(f"Summary written to {output_path.resolve()}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Run summarization pipeline on SEC filings.")
    parser.add_argument("symbol", help="Stock symbol to fetch SEC filings for")
    parser.add_argument("start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("end", help="End date (YYYY-MM-DD)")
    parser.add_argument("keyword", help="Keyword to search in filings")
    parser.add_argument("--prompt_file", default="prompts/sample_prompt.yml",
                        help="Path to a .yml file containing the LLM prompt")
    parser.add_argument("--model_name", default="google/flan-t5-base",
                        help="The name of the LLM to use (default is )")

    args = parser.parse_args()

    start_time = time.perf_counter()
    output = run_pipeline(args.symbol, args.start, args.end,
                          args.keyword, args.prompt_file, args.model_name)
    elapsed_time = time.perf_counter() - start_time

    if output:
        logger.info(f"Pipeline complete in {elapsed_time:.2f} seconds.")
    else:
        logger.info("Pipeline finished with no output.")


if __name__ == "__main__":
    main()
