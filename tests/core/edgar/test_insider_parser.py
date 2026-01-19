# tests/core/edgar/test_insider_parser.py
"""Tests for parsing Forms 3/4 ownership XML."""

from datetime import date
from pathlib import Path

from sec_nlp.core.edgar.insider_parser import parse_insider_documents


def _write_full_submission(path: Path, filed_date: date) -> None:
    lines = [
        "<SEC-HEADER>",
        f"FILED AS OF DATE: {filed_date.strftime('%Y%m%d')}",
        "</SEC-HEADER>",
    ]
    path.write_text("\n".join(lines))


def test_insider_parser_parses_form4_transactions(tmp_path: Path) -> None:
    accession_dir = (
        tmp_path / "sec-edgar-filings" / "ACME" / "4" / "0000000000-24-000001"
    )
    accession_dir.mkdir(parents=True, exist_ok=True)

    _write_full_submission(
        accession_dir / "full-submission.txt",
        filed_date=date(2024, 1, 31),
    )

    ownership_xml = """
    <ownershipDocument>
        <documentType>4</documentType>
        <periodOfReport>2024-01-10</periodOfReport>
        <issuer>
            <issuerCik>0000123456</issuerCik>
            <issuerName>ACME Corp</issuerName>
            <issuerTradingSymbol>ACME</issuerTradingSymbol>
        </issuer>
        <reportingOwner>
            <reportingOwnerId>
                <rptOwnerCik>0001111111</rptOwnerCik>
                <rptOwnerName>Jane Doe</rptOwnerName>
            </reportingOwnerId>
            <reportingOwnerRelationship>
                <isDirector>1</isDirector>
                <isOfficer>1</isOfficer>
                <isTenPercentOwner>0</isTenPercentOwner>
                <isOther>0</isOther>
                <officerTitle>CEO</officerTitle>
            </reportingOwnerRelationship>
        </reportingOwner>
        <nonDerivativeTable>
            <nonDerivativeTransaction>
                <securityTitle><value>Common Stock</value></securityTitle>
                <transactionDate><value>2024-01-10</value></transactionDate>
                <transactionCoding>
                    <transactionFormType>4</transactionFormType>
                    <transactionCode>P</transactionCode>
                </transactionCoding>
                <transactionAmounts>
                    <transactionShares><value>1000</value></transactionShares>
                    <transactionPricePerShare><value>12.34</value></transactionPricePerShare>
                    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
                </transactionAmounts>
                <postTransactionAmounts>
                    <sharesOwnedFollowingTransaction><value>5000</value></sharesOwnedFollowingTransaction>
                </postTransactionAmounts>
                <ownershipNature>
                    <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
                </ownershipNature>
                <footnoteId id="F1" />
            </nonDerivativeTransaction>
        </nonDerivativeTable>
        <derivativeTable>
            <derivativeTransaction>
                <securityTitle><value>Stock Option</value></securityTitle>
                <conversionOrExercisePrice><value>5.00</value></conversionOrExercisePrice>
                <transactionDate><value>2024-01-10</value></transactionDate>
                <transactionCoding>
                    <transactionFormType>4</transactionFormType>
                    <transactionCode>A</transactionCode>
                </transactionCoding>
                <transactionAmounts>
                    <transactionShares><value>200</value></transactionShares>
                    <transactionPricePerShare><value>0</value></transactionPricePerShare>
                    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
                </transactionAmounts>
                <postTransactionAmounts>
                    <sharesOwnedFollowingTransaction><value>200</value></sharesOwnedFollowingTransaction>
                </postTransactionAmounts>
                <ownershipNature>
                    <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
                    <natureOfOwnership><value>By Trust</value></natureOfOwnership>
                </ownershipNature>
            </derivativeTransaction>
        </derivativeTable>
        <footnotes>
            <footnote id="F1">Open market purchase</footnote>
        </footnotes>
    </ownershipDocument>
    """

    (accession_dir / "ownership.xml").write_text(ownership_xml.strip())

    docs = parse_insider_documents(accession_dir)

    assert len(docs) == 2

    base_doc = docs[0]
    base_meta = base_doc.metadata
    assert base_meta.get("document_type") == "4"
    assert base_meta.get("issuer_name") == "ACME Corp"
    assert base_meta.get("issuer_ticker") == "ACME"
    assert base_meta.get("reporting_owner_name") == "Jane Doe"
    assert base_meta.get("reporting_owner_cik") == "0001111111"
    assert base_meta.get("transaction_code") == "P"
    assert base_meta.get("transaction_type") == "open_market"
    assert base_meta.get("transaction_shares") == 1000
    assert base_meta.get("transaction_price") == 12.34
    assert base_meta.get("ownership_type") == "A"
    assert base_meta.get("direct_or_indirect") == "D"
    assert base_meta.get("shares_owned_following_transaction") == 5000
    assert base_meta.get("accession_number") == "0000000000-24-000001"
    assert base_meta.get("filed_date") == "2024-01-31"

    roles = base_meta.get("relationship_to_issuer")
    assert isinstance(roles, list)
    assert "director" in roles
    assert "officer" in roles

    footnotes = base_meta.get("footnotes")
    assert isinstance(footnotes, list)
    assert "Open market purchase" in footnotes

    derivative_doc = docs[1]
    derivative_meta = derivative_doc.metadata
    assert derivative_meta.get("security_type") == "derivative"
    assert derivative_meta.get("security_title") == "Stock Option"
    assert derivative_meta.get("transaction_type") == "grant"
    assert derivative_meta.get("conversion_or_exercise_price") == 5.0
    assert derivative_meta.get("direct_or_indirect") == "I"


def test_insider_parser_marks_form3_initial_holding(tmp_path: Path) -> None:
    accession_dir = (
        tmp_path / "sec-edgar-filings" / "ACME" / "3" / "0000000000-24-000002"
    )
    accession_dir.mkdir(parents=True, exist_ok=True)

    _write_full_submission(
        accession_dir / "full-submission.txt",
        filed_date=date(2024, 2, 1),
    )

    ownership_xml = """
    <ownershipDocument>
        <documentType>3</documentType>
        <issuer>
            <issuerCik>0000123456</issuerCik>
            <issuerName>ACME Corp</issuerName>
        </issuer>
        <reportingOwner>
            <reportingOwnerId>
                <rptOwnerCik>0002222222</rptOwnerCik>
                <rptOwnerName>Alex Smith</rptOwnerName>
            </reportingOwnerId>
        </reportingOwner>
        <nonDerivativeTable>
            <nonDerivativeHolding>
                <securityTitle><value>Common Stock</value></securityTitle>
                <postTransactionAmounts>
                    <sharesOwnedFollowingTransaction><value>2500</value></sharesOwnedFollowingTransaction>
                </postTransactionAmounts>
                <ownershipNature>
                    <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
                </ownershipNature>
            </nonDerivativeHolding>
        </nonDerivativeTable>
    </ownershipDocument>
    """

    (accession_dir / "ownership.xml").write_text(ownership_xml.strip())

    docs = parse_insider_documents(accession_dir)

    assert len(docs) == 1
    metadata = docs[0].metadata
    assert metadata.get("document_type") == "3"
    assert metadata.get("initial_holding") is True
    assert metadata.get("shares_owned_following_transaction") == 2500
