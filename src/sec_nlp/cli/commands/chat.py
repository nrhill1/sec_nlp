"""CLI command for RAG chat over indexed filings."""

from __future__ import annotations

import sys

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.core.infra.logger import color_text, logger
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.pipelines.presets.chat import (
    ChatHistoryTurn,
    ChatPipeline,
    ChatResult,
    ChatSettings,
)


class Chat(ChatSettings, BasePipelineCommand):
    """Interactive retrieval-augmented chat over indexed filings."""

    @classmethod
    def pipeline_class(cls) -> type[ChatPipeline]:
        return ChatPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description=(
            "Optional ticker symbol scope (e.g., CDE). "
            "Omit to search all indexed symbols."
        ),
    )

    def _get_header_subtitle(self) -> str:
        return "RAG Chat"

    def cli_cmd(self) -> None:
        question = (self.question or "").strip()
        if question:
            BasePipelineCommand.cli_cmd(self)
            return

        if not self.interactive:
            logger.error(
                color_text(
                    "No question provided. Use --question or enable interactive mode.",
                    color="red",
                )
            )
            return

        if not sys.stdin.isatty():
            logger.error(
                color_text(
                    "Interactive chat requires a TTY. Provide --question for non-interactive runs.",
                    color="red",
                )
            )
            return

        self._run_interactive_chat()

    def _run_interactive_chat(self) -> None:
        logger.info(
            color_text(
                "Starting chat session. Type '/exit' to finish.",
                color="cyan",
            )
        )
        if self.symbols:
            logger.info(
                color_text(
                    f"Symbol scope: {', '.join(self.symbols)}",
                    color="cyan",
                )
            )
        else:
            logger.info(color_text("Symbol scope: ALL", color="cyan"))

        history = list(self.chat_history)
        run_id = self.run_id

        while True:
            try:
                question = input("chat> ").strip()
            except (EOFError, KeyboardInterrupt):
                logger.info("\nEnding chat session")
                return

            if not question:
                continue
            if question.lower() in {"/exit", "exit", "quit", ":q"}:
                logger.info("Ending chat session")
                return

            cfg_data = self.model_dump(mode="python")
            cfg_data["question"] = question
            cfg_data["interactive"] = False
            cfg_data["run_id"] = run_id
            cfg_data["chat_history"] = [
                turn.model_dump(mode="python") for turn in history
            ]

            turn_config = ChatSettings.model_validate(cfg_data)
            result = ChatPipeline(config=turn_config).run()

            if not result.success:
                logger.error(
                    color_text(
                        f"Chat turn failed: {result.error or 'unknown error'}",
                        color="red",
                    )
                )
                continue

            answer = result.answer or "(no answer generated)"
            print(f"\nassistant> {answer}\n")

            if result.citation_ids:
                print(f"citations: {' '.join(result.citation_ids)}\n")

            history.append(ChatHistoryTurn(role="user", message=question))
            history.append(
                ChatHistoryTurn(
                    role="assistant",
                    message=answer,
                )
            )

            if result.outputs:
                last_output = result.outputs[-1]
                logger.info(
                    color_text(
                        f"Transcript updated: {last_output}",
                        color="dim",
                    )
                )

    def _handle_result(self, result: BasePipelineResult) -> None:
        if not isinstance(result, ChatResult):
            super()._handle_result(result)
            return

        if result.error is not None:
            logger.error(
                color_text(f"Chat failed: {result.error}", color="red")
            )
            return

        if not result.success:
            logger.error(color_text("Chat failed", color="red"))
            return

        question = (self.question or "").strip()
        if question:
            logger.info(color_text("Question:", color="cyan"))
            logger.info(question)

        if result.answer is not None:
            logger.info(color_text("Answer:", color="green"))
            logger.info(result.answer)
            if result.citation_ids:
                logger.info(
                    color_text(
                        f"Citations: {' '.join(result.citation_ids)}",
                        color="cyan",
                    )
                )

        if result.outputs:
            logger.info(color_text("Outputs:", color="cyan"))
            for output_path in result.outputs:
                logger.info(color_text(f"  → {output_path}", color="cyan"))
