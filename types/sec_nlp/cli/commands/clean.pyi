from pathlib import Path
from typing import Literal

from _typeshed import Incomplete
from pydantic import BaseModel
from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    error as error,
    format_path as format_path,
    format_size as format_size,
    info_line as info_line,
    logger as logger,
    styled_header as styled_header,
    success as success,
    warning as warning,
)
from sec_nlp.core.infra.settings import PROJECT_ROOT as PROJECT_ROOT

class Clean(BaseModel):
    model_config: Incomplete
    target: CliPositionalArg[Literal["all", "downloads", "outputs", "logs"]]
    root: Path
    downloads_path: Path | None
    outputs_path: Path | None
    logs_path: Path | None
    dry_run: bool
    force: bool
    def cli_cmd(self) -> None: ...
