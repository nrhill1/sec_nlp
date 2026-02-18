# tests/core/edgar/test_holdings_parser.py
"""Tests for parsing 13F holdings info tables."""

from datetime import date
from pathlib import Path

from sec_nlp.core.edgar.holdings_parser import parse_holdings_documents


def _write_full_submission(path: Path, filed_date: date) -> None:
    lines = [
        "<SEC-HEADER>",
        f"FILED AS OF DATE: {filed_date.strftime('%Y%m%d')}",
        "</SEC-HEADER>",
    ]
    path.write_text("\n".join(lines))


def test_holdings_parser_parses_info_table(tmp_path: Path) -> None:
    accession_dir = (
        tmp_path
        / "sec-edgar-filings"
        / "ACME"
        / "13F-HR"
        / "0000000000-24-000001"
    )
    accession_dir.mkdir(parents=True, exist_ok=True)

    _write_full_submission(
        accession_dir / "full-submission.txt",
        filed_date=date(2024, 1, 31),
    )

    info_table = """
    <informationTable>
        <infoTable>
            <nameOfIssuer>ACME Corp</nameOfIssuer>
            <titleOfClass>COM</titleOfClass>
            <cusip>000000000</cusip>
            <value>12345</value>
            <shrsOrPrnAmt>
                <sshPrnamt>1000</sshPrnamt>
                <sshPrnamtType>SH</sshPrnamtType>
            </shrsOrPrnAmt>
            <votingAuthority>
                <Sole>1000</Sole>
                <Shared>0</Shared>
                <None>0</None>
            </votingAuthority>
        </infoTable>
    </informationTable>
    """

    (accession_dir / "infotable.xml").write_text(info_table.strip())

    docs = parse_holdings_documents(accession_dir)

    assert len(docs) == 1
    doc = docs[0]
    metadata = doc.metadata
    assert metadata.get("issuer") == "ACME Corp"
    assert metadata.get("cusip") == "000000000"
    assert metadata.get("shares") == 1000
    assert metadata.get("accession_number") == "0000000000-24-000001"
    assert metadata.get("filed_date") == "2024-01-31"
    voting = metadata.get("voting_authority")
    assert isinstance(voting, dict)
    assert voting.get("sole") == 1000


def test_holdings_parser_parses_info_table_from_full_submission_fallback(
    tmp_path: Path,
) -> None:
    accession_dir = (
        tmp_path
        / "sec-edgar-filings"
        / "0000102909"
        / "13F-HR"
        / "0000102909-25-000353"
    )
    accession_dir.mkdir(parents=True, exist_ok=True)

    full_submission = """
<SEC-DOCUMENT>
<SEC-HEADER>
FILED AS OF DATE: 20251103
</SEC-HEADER>
<DOCUMENT>
<TYPE>INFORMATION TABLE</TYPE>
<TEXT>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>1 800 FLOWERS COM INC</nameOfIssuer>
    <titleOfClass>CL A</titleOfClass>
    <cusip>68243Q106</cusip>
    <value>10347</value>
    <shrsOrPrnAmt>
      <sshPrnamt>335100</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>335100</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
</informationTable>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""
    (accession_dir / "full-submission.txt").write_text(full_submission.strip())

    docs = parse_holdings_documents(accession_dir)

    assert len(docs) == 1
    metadata = docs[0].metadata
    assert metadata.get("issuer") == "1 800 FLOWERS COM INC"
    assert metadata.get("cusip") == "68243Q106"
    assert metadata.get("shares") == 335100
    assert metadata.get("value") == 10347
