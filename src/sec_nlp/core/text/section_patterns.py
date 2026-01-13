# src/sec_nlp/core/text/section_patterns.py
"""Filing-specific section patterns for SEC documents."""

# Common proxy statement section patterns
PROXY_SECTION_PATTERNS = {
    "executive_compensation": r"executive\s+compensation|compensation\s+discussion|compensation\s+of\s+(named\s+)?executive",
    "director_compensation": r"director\s+compensation|compensation\s+of\s+directors",
    "say_on_pay": r"say[- ]on[- ]pay|advisory\s+vote\s+on\s+(executive\s+)?compensation",
    "board_composition": r"board\s+of\s+directors|election\s+of\s+directors|director\s+nominees",
    "audit_committee": r"audit\s+committee|independent\s+auditor",
    "related_party": r"related\s+party|related\s+person|certain\s+relationships",
    "shareholder_proposals": r"shareholder\s+proposal|stockholder\s+proposal",
    "beneficial_ownership": r"beneficial\s+ownership|security\s+ownership",
    "equity_compensation": r"equity\s+compensation\s+plan|stock\s+incentive",
}

# 13F has structured data; filter patterns focus on the information table
HOLDINGS_SECTION_PATTERNS = {
    "info_table": r"information\s+table|infotable|13f.*table",
    "cover_page": r"cover\s+page|form\s+13f",
    "summary": r"summary\s+page|report\s+summary",
    "signature": r"signature",
}

# Registration statement (S-1/S-3) section patterns
REGISTRATION_SECTION_PATTERNS = {
    "risk_factors": r"risk\s+factors?",
    "use_of_proceeds": r"use\s+of\s+proceeds",
    "business_description": r"business\s+description|our\s+business|business\s+overview",
}
