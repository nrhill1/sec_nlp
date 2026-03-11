# src/sec_nlp/cli/commands/qdrant.py
"""Qdrant collections management CLI commands."""

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import CliSubCommand
from qdrant_client import QdrantClient
from qdrant_client.http.models import CollectionInfo
from qdrant_client.models import Distance, VectorParams

from sec_nlp.core.infra.logger import (
    bullet_line,
    color_text,
    logger,
    styled_header,
)
from sec_nlp.pipelines.vector.client import (
    create_qdrant_client,
    format_qdrant_endpoint,
)
from sec_nlp.types import JsonValue


class QdrantBaseConfig(BaseModel):
    """Base configuration for Qdrant connection settings."""

    model_config = ConfigDict(defer_build=True, frozen=True, extra="forbid")

    qdrant_location: str | None = Field(
        default=None,
        description=(
            "Local Qdrant location (e.g., ':memory:' or storage path). "
            "When unset, qdrant_url or host/port is used."
        ),
    )
    qdrant_url: str | None = Field(
        default=None,
        description="Qdrant server URL (e.g., 'http://localhost:6333')",
    )
    qdrant_host: str = Field(
        default="localhost",
        description="Qdrant server host (used when qdrant_url is not set)",
    )
    qdrant_port: int = Field(
        default=6333,
        ge=1,
        le=65535,
        description="Qdrant HTTP port (used when qdrant_url is not set)",
    )
    qdrant_grpc_port: int = Field(
        default=6334,
        ge=1,
        le=65535,
        description="Qdrant gRPC port (used when qdrant_url is not set)",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key for authentication",
    )
    qdrant_https: bool = Field(
        default=False,
        description="Use HTTPS for host/port connections",
    )
    qdrant_prefer_grpc: bool = Field(
        default=False,
        description="Prefer gRPC over HTTP for Qdrant operations",
    )
    qdrant_timeout: int = Field(
        default=60,
        ge=1,
        description="Qdrant request timeout in seconds",
    )

    @field_validator("qdrant_location", mode="before")
    @classmethod
    def _normalize_qdrant_location(cls, value: str | None) -> str | None:
        """Treat blank strings and explicit null markers as unset."""
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "none",
            "null",
        }:
            return None
        return value

    def _setup_qdrant_client(self) -> QdrantClient:
        """Initialize a Qdrant client."""
        location = None if self.qdrant_url else self.qdrant_location
        return create_qdrant_client(
            location=location,
            url=self.qdrant_url,
            host=self.qdrant_host,
            port=self.qdrant_port,
            grpc_port=self.qdrant_grpc_port,
            api_key=self.qdrant_api_key,
            timeout=self.qdrant_timeout,
            prefer_grpc=self.qdrant_prefer_grpc,
            https=self.qdrant_https,
        )

    def _get_endpoint_display(self) -> str:
        """Get human-readable endpoint string."""
        location = None if self.qdrant_url else self.qdrant_location
        return format_qdrant_endpoint(
            location=location,
            url=self.qdrant_url,
            host=self.qdrant_host,
            port=self.qdrant_port,
            https=self.qdrant_https,
        )

    @staticmethod
    def _stored_vector_count_from_info(info: CollectionInfo) -> int:
        """Return the best available stored-vector count for a collection.

        Qdrant's ``indexed_vectors_count`` reflects optimizer/HNSW state rather
        than whether vectors are present at all. For the single-vector
        collections used in this project, ``points_count`` is the safest
        fallback when ``vectors_count`` is unset.
        """
        vectors = getattr(info, "vectors_count", None)
        if isinstance(vectors, int) and vectors > 0:
            return vectors
        points = getattr(info, "points_count", None)
        if isinstance(points, int):
            return points
        indexed = getattr(info, "indexed_vectors_count", None)
        if isinstance(indexed, int):
            return indexed
        return 0


class QdrantList(QdrantBaseConfig):
    """List all Qdrant collections."""

    verbose: bool = Field(
        default=False,
        description="Show detailed collection information",
    )

    def cli_cmd(self) -> None:
        """List all Qdrant collections."""
        logger.info(styled_header("Qdrant Collections"))
        logger.info(bullet_line("Endpoint", self._get_endpoint_display()))

        try:
            client = self._setup_qdrant_client()
            collections = client.get_collections().collections

            if not collections:
                logger.info(
                    color_text("\nNo collections found.", color="yellow")
                )
                return

            logger.info(f"\n{color_text('Collections:', color='cyan')}")
            for collection in sorted(collections, key=lambda c: c.name):
                if self.verbose:
                    info = client.get_collection(collection.name)
                    logger.info(
                        f"\n  {color_text(collection.name, color='green')}"
                    )
                    vectors_count = self._stored_vector_count_from_info(info)
                    points_count = info.points_count or 0
                    logger.info(f"    Stored vectors: {vectors_count:,}")
                    logger.info(f"    Points: {points_count:,}")
                    if info.config.params:
                        vector_params = info.config.params.vectors
                        if isinstance(vector_params, VectorParams):
                            logger.info(
                                f"    Vector size: {vector_params.size}"
                            )
                            logger.info(
                                f"    Distance: {vector_params.distance.name}"
                            )
                else:
                    logger.info(
                        f"  • {color_text(collection.name, color='green')}"
                    )

            logger.info(
                f"\n{color_text('Total:', color='cyan')} {len(collections)} collection{'s' if len(collections) != 1 else ''}"
            )

        except Exception as exc:
            logger.error(
                color_text(f"Failed to list collections: {exc}", color="red")
            )


class QdrantInfo(QdrantBaseConfig):
    """Show detailed information about a Qdrant collection."""

    collection_name: str = Field(
        description="Name of the collection to inspect",
    )

    def cli_cmd(self) -> None:
        """Show detailed information about a collection."""
        logger.info(styled_header(f"Collection: {self.collection_name}"))
        logger.info(bullet_line("Endpoint", self._get_endpoint_display()))

        try:
            client = self._setup_qdrant_client()

            if not client.collection_exists(self.collection_name):
                logger.error(
                    color_text(
                        f"\nCollection '{self.collection_name}' does not exist.",
                        color="red",
                    )
                )
                return

            info = client.get_collection(self.collection_name)

            logger.info(f"\n{color_text('Collection Details:', color='cyan')}")
            logger.info(
                f"  Name: {color_text(self.collection_name, color='green')}"
            )
            logger.info(f"  Status: {info.status}")
            vectors_count = self._stored_vector_count_from_info(info)
            points_count = info.points_count or 0
            indexed_count = info.indexed_vectors_count or 0
            logger.info(f"  Stored vectors: {vectors_count:,}")
            logger.info(f"  Points: {points_count:,}")
            logger.info(f"  Indexed vectors: {indexed_count:,}")

            if info.config.params:
                vector_params = info.config.params.vectors
                logger.info(
                    f"\n{color_text('Vector Configuration:', color='cyan')}"
                )
                if isinstance(vector_params, VectorParams):
                    logger.info(f"  Size: {vector_params.size}")
                    logger.info(f"  Distance: {vector_params.distance.name}")
                logger.info(
                    f"  On-disk payload: {info.config.params.on_disk_payload}"
                )
                if info.config.optimizer_config:
                    logger.info(f"\n{color_text('Optimizer:', color='cyan')}")
                    logger.info(
                        f"  Deleted threshold: {info.config.optimizer_config.deleted_threshold}"
                    )
                    logger.info(
                        f"  Indexing threshold: {info.config.optimizer_config.indexing_threshold}"
                    )

        except Exception as exc:
            logger.error(
                color_text(f"Failed to get collection info: {exc}", color="red")
            )


class QdrantDelete(QdrantBaseConfig):
    """Delete Qdrant collections."""

    collections: list[str] = Field(
        description="Names of collections to delete",
        json_schema_extra={"cli_args": {"nargs": "+"}},
    )

    force: bool = Field(
        default=False,
        description="Skip confirmation prompt",
        json_schema_extra={"cli_args": {"aliases": ["-f"]}},
    )

    def cli_cmd(self) -> None:
        """Delete specified Qdrant collections."""
        logger.info(styled_header("Delete Qdrant Collections"))
        logger.info(bullet_line("Endpoint", self._get_endpoint_display()))
        logger.info(
            bullet_line("Collections", ", ".join(sorted(self.collections)))
        )

        if not self.force:
            logger.warning(
                color_text(
                    "\nThis will permanently delete the collections listed above.",
                    color="yellow",
                )
            )
            logger.warning(
                color_text("Use --force to skip this prompt", color="dim")
            )
            try:
                response = input("Continue? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                logger.info("\nAborted.")
                return

            if response not in ("y", "yes"):
                logger.info("Aborted.")
                return

        try:
            client = self._setup_qdrant_client()

            logger.info("")
            for name in sorted(self.collections):
                try:
                    if client.collection_exists(name):
                        client.delete_collection(name)
                        logger.info(
                            color_text(
                                f"  ✓ Deleted collection: {name}",
                                color="green",
                            )
                        )
                    else:
                        logger.info(
                            color_text(
                                f"  - Collection not found: {name}",
                                color="dim",
                            )
                        )
                except Exception as exc:
                    logger.error(
                        color_text(
                            f"  ✗ Failed to delete collection {name}: {exc}",
                            color="red",
                        )
                    )

        except Exception as exc:
            logger.error(
                color_text(f"Failed to connect to Qdrant: {exc}", color="red")
            )


class QdrantCreate(QdrantBaseConfig):
    """Create a new Qdrant collection."""

    collection_name: str = Field(
        description="Name of the collection to create",
    )

    vector_size: int = Field(
        default=2048,
        ge=1,
        description="Dimension of embedding vectors",
    )

    distance: Literal["Cosine", "Euclid", "Dot"] = Field(
        default="Cosine",
        description="Distance metric for vector similarity",
    )

    on_disk_payload: bool = Field(
        default=False,
        description="Store payload on disk to save RAM",
    )

    replication_factor: int = Field(
        default=1,
        ge=1,
        description="Number of replicas for the collection",
    )

    write_consistency_factor: int = Field(
        default=1,
        ge=1,
        description="Write consistency factor",
    )

    recreate: bool = Field(
        default=False,
        description="Delete collection if it exists before creating",
    )

    def cli_cmd(self) -> None:
        """Create a new Qdrant collection."""
        logger.info(styled_header(f"Create Collection: {self.collection_name}"))
        logger.info(bullet_line("Endpoint", self._get_endpoint_display()))
        logger.info(bullet_line("Vector size", str(self.vector_size)))
        logger.info(bullet_line("Distance metric", self.distance))

        try:
            client = self._setup_qdrant_client()

            # Check if collection exists
            exists = client.collection_exists(self.collection_name)

            if exists and not self.recreate:
                logger.error(
                    color_text(
                        f"\nCollection '{self.collection_name}' already exists. "
                        "Use --recreate to delete and recreate it.",
                        color="red",
                    )
                )
                return

            if exists and self.recreate:
                logger.info(
                    color_text(
                        f"\nDeleting existing collection '{self.collection_name}'...",
                        color="yellow",
                    )
                )
                client.delete_collection(self.collection_name)

            # Create collection
            distance_mapping = {
                "Cosine": Distance.COSINE,
                "Euclid": Distance.EUCLID,
                "Dot": Distance.DOT,
            }

            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=distance_mapping[self.distance],
                ),
                on_disk_payload=self.on_disk_payload,
                replication_factor=self.replication_factor,
                write_consistency_factor=self.write_consistency_factor,
            )

            logger.info(
                color_text(
                    f"\n✓ Successfully created collection '{self.collection_name}'",
                    color="green",
                )
            )

        except Exception as exc:
            logger.error(
                color_text(f"Failed to create collection: {exc}", color="red")
            )


class QdrantSearch(QdrantBaseConfig):
    """Search for points in a Qdrant collection by payload."""

    collection_name: str = Field(
        description="Name of the collection to search",
    )

    query: str | None = Field(
        default=None,
        description="Search query text (searches in payload fields)",
    )

    limit: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Maximum number of results to return",
    )

    def cli_cmd(self) -> None:
        """Search for points in a collection."""
        logger.info(styled_header(f"Search Collection: {self.collection_name}"))
        logger.info(bullet_line("Endpoint", self._get_endpoint_display()))

        try:
            client = self._setup_qdrant_client()

            if not client.collection_exists(self.collection_name):
                logger.error(
                    color_text(
                        f"\nCollection '{self.collection_name}' does not exist.",
                        color="red",
                    )
                )
                return

            # Get collection info
            info = client.get_collection(self.collection_name)
            logger.info(bullet_line("Total points", f"{info.points_count:,}"))

            if self.query:
                logger.info(bullet_line("Query", self.query))

            # Scroll through points
            logger.info(f"\n{color_text('Points:', color='cyan')}")

            points, _ = client.scroll(
                collection_name=self.collection_name,
                limit=self.limit,
                with_payload=True,
                with_vectors=False,
            )

            if not points:
                logger.info(color_text("\nNo points found.", color="yellow"))
                return

            for idx, point in enumerate(points, 1):
                logger.info(f"\n{color_text(f'Point {idx}:', color='green')}")
                logger.info(f"  ID: {point.id}")

                if point.payload:
                    logger.info("  Payload:")
                    for key, value in sorted(point.payload.items()):
                        # Truncate long values
                        str_value = str(value)
                        if len(str_value) > 100:
                            str_value = str_value[:97] + "..."
                        logger.info(f"    {key}: {str_value}")

            shown = min(len(points), self.limit)
            total = info.points_count
            logger.info(
                f"\n{color_text('Showing:', color='cyan')} {shown} of {total:,} total point{'s' if total != 1 else ''}"
            )

        except Exception as exc:
            logger.error(
                color_text(f"Failed to search collection: {exc}", color="red")
            )


QDRANT_CONTAINER = "sec-nlp-qdrant"
_QDRANT_HTTP_PORT = 6333
_QDRANT_GRPC_PORT = 6334
_STARTUP_POLL_INTERVAL_SECONDS = 0.25


def _normalize_json_dict(raw: str | None) -> dict[str, JsonValue] | None:
    """Parse JSON text into a string-keyed dictionary."""
    if raw is None:
        return None
    payload = raw.strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        logger.debug("Failed to parse JSON payload: %s", payload)
        return None
    if not isinstance(parsed, dict):
        return None
    typed: dict[str, JsonValue] = {}
    for key, value in parsed.items():
        if isinstance(key, str):
            typed[key] = value
    return typed


class QdrantUp(BaseModel):
    """Start the Qdrant Docker container."""

    model_config = ConfigDict(defer_build=True, frozen=True, extra="forbid")

    detach: bool = Field(
        default=True,
        description="Run in background (detached mode)",
        json_schema_extra={"cli_args": {"aliases": ["-d"]}},
    )
    readiness_timeout: int = Field(
        default=20,
        ge=1,
        le=300,
        description="Seconds to wait for localhost:6333 to become reachable",
    )
    rootless: bool = Field(
        default=True,
        description=(
            "Attempt to run the Qdrant container as the current host user "
            "with no-new-privileges before falling back to the default "
            "container mode."
        ),
    )

    def _run_docker(
        self, args: list[str], *, check: bool, capture_output: bool
    ) -> subprocess.CompletedProcess[str]:
        """Execute a docker command."""
        return subprocess.run(
            args,
            capture_output=capture_output,
            text=True,
            check=check,
        )

    def _docker_capture(self, args: list[str]) -> str | None:
        """Run a docker command and return stdout on success."""
        result = self._run_docker(args, check=False, capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                logger.debug("Command failed (%s): %s", " ".join(args), stderr)
            return None
        output = result.stdout.strip()
        return output or None

    def _container_exists(self) -> bool:
        """Return True when the Qdrant container already exists."""
        result = self._run_docker(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={QDRANT_CONTAINER}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0 and QDRANT_CONTAINER in result.stdout

    def _start_existing_container(self) -> None:
        """Start an existing Qdrant container."""
        self._run_docker(
            ["docker", "start", QDRANT_CONTAINER],
            capture_output=False,
            check=True,
        )

    def _create_container(self) -> None:
        """Create and start a new Qdrant container."""
        rootful_command = self._build_rootful_create_command()
        if not self.rootless:
            self._run_docker(rootful_command, capture_output=False, check=True)
            return

        rootless_command = self._build_rootless_create_command()
        if rootless_command is None:
            logger.info(
                bullet_line(
                    "Container mode",
                    "default (rootless mode unsupported on this platform)",
                )
            )
            self._run_docker(rootful_command, capture_output=False, check=True)
            return

        try:
            self._run_docker(rootless_command, capture_output=False, check=True)
            logger.info(
                bullet_line(
                    "Container mode",
                    f"rootless ({self._rootless_user_spec()})",
                )
            )
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "Rootless Qdrant container start failed; retrying with default container user: %s",
                exc,
            )
            self._run_docker(rootful_command, capture_output=False, check=True)

    def _rootless_user_spec(self) -> str | None:
        """Return the current UID:GID string when supported."""
        if os.name == "nt":
            return None
        return f"{os.getuid()}:{os.getgid()}"

    def _build_rootful_create_command(self) -> list[str]:
        """Build the default `docker run` command for Qdrant startup."""
        cmd = [
            "docker",
            "run",
            "--name",
            QDRANT_CONTAINER,
            "-p",
            f"{_QDRANT_HTTP_PORT}:{_QDRANT_HTTP_PORT}",
            "-p",
            f"{_QDRANT_GRPC_PORT}:{_QDRANT_GRPC_PORT}",
            "-v",
            f"{Path.cwd()}/qdrant_storage:/qdrant/storage:z",
        ]
        if self.detach:
            cmd.append("-d")
        cmd.append("qdrant/qdrant")
        return cmd

    def _build_rootless_create_command(self) -> list[str] | None:
        """Build the current-user `docker run` command when supported."""
        user_spec = self._rootless_user_spec()
        if user_spec is None:
            return None
        cmd = self._build_rootful_create_command()
        cmd[2:2] = [
            "--user",
            user_spec,
            "--security-opt",
            "no-new-privileges:true",
        ]
        return cmd

    def _wait_for_localhost_http(self) -> bool:
        """Poll localhost until Qdrant HTTP port is reachable."""
        deadline = time.monotonic() + float(self.readiness_timeout)
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(
                    ("127.0.0.1", _QDRANT_HTTP_PORT), timeout=1.0
                ):
                    return True
            except OSError:
                time.sleep(_STARTUP_POLL_INTERVAL_SECONDS)
        return False

    def _docker_inspect_json(
        self, template: str
    ) -> dict[str, JsonValue] | None:
        """Read a JSON dictionary from `docker inspect --format`."""
        raw = self._docker_capture(
            ["docker", "inspect", QDRANT_CONTAINER, "--format", template]
        )
        return _normalize_json_dict(raw)

    def _summarize_port_bindings(
        self, port_map: dict[str, JsonValue] | None
    ) -> str:
        """Render a compact summary of published Qdrant ports."""
        if port_map is None:
            return "<unknown>"

        summaries: list[str] = []
        for container_port in ("6333/tcp", "6334/tcp"):
            bindings = port_map.get(container_port)
            host_bindings: list[str] = []
            if isinstance(bindings, list):
                for binding in bindings:
                    if not isinstance(binding, dict):
                        continue
                    host_ip = binding.get("HostIp")
                    host_port = binding.get("HostPort")
                    if isinstance(host_ip, str) and isinstance(host_port, str):
                        normalized_ip = host_ip or "0.0.0.0"
                        host_bindings.append(f"{normalized_ip}:{host_port}")

            if host_bindings:
                summaries.append(
                    f"{container_port} -> {', '.join(host_bindings)}"
                )
            else:
                summaries.append(f"{container_port} -> <not published>")

        return "; ".join(summaries)

    def _summarize_networks(
        self, network_map: dict[str, JsonValue] | None
    ) -> str:
        """Render attached Docker network names."""
        if network_map is None:
            return "<unknown>"
        if not network_map:
            return "<none>"
        return ", ".join(sorted(network_map.keys()))

    def _log_runtime_snapshot(self) -> None:
        """Log runtime Docker port bindings for quick debugging."""
        docker_port = self._docker_capture(["docker", "port", QDRANT_CONTAINER])
        if not docker_port:
            logger.info(bullet_line("Published ports", "<none>"))
            return

        one_line = "; ".join(
            line.strip() for line in docker_port.splitlines() if line.strip()
        )
        logger.info(bullet_line("Published ports", one_line))

    def _log_unreachable_diagnostics(self) -> None:
        """Log diagnostics explaining why localhost reachability can fail."""
        status = self._docker_capture(
            [
                "docker",
                "ps",
                "--filter",
                f"name={QDRANT_CONTAINER}",
                "--format",
                "{{.Status}}",
            ]
        )
        ports = self._docker_inspect_json("{{json .NetworkSettings.Ports}}")
        networks = self._docker_inspect_json(
            "{{json .NetworkSettings.Networks}}"
        )

        logger.error(
            color_text(
                "Qdrant started, but localhost:6333 is still unreachable.",
                color="red",
            )
        )
        if status:
            logger.error(bullet_line("Container status", status))
        logger.error(
            bullet_line("Published ports", self._summarize_port_bindings(ports))
        )
        logger.error(
            bullet_line("Attached networks", self._summarize_networks(networks))
        )

        if networks is not None and not networks:
            logger.error(
                color_text(
                    "Qdrant can listen on 0.0.0.0 inside the container while "
                    "still being unreachable from localhost when the runtime "
                    "network endpoint is missing.",
                    color="yellow",
                )
            )

        logger.error(
            color_text(
                "Try `sec-nlp qdrant restart`. If it persists, run "
                "`sec-nlp qdrant down --remove` then `sec-nlp qdrant up`.",
                color="yellow",
            )
        )

    def cli_cmd(self) -> None:
        """Start Qdrant container."""
        logger.info(color_text("Starting Qdrant...", color="cyan"))
        if self._container_exists():
            self._start_existing_container()
        else:
            self._create_container()

        if not self.detach:
            return

        if not self._wait_for_localhost_http():
            self._log_unreachable_diagnostics()
            raise RuntimeError(
                "Qdrant container is running, but localhost:6333 is unreachable."
            )

        logger.info(color_text("✓ Qdrant started", color="green"))
        logger.info(bullet_line("Endpoint", "http://localhost:6333"))
        self._log_runtime_snapshot()


class QdrantDown(BaseModel):
    """Stop the Qdrant Docker container."""

    model_config = ConfigDict(defer_build=True, frozen=True, extra="forbid")

    remove: bool = Field(
        default=False,
        description="Remove the container after stopping",
        json_schema_extra={"cli_args": {"aliases": ["-r", "--rm"]}},
    )

    def cli_cmd(self) -> None:
        """Stop Qdrant container."""
        logger.info(color_text("Stopping Qdrant...", color="cyan"))
        subprocess.run(["docker", "stop", QDRANT_CONTAINER], check=False)
        if self.remove:
            subprocess.run(["docker", "rm", QDRANT_CONTAINER], check=False)
            logger.info(
                color_text("✓ Qdrant stopped and removed", color="green")
            )
        else:
            logger.info(color_text("✓ Qdrant stopped", color="green"))


class QdrantRestart(BaseModel):
    """Restart the Qdrant Docker container."""

    model_config = ConfigDict(defer_build=True, frozen=True, extra="forbid")

    def cli_cmd(self) -> None:
        """Restart Qdrant container."""
        logger.info(color_text("Restarting Qdrant...", color="cyan"))
        subprocess.run(["docker", "restart", QDRANT_CONTAINER], check=True)
        logger.info(color_text("✓ Qdrant restarted", color="green"))


class QdrantLogs(BaseModel):
    """Show Qdrant Docker container logs."""

    model_config = ConfigDict(defer_build=True, frozen=True, extra="forbid")

    follow: bool = Field(
        default=True,
        description="Follow log output",
        json_schema_extra={"cli_args": {"aliases": ["-f"]}},
    )

    tail: int = Field(
        default=100,
        ge=1,
        description="Number of lines to show from the end",
        json_schema_extra={"cli_args": {"aliases": ["-n"]}},
    )

    def cli_cmd(self) -> None:
        """Show Qdrant logs."""
        cmd = ["docker", "logs"]
        if self.follow:
            cmd.append("-f")
        cmd.extend(["--tail", str(self.tail), QDRANT_CONTAINER])
        subprocess.run(cmd, check=False)


class Qdrant(BaseModel):
    """Manage Qdrant collections and Docker container."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
    )

    up: CliSubCommand[QdrantUp] = Field(
        description="Start Qdrant container",
        json_schema_extra={"cli_args": {"aliases": ["start"]}},
    )

    down: CliSubCommand[QdrantDown] = Field(
        description="Stop Qdrant container",
        json_schema_extra={"cli_args": {"aliases": ["stp", "stop"]}},
    )

    restart: CliSubCommand[QdrantRestart] = Field(
        description="Restart Qdrant container",
        json_schema_extra={"cli_args": {"aliases": ["rst"]}},
    )

    logs: CliSubCommand[QdrantLogs] = Field(
        description="Show Qdrant container logs",
        json_schema_extra={"cli_args": {"aliases": ["log"]}},
    )

    ls: CliSubCommand[QdrantList] = Field(
        description="List all collections",
        json_schema_extra={"cli_args": {"aliases": ["lst"]}},
    )

    info: CliSubCommand[QdrantInfo] = Field(
        description="Show detailed collection information",
        json_schema_extra={"cli_args": {"aliases": ["inf"]}},
    )

    delete: CliSubCommand[QdrantDelete] = Field(
        description="Delete collections",
        json_schema_extra={"cli_args": {"aliases": ["del", "rm"]}},
    )

    create: CliSubCommand[QdrantCreate] = Field(
        description="Create a new collection",
        json_schema_extra={"cli_args": {"aliases": ["new", "add"]}},
    )

    search: CliSubCommand[QdrantSearch] = Field(
        description="Search collection points by payload",
        json_schema_extra={"cli_args": {"aliases": ["qry", "src"]}},
    )

    def cli_cmd(self) -> None:
        """Execute the selected Qdrant subcommand."""
        from pydantic_settings import CliApp

        CliApp.run_subcommand(self)
