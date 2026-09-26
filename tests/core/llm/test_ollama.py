# tests/core/llm/test_ollama.py
"""Unit tests for sec_nlp.core.llm.ollama module."""

from unittest.mock import MagicMock, patch

from sec_nlp.core.llm.ollama import build_ollama_llm


class TestBuildOllamaLLM:
    """Tests for build_ollama_llm function."""

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_with_defaults(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test building Ollama LLM with default parameters."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        llm = build_ollama_llm("llama3.2")

        # Verify OllamaLLM was called with correct parameters
        mock_ollama_class.assert_called_once_with(
            model="llama3.2",
            base_url="http://localhost:11434",
            temperature=0.1,
            top_k=10,
            top_p=0.5,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_with_custom_base_url(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test building Ollama LLM with custom base URL."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        custom_url = "http://192.168.1.100:11434"
        llm = build_ollama_llm("mistral", base_url=custom_url)

        mock_ollama_class.assert_called_once_with(
            model="mistral",
            base_url=custom_url,
            temperature=0.1,
            top_k=10,
            top_p=0.5,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_with_custom_temperature(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test building Ollama LLM with custom temperature."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        llm = build_ollama_llm("llama3.2", temperature=0.7)

        mock_ollama_class.assert_called_once_with(
            model="llama3.2",
            base_url="http://localhost:11434",
            temperature=0.7,
            top_k=10,
            top_p=0.5,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_with_sec_nlp_env_base_url(
        self,
        mock_ollama_class: MagicMock,
        monkeypatch,
    ) -> None:
        """Test that SEC_NLP_OLLAMA_BASE_URL environment variable is used."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        env_url = "http://ollama.example.com:8080"
        monkeypatch.setenv("SEC_NLP_OLLAMA_BASE_URL", env_url)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        llm = build_ollama_llm("llama3.2")

        mock_ollama_class.assert_called_once_with(
            model="llama3.2",
            base_url=env_url,
            temperature=0.1,
            top_k=10,
            top_p=0.5,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_with_legacy_env_base_url(
        self,
        mock_ollama_class: MagicMock,
        monkeypatch,
    ) -> None:
        """Test that legacy OLLAMA_BASE_URL is still supported."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        env_url = "http://legacy-ollama.example.com:11434"
        monkeypatch.delenv("SEC_NLP_OLLAMA_BASE_URL", raising=False)
        monkeypatch.setenv("OLLAMA_BASE_URL", env_url)

        llm = build_ollama_llm("llama3.2")

        mock_ollama_class.assert_called_once_with(
            model="llama3.2",
            base_url=env_url,
            temperature=0.1,
            top_k=10,
            top_p=0.5,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_explicit_url_overrides_env(
        self,
        mock_ollama_class: MagicMock,
        monkeypatch,
    ) -> None:
        """Test that explicit base_url overrides environment variable."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        monkeypatch.setenv("SEC_NLP_OLLAMA_BASE_URL", "http://env-server:11434")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://legacy-server:11434")
        explicit_url = "http://explicit-server:11434"

        llm = build_ollama_llm("llama3.2", base_url=explicit_url)

        mock_ollama_class.assert_called_once_with(
            model="llama3.2",
            base_url=explicit_url,
            temperature=0.1,
            top_k=10,
            top_p=0.5,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_with_additional_kwargs(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test passing additional kwargs to OllamaLLM."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        llm = build_ollama_llm(
            "llama3.2",
            num_ctx=4096,
            top_p=0.9,
            repeat_penalty=1.1,
        )

        mock_ollama_class.assert_called_once_with(
            model="llama3.2",
            base_url="http://localhost:11434",
            temperature=0.1,
            top_k=10,
            top_p=0.9,
            num_ctx=4096,
            repeat_penalty=1.1,
            keep_alive=-1,
            num_gpu=-1,
        )
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    @patch("sec_nlp.core.llm.ollama.logger")
    def test_build_ollama_llm_logs_creation(
        self, mock_logger: MagicMock, mock_ollama_class: MagicMock
    ) -> None:
        """Test that LLM creation is logged."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        _llm = build_ollama_llm("llama3.2")

        # Verify info log was called
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "Created Ollama LLM" in call_args[0]
        assert "llama3.2" in call_args

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_different_models(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test building LLMs with different model names."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        models = [
            "llama3.2",
            "llama3.2:70b",
            "mistral",
            "codellama",
            "phi3",
        ]

        for model in models:
            mock_ollama_class.reset_mock()
            build_ollama_llm(model)

            args = mock_ollama_class.call_args[1]
            assert args["model"] == model
            assert args["top_k"] == 10
            assert args["top_p"] == 0.5

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_returns_runnable(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test that return value has expected LLM interface."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        llm = build_ollama_llm("llama3.2")

        # The returned object should be the mock instance
        assert llm == mock_instance

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_zero_temperature(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test building LLM with zero temperature for deterministic output."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        _llm = build_ollama_llm("llama3.2", temperature=0.0)

        mock_ollama_class.assert_called_once()
        args = mock_ollama_class.call_args[1]
        assert args["temperature"] == 0.0
        assert args["top_k"] == 10
        assert args["top_p"] == 0.5

    @patch("langchain_ollama.llms.OllamaLLM")
    def test_build_ollama_llm_high_temperature(
        self, mock_ollama_class: MagicMock
    ) -> None:
        """Test building LLM with high temperature for creative output."""
        mock_instance = MagicMock()
        mock_ollama_class.return_value = mock_instance

        _llm = build_ollama_llm("llama3.2", temperature=1.5)

        mock_ollama_class.assert_called_once()
        args = mock_ollama_class.call_args[1]
        assert args["temperature"] == 1.5
        assert args["top_k"] == 10
        assert args["top_p"] == 0.5
