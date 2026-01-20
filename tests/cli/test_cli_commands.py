# tests/cli/test_cli_commands.py
"""Comprehensive tests for CLI commands and nested model configuration."""

from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.exb import Exb
from sec_nlp.cli.commands.warranty import Warranty


class TestExbCommand:
    """Tests for Exb CLI command."""

    def test_exb_inherits_from_exhibit_config(self) -> None:
        """Test that Exb inherits from ExhibitConfig."""
        from sec_nlp.pipelines.presets.exb import ExhibitConfig

        assert issubclass(Exb, ExhibitConfig)

    def test_exb_basic_configuration(self, tmp_path: Path) -> None:
        """Test basic Exb configuration."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["CAT"],
        )

        assert cmd.email == "test@example.com"
        assert cmd.symbols == ["CAT"]
        assert cmd.dl_path == dl_path

    def test_exb_nested_vdb_config(self, tmp_path: Path) -> None:
        """Test configuring nested VectorConfig settings."""
        from sec_nlp.pipelines.vector import VectorConfig

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            vdb=VectorConfig(
                embedding_model="nomic-embed-text",
                qdrant_host="localhost",
                qdrant_port=6333,
            ),
        )

        assert cmd.vdb.embedding_model == "nomic-embed-text"
        assert cmd.vdb.qdrant_host == "localhost"
        assert cmd.vdb.qdrant_port == 6333

    def test_exb_nested_search_config(self, tmp_path: Path) -> None:
        """Test configuring nested SearchConfig settings."""
        from sec_nlp.pipelines.presets.exb import SearchConfig

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            search=SearchConfig(
                queries=["exclusive contracts", "aftermarket provisions"],
                limit=20,
                score_threshold=0.7,
            ),
        )

        assert len(cmd.search.queries) == 2
        assert "exclusive contracts" in cmd.search.queries
        assert cmd.search.limit == 20
        assert cmd.search.score_threshold == 0.7

    def test_exb_search_terms_configuration(self, tmp_path: Path) -> None:
        """Test configuring search terms list."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            search_terms=["custom1", "custom2", "custom3"],
        )

        assert len(cmd.search_terms) == 3
        assert "custom1" in cmd.search_terms

    @patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
    def test_exb_cli_cmd_execution(
        self, mock_run_pipeline: Mock, tmp_path: Path
    ) -> None:
        """Test that cli_cmd executes the pipeline."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        cmd.cli_cmd()

        # Verify _run_pipeline was called
        mock_run_pipeline.assert_called_once()

    @patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
    def test_exb_cli_cmd_with_outputs(
        self, mock_run_pipeline: Mock, tmp_path: Path
    ) -> None:
        """Test cli_cmd runs without error."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        cmd.cli_cmd()

        assert mock_run_pipeline.called


class TestWarrantyCommand:
    """Tests for Warranty CLI command."""

    def test_warranty_inherits_from_warranty_config(self) -> None:
        """Test that Warranty inherits from WarrantyConfig."""
        from sec_nlp.pipelines.presets.warranty import WarrantyConfig

        assert issubclass(Warranty, WarrantyConfig)

    def test_warranty_basic_configuration(self, tmp_path: Path) -> None:
        """Test basic Warranty configuration."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Warranty(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["DE"],
            limit=3,
        )

        assert cmd.email == "test@example.com"
        assert cmd.symbols == ["DE"]
        assert cmd.limit == 3

    def test_warranty_xbrl_only_mode(self, tmp_path: Path) -> None:
        """Test that warranty pipeline uses XBRL-only mode (no LLM)."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Warranty(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        # Warranty pipeline is XBRL-only with no LLM
        assert cmd.xbrl_only is True
        assert "llm" not in type(cmd).model_fields

    @patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
    def test_warranty_cli_cmd_execution(
        self, mock_run_pipeline: Mock, tmp_path: Path
    ) -> None:
        """Test that cli_cmd executes the warranty pipeline."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Warranty(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        cmd.cli_cmd()

        mock_run_pipeline.assert_called_once()


class TestNestedModelConfiguration:
    """Tests for nested model configuration across all commands."""

    def test_multiple_nested_configs_exb(self, tmp_path: Path) -> None:
        """Test configuring multiple nested models in Exb."""
        from sec_nlp.pipelines.presets.exb import SearchConfig
        from sec_nlp.pipelines.vector import VectorConfig

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["CAT", "DE"],
            vdb=VectorConfig(
                embedding_model="nomic-embed-text",
                qdrant_host="localhost",
            ),
            search=SearchConfig(
                queries=["test query"],
                limit=15,
            ),
        )

        # Verify all nested configs are set correctly
        assert cmd.vdb.embedding_model == "nomic-embed-text"
        assert cmd.search.limit == 15

    def test_list_field_configuration(self, tmp_path: Path) -> None:
        """Test configuring list fields (symbols, queries, search_terms)."""
        from sec_nlp.pipelines.presets.exb import SearchConfig

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["CAT", "DE", "PCAR"],
            search_terms=["exclusive", "custom_term"],
            search=SearchConfig(
                queries=["query1", "query2", "query3"],
            ),
        )

        # Verify all list fields are correct
        assert len(cmd.symbols) == 3
        assert "PCAR" in cmd.symbols

        assert len(cmd.search_terms) == 2
        assert "custom_term" in cmd.search_terms

        assert len(cmd.search.queries) == 3
        assert "query2" in cmd.search.queries

    def test_symbols_normalization_uppercase(self, tmp_path: Path) -> None:
        """Test that symbols are normalized to uppercase."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["cat", "de", "pcar"],
        )

        # All symbols should be uppercase
        assert cmd.symbols == ["CAT", "DE", "PCAR"]


class TestCommandErrorHandling:
    """Tests for error handling in CLI commands."""

    @patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
    def test_exb_handles_pipeline_error(
        self, mock_run_pipeline: Mock, tmp_path: Path
    ) -> None:
        """Test that cli_cmd handles pipeline errors gracefully."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Exb(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        # Should not raise, just log error
        cmd.cli_cmd()

        assert mock_run_pipeline.called

    @patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
    def test_warranty_handles_no_outputs(
        self, mock_run_pipeline: Mock, tmp_path: Path
    ) -> None:
        """Test that warranty command handles no outputs."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Warranty(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        # Should not raise, just log warning
        cmd.cli_cmd()

        assert mock_run_pipeline.called

    @patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
    def test_warranty_handles_pipeline_error(
        self, mock_run_pipeline: Mock, tmp_path: Path
    ) -> None:
        """Test that warranty command handles pipeline errors."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        cmd = Warranty(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        cmd.cli_cmd()

        assert mock_run_pipeline.called
