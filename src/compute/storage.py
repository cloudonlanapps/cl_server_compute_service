from __future__ import annotations

import hashlib
import shutil
from os import PathLike
from pathlib import Path
from typing import Final, override

import aiofiles
from cl_ml_tools import AsyncFileLike, FileLike, JobStorage, SavedJobFile


class JobStorageService(JobStorage):
    """Service for managing file storage with organized directory structure."""

    _CHUNK_SIZE: Final[int] = 1024 * 1024  # 1 MB
    base_dir: Path

    def __init__(self, base_dir: Path | str):
        """
        Initialize file storage service.

        Args:
            base_dir: Base directory for file storage. Required.
        """
        if not base_dir:
            raise ValueError("base_dir is required for JobStorageService")

        self.base_dir: Path = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # JobStorage Protocol Methods
    # -------------------------------------------------------------------------
    @override
    def create_directory(self, job_id: str) -> None:
        """Create storage directory for a job (JobStorage protocol).

        Args:
            job_id: Unique job identifier
        """
        job_dir = self.base_dir / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "input").mkdir(exist_ok=True)
        (job_dir / "output").mkdir(exist_ok=True)

    @override
    def remove(self, job_id: str) -> bool:
        """Remove all files associated with a job (JobStorage protocol).

        Args:
            job_id: Unique job identifier

        Returns:
            True if removed successfully, False otherwise
        """
        job_dir = self.base_dir / "jobs" / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
            return True
        return False

    @override
    async def save(
        self,
        job_id: str,
        relative_path: str,
        file: FileLike,
        *,
        mkdirs: bool = True,
    ) -> SavedJobFile:
        """Save a file into job storage (JobStorage protocol).

        Args:
            job_id: Unique job identifier
            relative_path: Relative path within job storage
            file: File to save (async file-like, bytes, str path, or PathLike)
            mkdirs: Create parent directories if needed

        Returns:
            Metadata of the saved file
        """
        # Resolve target path
        target_path = self.base_dir / "jobs" / job_id / relative_path

        file_size = 0
        hasher = hashlib.sha256()
        # Create parent directories if requested
        if mkdirs:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle different file types
        if isinstance(file, bytes):
            # Direct bytes
            _ = target_path.write_bytes(file)
            file_size = len(file)
            hasher.update(file)
        elif isinstance(file, (str, PathLike)):
            # Copy from existing file
            source_path = Path(file)
            _ = shutil.copy2(source_path, target_path)
            file_size = target_path.stat().st_size
            with open(target_path, "rb") as f:
                for chunk in iter(lambda: f.read(self._CHUNK_SIZE), b""):
                    hasher.update(chunk)
        else:
            async with aiofiles.open(target_path, "wb") as f:
                while True:
                    chunk = await file.read(self._CHUNK_SIZE)
                    if not chunk:
                        break
                    _ = await f.write(chunk)
                    file_size += len(chunk)
                    hasher.update(chunk)

        return SavedJobFile(
            relative_path=relative_path,
            size=file_size,
            hash=hasher.hexdigest(),
        )

    @override
    def allocate_path(
        self,
        job_id: str,
        relative_path: str,
        *,
        mkdirs: bool = True,
    ) -> Path:
        """Allocate a filesystem path for writing (JobStorage protocol).

        Intended for libraries that require filenames (numpy, opencv, ffmpeg, PIL).

        Args:
            job_id: Unique job identifier
            relative_path: Relative path within job storage
            mkdirs: Create parent directories if needed

        Returns:
            Absolute Path object
        """
        target_path = self.base_dir / "jobs" / job_id / relative_path

        if mkdirs:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        return target_path

    @override
    async def open(
        self,
        job_id: str,
        relative_path: str,
    ) -> AsyncFileLike:
        """Open a stored file for async reading (JobStorage protocol).

        Args:
            job_id: Unique job identifier
            relative_path: Relative path within job storage

        Returns:
            Async file-like object
        """
        target_path = self.base_dir / "jobs" / job_id / relative_path
        return await aiofiles.open(target_path, "rb")

    @override
    def resolve_path(
        self,
        job_id: str,
        relative_path: str | None = None,
    ) -> Path:
        """Resolve a job-relative path to an absolute filesystem path (JobStorage protocol).

        Args:
            job_id: Unique job identifier
            relative_path: Optional relative path within job storage

        Returns:
            Absolute Path object
        """
        if relative_path is None:
            return self.base_dir / "jobs" / job_id
        return self.base_dir / "jobs" / job_id / relative_path
