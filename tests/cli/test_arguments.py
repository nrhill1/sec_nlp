# tests/cli/test_arguments.py
"""Tests for retained specialist command argument normalization."""


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

    def test_expands_forms_multi_value_flag(self) -> None:
        """Holdings forms flag should support space-separated values."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "holdings",
            "AAPL",
            "--forms",
            "13F-HR",
            "13F-HR/A",
            "--quarters",
            "2",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized == [
            "holdings",
            "AAPL",
            "--forms",
            "13F-HR",
            "--forms",
            "13F-HR/A",
            "--quarters",
            "2",
        ]

    def test_coerces_falsey_booleans(self) -> None:
        """Convert '--flag false' into '--no-flag' for boolean options."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "--search.export-results",
            "false",
            "--verbose",
            "0",
        ]
        normalized = _normalize_cli_args(argv)

        assert "--no-search.export-results" in normalized
        assert "--no-verbose" in normalized

    def test_coerces_falsey_chat_booleans(self) -> None:
        """Convert explicit false values for chat boolean flags into no-flags."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "chat",
            "--include-market-context",
            "false",
            "--include-news-context",
            "no",
            "--interactive",
            "0",
            "--prefetch-retrieve",
            "off",
            "--strict-citations",
            "false",
        ]
        normalized = _normalize_cli_args(argv)

        assert "--no-include-market-context" in normalized
        assert "--no-include-news-context" in normalized
        assert "--no-interactive" in normalized
        assert "--no-prefetch-retrieve" in normalized
        assert "--no-strict-citations" in normalized

    def test_quotes_numeric_symbol_positionals_for_symbol_commands(
        self,
    ) -> None:
        """Numeric CIK-like positional symbols should remain strings."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "holdings",
            "0000102909",
            "--email",
            "you@example.com",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized[0] == "holdings"
        assert normalized[1] == '"0000102909"'

    def test_quotes_numeric_symbol_positionals_for_news_command(self) -> None:
        """Numeric CIK-like values should stay quoted for news positional symbol."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "news",
            "0000102909",
            "--email",
            "you@example.com",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized[0] == "news"
        assert normalized[1] == '"0000102909"'

    def test_quotes_numeric_symbol_positionals_for_events_command(self) -> None:
        """Numeric CIK-like values should stay quoted for events positional symbol."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "events",
            "0000102909",
            "--email",
            "you@example.com",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized[0] == "events"
        assert normalized[1] == '"0000102909"'

    def test_quotes_numeric_symbol_positionals_for_retrieve_command(
        self,
    ) -> None:
        """Numeric CIK-like values should stay quoted for retrieve positional symbol."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "retrieve",
            "0000102909",
            "--email",
            "you@example.com",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized[0] == "retrieve"
        assert normalized[1] == '"0000102909"'

    def test_quotes_numeric_symbol_positionals_for_chat_command(self) -> None:
        """Numeric CIK-like values should stay quoted for chat positional symbol."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "chat",
            "0000102909",
            "--email",
            "you@example.com",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized[0] == "chat"
        assert normalized[1] == '"0000102909"'

    def test_leaves_numeric_positionals_for_non_symbol_commands(self) -> None:
        """Non-symbol commands should not rewrite numeric positionals."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "runs",
            "delete",
            "123",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized == argv

    def test_rewrites_queries_flag_for_analyze_command(self) -> None:
        """Analyze should map --queries to nested --search.queries."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "analyze",
            "AAPL",
            "--queries",
            "warranty",
        ]
        normalized = _normalize_cli_args(argv)

        assert "--search.queries" in normalized
        assert "--queries" not in normalized

    def test_does_not_rewrite_queries_flag_for_retrieve_command(self) -> None:
        """Retrieve should preserve --queries for RetrieveSettings parsing."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "retrieve",
            "AAPL",
            "--queries",
            "warranty",
        ]
        normalized = _normalize_cli_args(argv)

        assert "--queries" in normalized
        assert "--search.queries" not in normalized

    def test_expands_collections_multi_value_flag(self) -> None:
        """Chat collections flag should support space-separated values."""
        from sec_nlp.cli.__main__ import _normalize_cli_args

        argv = [
            "chat",
            "CDE",
            "--collections",
            "retrieve",
            "analyze",
            "--question",
            "test",
        ]
        normalized = _normalize_cli_args(argv)

        assert normalized == [
            "chat",
            "CDE",
            "--collections",
            "retrieve",
            "--collections",
            "analyze",
            "--question",
            "test",
        ]
