import os
import time
import json
import logging
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import List

from tqdm import tqdm

from langchain.prompts import load_prompt

from sec_nlp.chains import SECFilingSummaryChain
from sec_nlp.embeddings.pinecone import PineconeEmbedder
from sec_nlp.llms import LocalT5Wrapper
from sec_nlp.utils import SECFilingDownloader, PreProcessor


logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    symbol: str
    start_date: str
    end_date: str
    keyword: str
    prompt_file: str
    model_name: str
    out_path: Path
    dl_path: Path


def run_pipeline(config: PipelineConfig) -> List[Path]:
    """
    Run summarization pipeline for one symbol across all filings.
    Returns a list of output paths (one per document).

    Args:
        config (PipelineConfig): Configuration parameters

    Returns:
        List[Path]: List of output file paths
    """

    symbol = config.symbol
    start_date = config.start_date
    end_date = config.end_date
    keyword = config.keyword
    prompt_file = config.prompt_file
    model_name = config.model_name
    out_path = config.out_path
    dl_path = config.dl_path

    downloader = SECFilingDownloader(
        os.getenv("EMAIL", "xxxxxx_xxxx@gmail.com"), dl_path)
    downloader.add_symbol(symbol)
    downloader.download_filings(start_date=start_date, end_date=end_date)

    preprocessor = PreProcessor(dl_path)
    html_paths = preprocessor.html_paths_for_symbol(symbol)

    if not html_paths:
        logger.warning(f"No filings found for {symbol}.")
        return []

    prompt = load_prompt(Path(prompt_file))
    llm = LocalT5Wrapper(model_name, max_new_tokens=1024)
    chain = SECFilingSummaryChain(prompt=prompt, llm=llm)

    output_files = []

    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY environment variable not set.")

    embedder = PineconeEmbedder(
        pinecone_api_key, initial_index=f"{symbol.lower()}-{keyword.lower()}-docs")

    for html_path in html_paths:
        chunks = preprocessor.transform_html(html_path)
        relevant_chunks = [
            chunk for chunk in chunks if keyword.lower() in chunk.page_content.lower()
        ]

        embedder.add_documents(relevant_chunks)

        if not relevant_chunks:
            logger.warning(
                f"No chunks matched keyword '{keyword}' in {html_path.name}.")
            continue

        logger.info(
            f"{len(relevant_chunks)} relevant chunks found in {html_path.name}. Summarizing...")

        summaries = []
        for chunk in tqdm(relevant_chunks,
                          desc=f"Summarizing {symbol}-{html_path.stem}"):
            try:
                result = chain.invoke({
                    "symbol": symbol,
                    "chunk": chunk.page_content,
                    "search_term": keyword
                })
                if not result["summary"]:
                    logger.warning(
                        f"Failed to parse output for {symbol}: {html_path.name}.")
                summaries.append(result.get(
                    "summary", {"n/a": "No summary produced."}))
            except Exception as e:
                logger.error(
                    f"Model invocation failed: {type(e).__name__}: {e}")
                traceback.print_exc()

        safe_keyword = keyword.lower().replace(" ", "_")
        doc_output_path = out_path / \
            f"{symbol.lower()}_{safe_keyword}_{html_path.stem}_summary.json"
        with open(doc_output_path, "w") as f:
            json.dump({"symbol": symbol, "document": html_path.name,
                      "summaries": summaries}, f, indent=2)

        logger.info(f"Summary written to {doc_output_path.resolve()}")
        output_files.append(doc_output_path)

    return output_files
