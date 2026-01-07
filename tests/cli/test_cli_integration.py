# tests/cli/test_cli_integration.py
"""Integration tests for CLI commands using sys.argv."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError


class TestExb10CLIIntegration:
    """Integration tests for exb_10 CLI command with sys.argv."""

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_basic_command(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test basic exb_10 command via CLI."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        # Simulate CLI arguments
        sys.argv = [
            "cli",
            "exb-10",
            "CAT",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
        ]

        CliApp.run(Root)

        # Verify pipeline was called
        assert mock_run_pipeline.called

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_multiple_symbols(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test exb_10 with multiple symbols."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "CAT",
            "DE",
            "PCAR",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
        ]

        CliApp.run(Root)

        # Verify the command was called - config is passed as self to _run_pipeline
        assert mock_run_pipeline.called
        # Get config from self (first arg)
        config = mock_run_pipeline.call_args[0][0]
        assert len(config.symbols) == 3
        assert "CAT" in config.symbols
        assert "DE" in config.symbols
        assert "PCAR" in config.symbols

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_no_llm_config(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """LLM config flags are ignored for Exhibit10 (no LLM support)."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        assert config.symbols == ["CAT", "DE", "GE", "CMI", "PCAR"]
        assert "llm" not in type(config).model_fields

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_nested_vdb_config(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test setting nested VDB configuration via CLI."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--vdb.embedding-model",
            "nomic-embed-text",
            "--vdb.qdrant-port",
            "6333",
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        assert config.symbols == ["CAT", "DE", "GE", "CMI", "PCAR"]
        assert config.vdb is not None
        assert config.vdb.embedding_model == "nomic-embed-text"
        assert config.vdb.qdrant_port == 6333

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_nested_search_config(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test setting nested Search configuration via CLI."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--search.limit",
            "20",
            "--search.score-threshold",
            "0.7",
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        assert config.symbols == ["CAT", "DE", "GE", "CMI", "PCAR"]
        assert config.search.limit == 20
        assert config.search.score_threshold == 0.7

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_search_queries_list(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test setting search queries list via CLI."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--search.queries",
            "exclusive contracts",
            "--search.queries",
            "aftermarket provisions",
            "--search.queries",
            "supplier pricing",
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        assert config.symbols == ["CAT", "DE", "GE", "CMI", "PCAR"]
        assert len(config.search.queries) == 3
        assert "exclusive contracts" in config.search.queries
        assert "aftermarket provisions" in config.search.queries

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_search_terms_list(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test setting search_terms list via CLI."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--search-terms",
            "custom1",
            "--search-terms",
            "custom2",
            "--search-terms",
            "custom3",
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        assert config.symbols == ["CAT", "DE", "GE", "CMI", "PCAR"]
        assert len(config.search_terms) == 3
        assert "custom1" in config.search_terms

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_exb10_all_nested_configs(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test setting all nested configurations simultaneously."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            # VDB config
            "--vdb.embedding-model",
            "nomic-embed-text",
            "--vdb.qdrant-port",
            "6333",
            # Search config
            "--search.queries",
            "test query 1",
            "--search.queries",
            "test query 2",
            "--search.limit",
            "15",
            "--search.score-threshold",
            "0.8",
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]

        # Verify base config
        assert config.symbols == ["CAT", "DE", "GE", "CMI", "PCAR"]

        # Verify VDB config
        assert config.vdb.embedding_model == "nomic-embed-text"
        assert config.vdb.qdrant_port == 6333

        # Verify Search config
        assert len(config.search.queries) == 2
        assert config.search.limit == 15
        assert config.search.score_threshold == 0.8


class TestAnalyzeCLIIntegration:
    """Integration tests for analyze CLI command."""

    @patch(
        "sec_nlp.cli.command.PipelineCommand._should_collect_metrics",
        return_value=False,
    )
    @patch(
        "sec_nlp.cli.command.PipelineCommand._should_validate",
        return_value=False,
    )
    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_analyze_cli_nested_llm_override(
        self,
        mock_run_pipeline: Mock,
        _mock_should_validate: Mock,
        _mock_should_collect_metrics: Mock,
        tmp_path: Path,
    ) -> None:
        """CLI inputs should overwrite LLM configuration safely."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "analyze",
            "AAPL",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--llm.model-name",
            "custom-llm",
            "--llm.temperature",
            "0.42",
        ]

        CliApp.run(Root)

        command_instance = mock_run_pipeline.call_args[0][0]
        assert command_instance.llm.model_name == "custom-llm"
        assert command_instance.llm.temperature == pytest.approx(0.42)

    def test_analyze_cli_rejects_malicious_run_id(self, tmp_path: Path) -> None:
        """Run ID should reject non-numeric/injection values."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "analyze",
            "AAPL",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--run-id",
            # NOTE: Intentional SQL injection string for testing validation.
            # Run ID should reject non-numeric and injection-style strings.
            "1; DROP TABLE runs;",
        ]

        with pytest.raises(ValidationError):
            CliApp.run(Root)


class TestWarrantyCLIIntegration:
    """Integration tests for warranty CLI command with sys.argv."""

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_warranty_basic_command(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test basic warranty command via CLI."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "warranty",
            "DE",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
        ]

        CliApp.run(Root)

        assert mock_run_pipeline.called

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_warranty_xbrl_only(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test that warranty pipeline uses XBRL-only mode."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "warranty",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        # Warranty pipeline is XBRL-only with no LLM
        assert config.xbrl_only is True


class TestCLIBooleanFlags:
    """Tests for boolean flag handling in CLI."""

    @patch("sec_nlp.cli.command.PipelineCommand._run_pipeline", autospec=True)
    def test_dry_run_flag(
        self,
        mock_run_pipeline: Mock,
        tmp_path: Path,
    ) -> None:
        """Test setting dry_run boolean flag."""
        from pydantic_settings import CliApp

        from sec_nlp.cli.commands import Root

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        sys.argv = [
            "cli",
            "exb-10",
            "--email",
            "test@example.com",
            "--dl-path",
            str(dl_path),
            "--out-path",
            str(out_path),
            "--dry-run",
        ]

        CliApp.run(Root)

        config = mock_run_pipeline.call_args[0][0]
        assert config.dry_run is True
