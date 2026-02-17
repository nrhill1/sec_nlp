"""Tests for DEF 14A proxy parsing helpers."""

from __future__ import annotations

from sec_nlp.core.edgar.proxy import parse_proxy

_FIXTURE_HTML = """
<html>
  <body>
    <h2>Summary Compensation Table (Fiscal Year 2025)</h2>
    <table>
      <tr>
        <th>Name and Principal Position</th>
        <th>Salary</th>
        <th>Bonus</th>
        <th>Stock Awards</th>
        <th>Option Awards</th>
        <th>Non-Equity Incentive Plan Compensation</th>
        <th>All Other Compensation</th>
        <th>Total</th>
      </tr>
      <tr>
        <td>Jane Doe\nChief Executive Officer</td>
        <td>$1,000,000</td>
        <td>$250,000</td>
        <td>$500,000</td>
        <td>$100,000</td>
        <td>$75,000</td>
        <td>$25,000</td>
        <td>$1,950,000</td>
      </tr>
    </table>

    <h2>Proposal Voting Results</h2>
    <table>
      <tr>
        <th>Proposal</th>
        <th>Description</th>
        <th>Proponent</th>
        <th>For</th>
        <th>Against</th>
        <th>Abstain</th>
      </tr>
      <tr>
        <td>Proposal 1</td>
        <td>Advisory Vote on Executive Compensation (Say-on-Pay)</td>
        <td>Management</td>
        <td>1,000,000</td>
        <td>200,000</td>
        <td>50,000</td>
      </tr>
      <tr>
        <td>Proposal 2</td>
        <td>Approve Equity Incentive Plan</td>
        <td>Management</td>
        <td>900,000</td>
        <td>300,000</td>
        <td>50,000</td>
      </tr>
    </table>

    <h2>Board of Directors</h2>
    <table>
      <tr>
        <th>Name</th>
        <th>Role</th>
        <th>Committees</th>
        <th>Independent</th>
        <th>Tenure (Years)</th>
      </tr>
      <tr>
        <td>Jane Doe</td>
        <td>Chair</td>
        <td>Compensation; Nominating</td>
        <td>Yes</td>
        <td>8</td>
      </tr>
      <tr>
        <td>John Smith</td>
        <td>Director</td>
        <td>Audit</td>
        <td>No</td>
        <td>3</td>
      </tr>
    </table>
  </body>
</html>
"""


def test_parse_proxy_extracts_compensation_proposals_board_and_say_on_pay() -> (
    None
):
    data = parse_proxy(
        _FIXTURE_HTML,
        accession_number="0000123456-26-000001",
        filing_date="2026-02-14",
    )

    assert data.accession_number == "0000123456-26-000001"
    assert data.filing_date == "2026-02-14"

    assert len(data.compensation) == 1
    comp = data.compensation[0]
    assert comp.name == "Jane Doe"
    assert comp.title == "Chief Executive Officer"
    assert comp.salary == 1_000_000.0
    assert comp.total == 1_950_000.0
    assert comp.fiscal_year == "2025"

    assert len(data.proposals) == 2
    say = data.proposals[0]
    assert say.proposal_number == 1
    assert "say-on-pay" in say.description.lower()
    assert say.vote_for == 1_000_000
    assert say.vote_against == 200_000
    assert say.vote_abstain == 50_000
    assert say.passed is True

    assert len(data.board) == 2
    assert data.board[0].name == "Jane Doe"
    assert data.board[0].committees == ["Compensation", "Nominating"]
    assert data.board[0].independent is True
    assert data.board[1].name == "John Smith"
    assert data.board[1].independent is False

    assert data.say_on_pay is not None
    assert round(data.say_on_pay.approval_percentage, 2) == 80.0


def test_parse_proxy_handles_empty_html() -> None:
    data = parse_proxy(
        "",
        accession_number="0000123456-26-000002",
        filing_date="2026-02-14",
    )

    assert data.compensation == []
    assert data.proposals == []
    assert data.board == []
    assert data.say_on_pay is None
