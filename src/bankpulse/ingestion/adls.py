"""
Async ADLS Gen2 uploader for the bronze layer.

Uses the official azure-storage-file-datalake SDK (sync under the hood —
Azure's async SDK story for Data Lake is patchy) with a thread-pool bridge
so the ingestion script can parallelise uploads via asyncio.

Retries are handled by `tenacity` with exponential backoff + jitter.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from bankpulse.utils.logging import get_logger

log = get_logger(__name__)


class BronzeUploader:
    """Uploads local Parquet files to the bronze container, partitioned paths."""

    def __init__(
        self,
        storage_account_name: str,
        container: str = "bronze",
        max_concurrent: int = 8,
    ) -> None:
        account_url = f"https://{storage_account_name}.dfs.core.windows.net"
        self._service = DataLakeServiceClient(
            account_url=account_url,
            credential=DefaultAzureCredential(),
        )
        self._fs = self._service.get_file_system_client(container)
        self._sem = asyncio.Semaphore(max_concurrent)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_random_exponential(multiplier=1, max=20),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _upload_sync(self, local_path: Path, remote_path: str) -> int:
        """Synchronous upload with retry. Returns bytes uploaded."""
        data = local_path.read_bytes()
        file_client = self._fs.get_file_client(remote_path)
        file_client.upload_data(data, overwrite=True)
        return len(data)

    async def upload_one(self, local_path: Path, remote_path: str) -> int:
        """Offload the sync SDK call to a thread; gated by semaphore."""
        async with self._sem:
            log.info("upload.start", remote=remote_path, size=local_path.stat().st_size)
            size = await asyncio.to_thread(self._upload_sync, local_path, remote_path)
            log.info("upload.done", remote=remote_path, bytes=size)
            return size

    async def upload_many(self, pairs: Iterable[tuple[Path, str]]) -> int:
        """Upload a batch of (local, remote) pairs concurrently."""
        tasks = [self.upload_one(lp, rp) for lp, rp in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_bytes = 0
        failures = 0
        for r in results:
            if isinstance(r, Exception):
                failures += 1
                log.error("upload.failed", error=str(r))
            else:
                total_bytes += r

        log.info("upload.batch_complete", total_bytes=total_bytes, failures=failures)
        if failures:
            raise RuntimeError(f"{failures} upload(s) failed")
        return total_bytes