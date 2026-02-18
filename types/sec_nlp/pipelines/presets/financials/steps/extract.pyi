from sec_nlp.core.edgar.xbrl_facts import XbrlParser as XbrlParser

from ..models import FinancialFact as FinancialFact
from .download import DownloadedFiling as DownloadedFiling

CANONICAL_CONCEPT_ALIASES: dict[str, str]

def normalize_concept(tag: str, local_name: str) -> str | None: ...
def extract_financial_facts(
    *, symbol: str, filing: DownloadedFiling, parser: XbrlParser
) -> list[FinancialFact]: ...
