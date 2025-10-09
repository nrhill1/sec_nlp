# src/cli/__main__.py
from __future__ import annotations

import argparse
import logging
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from importlib.resources import files

from dotenv import load_dotenv

from sec_nlp import _default_prompt_path
from sec_nlp.pipelines import Pipeline
from sec_nlp.types import FilingMode
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def setup_logging(verbose: bool) -> None:
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled (DEBUG).")


def setup_folders(fresh: bool) -> tuple[Path, Path]:
    here = Path(__file__).resolve()
    data_folder = here.parent.parent / "data"
    data_folder.mkdir(parents=True, exist_ok=True)

    output_folder = data_folder / "output"
    downloads_folder = data_folder / "downloads"

    if fresh:
        for folder in (output_folder, downloads_folder):
            if folder.exists() and any(folder.iterdir()):
                shutil.rmtree(folder)
                logger.info("Cleared existing folder: %s", folder)

    output_folder.mkdir(parents=True, exist_ok=True)
    downloads_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Output folder: %s", output_folder.resolve())
    logger.info("Downloads folder: %s", downloads_folder.resolve())
    return output_folder, downloads_folder


def cleanup_downloads(downloads_folder: Path) -> None:
    try:
        shutil.rmtree(downloads_folder / "sec-edgar-filings")
        logger.info("Cleaned up downloaded SEC files.")
    except Exception as e:
        logger.error("Cleanup failed: %s: %s", type(e).__name__, e)


def parse_args() -> argparse.Namespace:
    today = datetime.today()
    one_year_ago = today - timedelta(days=365)

    p = argparse.ArgumentParser(description="Run SEC NLP pipeline over filings.")
    p.add_argument(
        "symbols", nargs="*", default=["AAPL"], help="Ticker symbols (default: AAPL)."
    )
    p.add_argument(
        "--mode",
        choices=["annual", "quarterly"],
        default="annual",
        help="10-K or 10-Q mode.",
    )
    p.add_argument(
        "--start_date",
        default=one_year_ago.strftime("%Y-%m-%d"),
        help="Start date (YYYY-MM-DD).",
    )
    p.add_argument(
        "--end_date", default=today.strftime("%Y-%m-%d"), help="End date (YYYY-MM-DD)."
    )
    p.add_argument(
        "--keyword", default="revenue", help="Keyword to filter filing chunks."
    )
    p.add_argument(
        "--prompt_file",
        default=_default_prompt_path(),
        help="Prompt YAML path or packaged file.",
    )
    p.add_argument(
        "--model_name", default="google/flan-t5-base", help="LLM model name."
    )
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--max-new-tokens", type=int, default=1024)
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--no-require-json", action="store_true")
    p.add_argument("--fresh", action="store_true", help="Clear old output/downloads.")
    p.add_argument("--no-cleanup", action="store_true", help="Keep downloaded files.")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    p.add_argument(
        "--dry-run", action="store_true", help="Skip Pinecone provisioning and upserts."
    )
    return p.parse_args()


def main() -> None:
    load_dotenv()

    args = parse_args()
    setup_logging(args.verbose)
    output_folder, downloads_folder = setup_folders(fresh=args.fresh)

    start: date = date.fromisoformat(args.start_date)
    end: date = date.fromisoformat(args.end_date)
    mode: FilingMode = FilingMode(args.mode)
    symbols: list[str] = [str(s).upper() for s in args.symbols]

    prompt_path = Path(args.prompt_file) if Path(
        args.prompt_file).is_file() else _default_prompt_path()

    pipe = Pipeline(
        mode=mode,
        start_date=start,
        end_date=end,
        keyword=args.keyword,
        prompt_file=prompt_path,
        model_name=args.model_name,
        out_path=output_folder,
        dl_path=downloads_folder,
        limit=args.limit,
        max_new_tokens=args.max_new_tokens,
        require_json=not args.no_require_json,
        max_retries=args.max_retries,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    start_time = time.perf_counter()
    logger.info("Starting pipeline for symbols: %s", ", ".join(symbols))

    results = pipe.run_all(symbols)

    elapsed = time.perf_counter() - start_time
    logger.info("Pipeline complete in %.2f seconds.", elapsed)

    for sym, paths in results.items():
        logger.info("[%s] wrote %d file(s).", sym, len(paths))

    if not args.no_cleanup:
        cleanup_downloads(downloads_folder)
    else:
        logger.info(
            "--no-cleanup set; leaving downloads at %s", downloads_folder.resolve()
        )


if __name__ == "__main__":
    main()
