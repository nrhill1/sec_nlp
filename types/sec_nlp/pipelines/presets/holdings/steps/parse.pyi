from sec_nlp.core.edgar.holdings_parser import HoldingsParser as HoldingsParser

from ..models import HoldingPosition as HoldingPosition
from .download import DownloadedHoldingsFiling as DownloadedHoldingsFiling

def parse_holding_positions(
    *,
    symbol: str,
    filing: DownloadedHoldingsFiling,
    parser: HoldingsParser,
    cusip_filter: str | None = None,
) -> list[HoldingPosition]: ...
