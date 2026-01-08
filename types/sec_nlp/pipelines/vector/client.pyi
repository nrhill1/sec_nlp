from qdrant_client import QdrantClient

def create_qdrant_client(
    *,
    location: str | None,
    url: str | None,
    host: str,
    port: int,
    grpc_port: int,
    api_key: str | None,
    timeout: int,
    prefer_grpc: bool,
    https: bool,
) -> QdrantClient: ...
def format_qdrant_endpoint(
    *, location: str | None, url: str | None, host: str, port: int, https: bool
) -> str: ...
