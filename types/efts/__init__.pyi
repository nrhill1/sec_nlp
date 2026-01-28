"""Manual stub for the `efts` native extension."""

from __future__ import annotations

from collections.abc import Sequence

from sec_nlp.types import JsonDict

def create_efts_client(
    email: str, company_name: str = ..., timeout: float = ...
) -> EFTSClient: ...

class EFTSClient:
    def __init__(
        self,
        user_agent: str | None = ...,
        timeout: float = ...,
        max_retries: int = ...,
        retry_delay: float = ...,
        rate_limit_delay: float = ...,
        base_url: str | None = ...,
        allowed_hosts: Sequence[str] | None = ...,
    ) -> None: ...
    def search(
        self,
        query: str,
        *,
        forms: Sequence[str] | None = ...,
        ciks: Sequence[str] | None = ...,
        tickers: Sequence[str] | None = ...,
        start_date: str | None = ...,
        end_date: str | None = ...,
        limit: int = ...,
        start: int = ...,
        sort_field: str = ...,
        sort_order: str = ...,
    ) -> JsonDict: ...
    def search_all(
        self,
        query: str,
        *,
        forms: Sequence[str] | None = ...,
        ciks: Sequence[str] | None = ...,
        tickers: Sequence[str] | None = ...,
        start_date: str | None = ...,
        end_date: str | None = ...,
        max_results: int = ...,
        sort_field: str = ...,
        sort_order: str = ...,
    ) -> list[JsonDict]: ...
    @property
    def base_url(self) -> str: ...
    @property
    def user_agent(self) -> str: ...
    @property
    def timeout(self) -> float: ...
    @property
    def max_retries(self) -> int: ...
    @property
    def retry_delay(self) -> float: ...
    @property
    def rate_limit_delay(self) -> float: ...
    @property
    def allowed_hosts(self) -> list[str]: ...
