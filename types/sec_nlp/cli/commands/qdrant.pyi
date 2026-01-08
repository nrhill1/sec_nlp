from typing import Literal

from _typeshed import Incomplete
from pydantic import BaseModel
from pydantic_settings import CliSubCommand as CliSubCommand
from qdrant_client import QdrantClient as QdrantClient

from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    color_text as color_text,
    logger as logger,
    styled_header as styled_header,
)
from sec_nlp.pipelines.vector.client import (
    create_qdrant_client as create_qdrant_client,
    format_qdrant_endpoint as format_qdrant_endpoint,
)

class QdrantBaseConfig(BaseModel):
    model_config: Incomplete
    qdrant_location: str | None
    qdrant_url: str | None
    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int
    qdrant_api_key: str | None
    qdrant_https: bool
    qdrant_prefer_grpc: bool
    qdrant_timeout: int

class QdrantList(QdrantBaseConfig):
    verbose: bool
    def cli_cmd(self) -> None: ...

class QdrantInfo(QdrantBaseConfig):
    collection_name: str
    def cli_cmd(self) -> None: ...

class QdrantDelete(QdrantBaseConfig):
    collections: list[str]
    force: bool
    def cli_cmd(self) -> None: ...

class QdrantCreate(QdrantBaseConfig):
    collection_name: str
    vector_size: int
    distance: Literal["Cosine", "Euclid", "Dot"]
    on_disk_payload: bool
    replication_factor: int
    write_consistency_factor: int
    recreate: bool
    def cli_cmd(self) -> None: ...

class QdrantSearch(QdrantBaseConfig):
    collection_name: str
    query: str | None
    limit: int
    def cli_cmd(self) -> None: ...

QDRANT_CONTAINER: str

class QdrantUp(BaseModel):
    model_config: Incomplete
    detach: bool
    def cli_cmd(self) -> None: ...

class QdrantDown(BaseModel):
    model_config: Incomplete
    remove: bool
    def cli_cmd(self) -> None: ...

class QdrantRestart(BaseModel):
    model_config: Incomplete
    def cli_cmd(self) -> None: ...

class QdrantLogs(BaseModel):
    model_config: Incomplete
    follow: bool
    tail: int
    def cli_cmd(self) -> None: ...

class Qdrant(BaseModel):
    model_config: Incomplete
    up: CliSubCommand[QdrantUp]
    down: CliSubCommand[QdrantDown]
    restart: CliSubCommand[QdrantRestart]
    logs: CliSubCommand[QdrantLogs]
    ls: CliSubCommand[QdrantList]
    info: CliSubCommand[QdrantInfo]
    delete: CliSubCommand[QdrantDelete]
    create: CliSubCommand[QdrantCreate]
    search: CliSubCommand[QdrantSearch]
    def cli_cmd(self) -> None: ...
