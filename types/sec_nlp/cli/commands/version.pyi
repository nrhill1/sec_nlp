from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.core.infra.logger import (
    color_text as color_text,
    styled_header as styled_header,
)
from sec_nlp.core.infra.settings import PROJECT_ROOT as PROJECT_ROOT

class Version(BaseModel):
    model_config: Incomplete
    def cli_cmd(self) -> None: ...
