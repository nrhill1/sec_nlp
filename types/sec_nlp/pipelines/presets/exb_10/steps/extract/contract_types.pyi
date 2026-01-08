from enum import Enum

class ContractCategory(str, Enum):
    SUPPLY = "supply"
    CREDIT = "credit"
    EMPLOYMENT = "employment"
    LEASE = "lease"
    LICENSE = "license"
    SERVICE = "service"
    OTHER = "other"
    @classmethod
    def material_categories(cls) -> list[ContractCategory]: ...
    @classmethod
    def non_material_categories(cls) -> list[ContractCategory]: ...

CONTRACT_KEYWORDS: dict[ContractCategory, list[str]]

def get_keywords_for_categories(
    categories: list[ContractCategory],
) -> list[str]: ...
def detect_contract_category(text: str) -> ContractCategory: ...
def is_category_match(
    text: str, categories: list[ContractCategory], min_keywords: int = 2
) -> bool: ...
