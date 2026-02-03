"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from compute.schemas import CleanupResult, JobResponse, StorageInfo, PrefResponse


class TestJobResponse:
    """Tests for JobResponse schema."""

    def test_job_response_required_fields(self):
        """Test JobResponse with required fields only."""
        job = JobResponse(
            job_id="test-job-1",
            task_type="test_task",
            status="queued",
            progress=0,
            params={},
            task_output=None,
            error_message=None,
            priority=5,
            created_at=1234567890000,
            updated_at=None,
            started_at=None,
            completed_at=None,
        )

        assert job.job_id == "test-job-1"
        assert job.task_type == "test_task"
        assert job.status == "queued"
        assert job.progress == 0
        assert job.params == {}
        assert job.task_output is None
        assert job.error_message is None
        assert job.priority == 5
        assert job.created_at == 1234567890000
        assert job.updated_at is None
        assert job.started_at is None
        assert job.completed_at is None

    def test_job_response_all_fields(self):
        """Test JobResponse with all fields populated."""
        job = JobResponse(
            job_id="test-job-2",
            task_type="image_resize",
            status="completed",
            progress=100,
            params={"width": 800, "height": 600},
            task_output={"result": "success", "file_path": "/path/to/file.jpg"},
            error_message=None,
            priority=7,
            created_at=1234567890000,
            updated_at=1234567891000,
            started_at=1234567890500,
            completed_at=1234567891000,
        )

        assert job.job_id == "test-job-2"
        assert job.task_type == "image_resize"
        assert job.status == "completed"
        assert job.progress == 100
        assert job.params == {"width": 800, "height": 600}
        assert job.task_output == {"result": "success", "file_path": "/path/to/file.jpg"}
        assert job.error_message is None
        assert job.priority == 7
        assert job.created_at == 1234567890000
        assert job.updated_at == 1234567891000
        assert job.started_at == 1234567890500
        assert job.completed_at == 1234567891000

    def test_job_response_failed_status(self):
        """Test JobResponse with failed status and error message."""
        job = JobResponse(
            job_id="test-job-3",
            task_type="image_process",
            status="failed",
            progress=50,
            params={"input": "test.jpg"},
            task_output=None,
            error_message="File not found",
            created_at=1234567890000,
            priority=5,
            updated_at=None,
            started_at=None,
            completed_at=None,
        )

        assert job.status == "failed"
        assert job.error_message == "File not found"
        assert job.progress == 50

    def test_job_response_missing_required_fields(self):
        """Test that JobResponse requires job_id, task_type, status, and created_at."""
        with pytest.raises(ValidationError):
            _ = JobResponse.model_validate({})

        with pytest.raises(ValidationError):
            data = {"job_id": "test-id"}
            _ = JobResponse.model_validate(data)

        with pytest.raises(ValidationError):
            data2 = {"job_id": "test-id", "task_type": "test_task"}
            _ = JobResponse.model_validate(data2)

    def test_job_response_nested_params(self):
        """Test JobResponse with nested params structure."""
        job = JobResponse(
            job_id="test-job-4",
            task_type="complex_task",
            status="in_progress",
            progress=0,
            params={
                "config": {
                    "nested": {"value": 123},
                    "list": [1, 2, 3],
                },
                "flags": [True, False, True],
            },
            task_output=None,
            error_message=None,
            priority=5,
            created_at=1234567890000,
            updated_at=None,
            started_at=None,
            completed_at=None,
        )

        config = job.params["config"]
        assert isinstance(config, dict)
        nested = config["nested"]
        assert isinstance(nested, dict)
        assert nested["value"] == 123
        assert config["list"] == [1, 2, 3]
        assert job.params["flags"] == [True, False, True]


class TestStorageInfo:
    """Tests for StorageInfo schema."""

    def test_storage_info_valid(self):
        """Test StorageInfo with valid data."""
        storage = StorageInfo(
            total_size=1024000,
            job_count=42,
        )

        assert storage.total_size == 1024000
        assert storage.job_count == 42

    def test_storage_info_zero_values(self):
        """Test StorageInfo with zero values."""
        storage = StorageInfo(
            total_size=0,
            job_count=0,
        )

        assert storage.total_size == 0
        assert storage.job_count == 0

    def test_storage_info_missing_fields(self):
        """Test that StorageInfo requires both fields."""
        with pytest.raises(ValidationError):
            _ = StorageInfo.model_validate({})

        with pytest.raises(ValidationError):
            _ = StorageInfo.model_validate({"total_size": 100})

        with pytest.raises(ValidationError):
            _ = StorageInfo.model_validate({"job_count": 10})


class TestCleanupResult:
    """Tests for CleanupResult schema."""

    def test_cleanup_result_valid(self):
        """Test CleanupResult with valid data."""
        result = CleanupResult(
            deleted_count=10,
            freed_space=5242880,
        )

        assert result.deleted_count == 10
        assert result.freed_space == 5242880

    def test_cleanup_result_zero_values(self):
        """Test CleanupResult with zero values (no cleanup performed)."""
        result = CleanupResult(
            deleted_count=0,
            freed_space=0,
        )

        assert result.deleted_count == 0
        assert result.freed_space == 0

    def test_cleanup_result_missing_fields(self):
        """Test that CleanupResult requires both fields."""
        with pytest.raises(ValidationError):
            _ = CleanupResult.model_validate({})

        with pytest.raises(ValidationError):
            _ = CleanupResult.model_validate({"deleted_count": 5})

        with pytest.raises(ValidationError):
            _ = CleanupResult.model_validate({"freed_space": 1000})


class TestPrefResponse:
    """Tests for PrefResponse schema."""

    def test_pref_response_valid(self):
        """Test PrefResponse with valid data."""
        pref = PrefResponse(
            guest_mode=True,
            updated_at=1234567890000,
            updated_by="admin_user",
        )

        assert pref.guest_mode is True
        assert pref.updated_at == 1234567890000
        assert pref.updated_by == "admin_user"

    def test_pref_response_defaults(self):
        """Test PrefResponse with default values."""
        pref = PrefResponse(guest_mode=False)

        assert pref.guest_mode is False
        assert pref.updated_at is None
        assert pref.updated_by is None

    def test_pref_response_missing_fields(self):
        """Test that PrefResponse requires guest_mode."""
        with pytest.raises(ValidationError):
            _ = PrefResponse.model_validate({})
