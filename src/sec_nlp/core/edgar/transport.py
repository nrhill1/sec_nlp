# src/sec_nlp/core/edgar/transport.py
"""Share bounded HTTPX requests and one process-wide SEC request budget.

Async desktop jobs and synchronous specialist adapters reserve slots from the
same clock before every attempt. Failed requests never bypass pacing. Client
instances own their connections, while request policy remains centralized.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

import httpx
from pydantic import JsonValue, TypeAdapter

logger = logging.getLogger(__name__)
_JSON = TypeAdapter(JsonValue)
_LOCK = threading.Lock()
_next_request = 0.0
_INTERVAL = 0.2
_MAX_BYTES = 64 * 1024 * 1024


def _reserve_delay() -> float:
    """Reserve the next SEC request slot atomically across sync and async jobs."""
    global _next_request
    with _LOCK:
        current = time.monotonic()
        scheduled = max(current, _next_request)
        _next_request = scheduled + _INTERVAL
        return max(0.0, scheduled - current)


def _validate_url(url: str) -> None:
    """Require an HTTPS SEC endpoint without embedded credentials."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not (host == "sec.gov" or host.endswith(".sec.gov"))
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("SEC requests require an HTTPS sec.gov URL")


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Honor bounded Retry-After values or use exponential retry delays."""
    fallback = min(2.0**attempt, 30.0)
    if response is None:
        return fallback
    value = response.headers.get("Retry-After")
    if value is None:
        return fallback
    try:
        return min(60.0, max(float(value), 0.0))
    except ValueError:
        logger.debug(
            "Retry-After is not a duration; trying HTTP date", exc_info=True
        )
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return min(60.0, max((stamp - datetime.now(UTC)).total_seconds(), 0.0))
    except (ValueError, TypeError, OverflowError):
        logger.debug("Invalid Retry-After header", exc_info=True)
        return fallback


def _check_response(response: httpx.Response) -> bytes:
    """Validate status and bound the returned payload size."""
    response.raise_for_status()
    if len(response.content) > _MAX_BYTES:
        raise ValueError("SEC response exceeds the 64 MiB document limit")
    return response.content


class SecTransport:
    """Own asynchronous SEC connections under the shared application budget.

    The caller opens this client once for a refresh or interactive session and
    closes it through the asynchronous context manager. HTTP failures retain
    their status codes so the workspace can distinguish missing indexes.

    Attributes:
        user_agent: Declared application identity and contact information.
        retries: Number of retries after transient HTTP or transport failures.
    """

    def __init__(
        self, user_agent: str, *, timeout: float = 30.0, retries: int = 3
    ) -> None:
        """Construct a reusable HTTPX client with explicit timeouts and identity.

        Args:
            user_agent: Application identification sent to SEC.
            timeout: Timeout in seconds for each network operation.
            retries: Maximum retries after transient failures.
        """
        if not user_agent.strip() or timeout <= 0 or not 0 <= retries <= 10:
            raise ValueError(
                "Provide an identity, positive timeout, and 0–10 retries"
            )
        self.user_agent = user_agent
        self.retries = retries
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=timeout,
            follow_redirects=False,
        )

    async def __aenter__(self) -> Self:
        """Return this transport for use within an async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close all connections after the owning application operation."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client and release its connections."""
        await self._client.aclose()

    async def get_bytes(
        self, url: str, *, params: Mapping[str, str | int] | None = None
    ) -> bytes:
        """Retrieve bytes with shared pacing and bounded transient retries.

        Args:
            url: HTTPS endpoint on sec.gov or one of its subdomains.
            params: Optional query parameters.

        Returns:
            Successful response bytes, without writing to disk.

        Raises:
            ValueError: If the URL or payload size violates the transport contract.
            httpx.HTTPError: If a permanent error occurs or retries are exhausted.
        """
        _validate_url(url)
        for attempt in range(self.retries + 1):
            await asyncio.sleep(_reserve_delay())
            response: httpx.Response | None = None
            try:
                response = await self._client.get(url, params=params)
                if response.status_code != 429 and response.status_code < 500:
                    return _check_response(response)
                if attempt == self.retries:
                    return _check_response(response)
            except httpx.TransportError:
                logger.debug("Transient SEC network failure", exc_info=True)
                if attempt == self.retries:
                    raise
            await asyncio.sleep(_retry_delay(response, attempt))
        raise RuntimeError("Unreachable SEC request state")

    async def get_json(
        self, url: str, *, params: Mapping[str, str | int] | None = None
    ) -> JsonValue:
        """Retrieve and validate a JSON response through the shared transport.

        Args:
            url: HTTPS SEC endpoint.
            params: Optional query parameters.

        Returns:
            A JSON scalar, mapping, or list with recursively validated values.
        """
        return _JSON.validate_json(await self.get_bytes(url, params=params))


class _SyncSession:
    """Own a scoped event loop and reusable async clients on one worker thread."""

    def __init__(self) -> None:
        """Allocate a lazy worker without opening any network connections."""
        self._worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sec-http"
        )
        self._runner: asyncio.Runner | None = None
        self._clients: dict[tuple[str, float, int], SecTransport] = {}

    async def _fetch(
        self, url: str, user_agent: str, timeout: float, retries: int
    ) -> bytes:
        """Reuse an asynchronous transport for this session's request configuration."""
        key = (user_agent, timeout, retries)
        client = self._clients.get(key)
        if client is None:
            client = SecTransport(user_agent, timeout=timeout, retries=retries)
            self._clients[key] = client
        return await client.get_bytes(url)

    def _run(
        self, url: str, user_agent: str, timeout: float, retries: int
    ) -> bytes:
        """Run the single shared HTTP implementation on its owned event loop."""
        if self._runner is None:
            self._runner = asyncio.Runner()
        return self._runner.run(self._fetch(url, user_agent, timeout, retries))

    def fetch(
        self, url: str, user_agent: str, timeout: float, retries: int
    ) -> bytes:
        """Wait for a request on the scoped worker, even from an async caller."""
        return self._worker.submit(
            self._run, url, user_agent, timeout, retries
        ).result()

    async def _close_clients(self) -> None:
        """Close every connection before its owning event loop is destroyed."""
        await asyncio.gather(
            *(client.aclose() for client in self._clients.values())
        )
        self._clients.clear()

    def _close_loop(self) -> None:
        """Release clients and loop resources on their original worker thread."""
        if self._runner is not None:
            try:
                self._runner.run(self._close_clients())
            finally:
                self._runner.close()

    def close(self) -> None:
        """Finish cleanup and stop this explicit session's worker."""
        try:
            self._worker.submit(self._close_loop).result()
        finally:
            self._worker.shutdown(wait=True, cancel_futures=True)


_SYNC_SESSION: ContextVar[_SyncSession | None] = ContextVar(
    "sec_sync_session", default=None
)


@contextmanager
def sec_sync_session() -> Iterator[None]:
    """Reuse asynchronous SEC connections throughout explicit specialist work.

    Wrap a synchronous research action in this context. Nested scopes reuse the
    active session, and each outer scope closes its worker, event loop, and
    connections. All requests still execute ``SecTransport.get_bytes``; there
    is no separate synchronous HTTP implementation or retry policy.

    The synchronous adapter blocks its caller. Async applications should await
    ``SecTransport`` directly or run specialist work outside their event loop.
    """
    if _SYNC_SESSION.get() is not None:
        yield
        return
    session = _SyncSession()
    token = _SYNC_SESSION.set(session)
    try:
        yield
    finally:
        _SYNC_SESSION.reset(token)
        session.close()


def fetch_sec_bytes(
    url: str, user_agent: str, *, timeout: float = 30.0, retries: int = 3
) -> bytes:
    """Bridge synchronous specialist calls to the sole async SEC HTTP client.

    Args:
        url: HTTPS SEC endpoint.
        user_agent: Declared application identity.
        timeout: Per-operation network timeout in seconds.
        retries: Maximum number of transient retries.

    Returns:
        Successful bytes using the active scoped session or a temporary scope.

    Raises:
        ValueError: If request arguments or payload size are invalid.
        httpx.HTTPError: If retrieval fails after bounded retries.
    """
    _validate_url(url)
    with sec_sync_session():
        session = _SYNC_SESSION.get()
        if session is None:
            raise RuntimeError("SEC synchronous session did not initialize")
        return session.fetch(url, user_agent, timeout, retries)


def fetch_sec_json(url: str, user_agent: str) -> JsonValue:
    """Return validated JSON for synchronous SEC metadata consumers.

    Args:
        url: HTTPS SEC endpoint.
        user_agent: Application identification.

    Returns:
        Validated JSON data; malformed responses raise a validation error.
    """
    return _JSON.validate_json(fetch_sec_bytes(url, user_agent))
