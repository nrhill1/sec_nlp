# chains/sec.py
import json
from typing import Any, Dict, List

from langchain.chains.base import Chain
from langchain_core.prompts.base import BasePromptTemplate


class SECFilingSummaryChain(Chain):
    """
    Summarizes chunks of SEC filing text using a local Hugging Face model
    and a LangChain-compatible prompt template. Returns a JSON dict of summaries.

    Args:
        prompt (BasePromptTemplate): Langchain prompt template for summarization.
        llm (Any): Model instance with an `invoke` method.
    """

    prompt: BasePromptTemplate
    llm: Any

    @property
    def input_keys(self) -> List[str]:
        return ["symbol", "chunk", "search_term"]

    @property
    def output_keys(self) -> List[str]:
        return ["symbol", "summary"]

    def _summarize_chunk(self, chunk: str, symbol: str,
                         search_term: str) -> Dict[str, Any]:
        """
        Runs summarization over text chunk and returns parsed summary.

        Args:
            chunk (str): Text chunk to summarize
            symbol (str): Stock symbol for context
            search_term (str): Keyword used to filter chunks

        Returns:
            Dict[str, Any]: Parsed JSON summary with error handling
        """
        prompt_input = self.prompt.format_prompt(
            chunk=chunk, symbol=symbol, search_term=search_term).to_string()
        raw = self.llm.invoke(prompt_input)

        try:
            summary = json.loads(raw)
        except json.decoder.JSONDecodeError:
            summary = {
                "summary": None,
                "error": "JSON parse failed",
                "raw_output": raw
            }
        return summary

    def _call(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main chain call method.

        Args:
            inputs (Dict[str, Any]): Input dictionary with keys:
                - symbol (str): Stock symbol
                - chunk (str): Text chunk to summarize
                - search_term (str): Keyword used to filter chunks

        Raises:
            ValueError: If required inputs are missing or invalid

        Returns:
            Dict[str, Any]:  Output dictionary with keys:
                - symbol (str): Stock symbol
                - summary (Dict[str, Any]): Parsed JSON summary or error details
        """
        symbol = inputs.get("symbol")
        chunk = inputs.get("chunk")
        search_term = inputs.get("search_term")

        if not symbol or not chunk or not search_term:
            raise ValueError(
                "Inputs must include 'symbol', 'chunk', and 'search_term'.")

        output = self._summarize_chunk(chunk, symbol, search_term)

        return {
            "symbol": symbol,
            "output": output
        }
