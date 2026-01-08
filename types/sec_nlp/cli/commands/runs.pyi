from typing import Literal

from _typeshed import Incomplete
from pydantic import BaseModel
from pydantic_settings import CliSubCommand as CliSubCommand

from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    color_text as color_text,
    logger as logger,
    styled_header as styled_header,
)
from sec_nlp.pipelines.observability.run_registry import (
    get_registry as get_registry,
)

class RunsLs(BaseModel):
    model_config: Incomplete
    pipeline: str | None
    status: Literal["running", "completed", "failed"] | None
    limit: int
    def cli_cmd(self) -> None: ...

class RunsInfo(BaseModel):
    model_config: Incomplete
    run: str
    def cli_cmd(self) -> None: ...

class RunsDelete(BaseModel):
    model_config: Incomplete
    run: str
    force: bool
    def cli_cmd(self) -> None: ...

class RunsPrune(BaseModel):
    model_config: Incomplete
    older_than: int | None
    keep_last: int | None
    pipeline: str | None
    force: bool
    def cli_cmd(self) -> None: ...

class RunsStats(BaseModel):
    model_config: Incomplete
    def cli_cmd(self) -> None: ...

class Runs(BaseModel):
    model_config: Incomplete
    ls: CliSubCommand[RunsLs]
    info: CliSubCommand[RunsInfo]
    delete: CliSubCommand[RunsDelete]
    prune: CliSubCommand[RunsPrune]
    stats: CliSubCommand[RunsStats]
    def cli_cmd(self) -> None: ...
