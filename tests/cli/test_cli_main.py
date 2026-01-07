# tests/cli/test_cli_main.py
"""Unit tests for sec_nlp.cli.__main__ module."""

from unittest.mock import Mock, patch

from sec_nlp.cli.__main__ import main


class TestCLIMain:
    """Tests for CLI main entry point."""

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_success(self, mock_cli_app: Mock) -> None:
        """Test that main returns 0 on success."""
        mock_cli_app.run.return_value = None

        result = main()

        assert result == 0
        assert mock_cli_app.run.called

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_keyboard_interrupt(self, mock_cli_app: Mock) -> None:
        """Test that main handles KeyboardInterrupt (Ctrl+C)."""
        mock_cli_app.run.side_effect = KeyboardInterrupt()

        result = main()

        assert result == 130  # SIGINT exit code

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_system_exit_zero(self, mock_cli_app: Mock) -> None:
        """Test that main handles SystemExit with code 0."""
        mock_cli_app.run.side_effect = SystemExit(0)

        result = main()

        assert result == 0

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_system_exit_nonzero(self, mock_cli_app: Mock) -> None:
        """Test that main handles SystemExit with non-zero code."""
        mock_cli_app.run.side_effect = SystemExit(2)

        result = main()

        assert result == 2

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_value_error(self, mock_cli_app: Mock) -> None:
        """Test that main handles ValueError."""
        mock_cli_app.run.side_effect = ValueError("Invalid input")

        result = main()

        assert result == 2  # ValueError exit code

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_file_not_found(self, mock_cli_app: Mock) -> None:
        """Test that main handles FileNotFoundError."""
        mock_cli_app.run.side_effect = FileNotFoundError("File not found")

        result = main()

        assert result == 3  # FileNotFoundError exit code

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_permission_error(self, mock_cli_app: Mock) -> None:
        """Test that main handles PermissionError."""
        mock_cli_app.run.side_effect = PermissionError("Permission denied")

        result = main()

        assert result == 4  # PermissionError exit code

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_handles_generic_exception(self, mock_cli_app: Mock) -> None:
        """Test that main handles generic exceptions."""
        mock_cli_app.run.side_effect = RuntimeError("Something went wrong")

        result = main()

        assert result == 1  # Generic error exit code

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_calls_cli_app_with_root(self, mock_cli_app: Mock) -> None:
        """Test that main calls CliApp.run with Root command."""
        from sec_nlp.cli.commands import Root

        main()

        mock_cli_app.run.assert_called_once_with(Root)

    @patch("sec_nlp.cli.__main__.CliApp")
    def test_main_system_exit_with_non_int_code(
        self, mock_cli_app: Mock
    ) -> None:
        """Test that main handles SystemExit with non-integer code."""
        mock_cli_app.run.side_effect = SystemExit("error message")

        result = main()

        assert result == 1

    @patch("sec_nlp.cli.__main__.CliApp")
    @patch("sec_nlp.cli.__main__.logger")
    def test_main_logs_keyboard_interrupt(
        self, mock_logger: Mock, mock_cli_app: Mock
    ) -> None:
        """Test that main logs KeyboardInterrupt."""
        mock_cli_app.run.side_effect = KeyboardInterrupt()

        main()

        mock_logger.warning.assert_called_once()
        assert "Interrupted" in str(mock_logger.warning.call_args)

    @patch("sec_nlp.cli.__main__.CliApp")
    @patch("sec_nlp.cli.__main__.logger")
    def test_main_logs_value_error(
        self, mock_logger: Mock, mock_cli_app: Mock
    ) -> None:
        """Test that main logs ValueError."""
        mock_cli_app.run.side_effect = ValueError("Invalid")

        main()

        mock_logger.error.assert_called_once()
        assert "Invalid" in str(mock_logger.error.call_args)

    @patch("sec_nlp.cli.__main__.CliApp")
    @patch("sec_nlp.cli.__main__.logger")
    def test_main_logs_file_not_found(
        self, mock_logger: Mock, mock_cli_app: Mock
    ) -> None:
        """Test that main logs FileNotFoundError."""
        mock_cli_app.run.side_effect = FileNotFoundError("Missing")

        main()

        mock_logger.error.assert_called_once()
        assert "File not found" in str(mock_logger.error.call_args)

    @patch("sec_nlp.cli.__main__.CliApp")
    @patch("sec_nlp.cli.__main__.logger")
    def test_main_logs_permission_error(
        self, mock_logger: Mock, mock_cli_app: Mock
    ) -> None:
        """Test that main logs PermissionError."""
        mock_cli_app.run.side_effect = PermissionError("Access denied")

        main()

        mock_logger.error.assert_called_once()
        assert "Permission denied" in str(mock_logger.error.call_args)

    @patch("sec_nlp.cli.__main__.CliApp")
    @patch("sec_nlp.cli.__main__.logger")
    def test_main_logs_exception_with_traceback(
        self, mock_logger: Mock, mock_cli_app: Mock
    ) -> None:
        """Test that main logs exceptions with traceback."""
        mock_cli_app.run.side_effect = RuntimeError("Unexpected")

        main()

        mock_logger.error.assert_called_once()
        mock_logger.debug.assert_called()


class TestNormalizeCliArgs:
    """Tests for CLI argument normalization helpers."""

    def test_expands_multi_value_flags(self) -> None:
        """Ensure list-like flags are expanded for argparse compatibility."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "--search-terms",
            "exclusive",
            "aftermarket",
            "--section-numbers",
            "10",
            "21",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized == [
            "--search-terms",
            "exclusive",
            "--search-terms",
            "aftermarket",
            "--section-numbers",
            "10",
            "--section-numbers",
            "21",
        ]

    def test_coerces_falsey_booleans(self) -> None:
        """Convert '--flag false' into '--no-flag' for boolean options."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "--search.export-results",
            "false",
            "--validate-config",
            "0",
        ]
        normalized = _normalize_cli_args(argv)

        assert "--no-search.export-results" in normalized
        assert "--no-validate-config" in normalized
