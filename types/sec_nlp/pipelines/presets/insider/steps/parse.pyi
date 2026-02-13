from sec_nlp.core.edgar.insider_parser import InsiderParser as InsiderParser

from ..models import InsiderTransaction as InsiderTransaction
from .download import DownloadedInsiderFiling as DownloadedInsiderFiling

def parse_insider_transactions(
    *,
    symbol: str,
    filing: DownloadedInsiderFiling,
    parser: InsiderParser,
) -> list[InsiderTransaction]: ...
