"""Shared Qdrant client helpers for pipelines and CLI."""

from __future__ import annotations

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
) -> QdrantClient:
    """Create a Qdrant client using shared connection settings."""
    if location:
        return QdrantClient(
            location=location,
            timeout=timeout,
            prefer_grpc=False,
        )
    if url:
        return QdrantClient(
            url=url,
            api_key=api_key,
            timeout=timeout,
            prefer_grpc=prefer_grpc,
        )

    return QdrantClient(
        host=host,
        port=port,
        grpc_port=grpc_port,
        api_key=api_key,
        timeout=timeout,
        prefer_grpc=prefer_grpc,
        https=https,
    )


def format_qdrant_endpoint(
    *,
    location: str | None,
    url: str | None,
    host: str,
    port: int,
    https: bool,
) -> str:
    """Return a human-readable endpoint string for logs/CLI output."""
    if location:
        return location
    if url:
        return url
    protocol = "https" if https else "http"
    return f"{protocol}://{host}:{port}"
