from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from . import utils


class ComputeBaseConfig(BaseModel):
    """Base configuration for Compute service roles."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True, validate_assignment=True
    )

    # Paths (populated after CLI parsing by finalize)
    cl_server_dir: Path
    public_key_path: Path
    compute_storage_dir: Path

    # MQTT Settings
    mqtt_url: str
    mqtt_heartbeat_interval: float = 10.0
    capability_topic_prefix: str = "inference/workers"
    mqtt_job_events_topic: str

    # Database
    database_url: str
    debug: bool = False

    def finalize_base(self):
        """Finalize base configuration after CLI parsing."""
        cl_dir = utils.ensure_cl_server_dir(create_if_missing=True)
        self.cl_server_dir = cl_dir

        if not self.public_key_path:
            self.public_key_path = cl_dir / "keys" / "public_key.pem"

        if not self.compute_storage_dir:
            self.compute_storage_dir = cl_dir / "compute"

        # Determine database URL - strictly derived from CL_SERVER_DIR
        self.database_url = str(f"sqlite:///{cl_dir / 'compute.db'}")


class ComputeServerConfig(ComputeBaseConfig):
    """Configuration for the Compute Server."""

    _instance: ClassVar[ComputeServerConfig | None] = None

    host: str = "0.0.0.0"
    port: int = 8002
    reload: bool = False
    log_level: str = "info"
    auth_disabled: bool = False

    def finalize(self):
        """Finalize server configuration."""
        self.finalize_base()

    @classmethod
    def from_args(cls) -> ComputeServerConfig:
        """Get or create the global ComputeServerConfig singleton."""
        if cls._instance is not None:
            return cls._instance

        parser = ArgumentParser(prog="compute-server")
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", "-p", type=int, default=8002)
        parser.add_argument("--debug", action="store_true", help="Enable debug mode")
        parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload (dev)")
        parser.add_argument("--log-level", default="info")
        parser.add_argument("--mqtt-url", default="mqtt://localhost:1883")
        parser.add_argument(
            "--no-auth", action="store_true", dest="auth_disabled", help="Disable authentication"
        )
        parser.add_argument("--public-key-path", default="")
        parser.add_argument("--compute-storage-dir", default="")

        args, _ = parser.parse_known_args()
        config_dict = {k: v for k, v in vars(args).items() if v is not None}

        if config_dict.get("public_key_path"):
            config_dict["public_key_path"] = Path(config_dict["public_key_path"])
        if config_dict.get("compute_storage_dir"):
            config_dict["compute_storage_dir"] = Path(config_dict["compute_storage_dir"])

        cl_dir = utils.ensure_cl_server_dir(create_if_missing=True)
        config_dict["cl_server_dir"] = cl_dir

        # Ensure mandatory fields have values
        if "mqtt_url" not in config_dict:
            config_dict["mqtt_url"] = "mqtt://localhost:1883"
        if "mqtt_job_events_topic" not in config_dict:
            config_dict["mqtt_job_events_topic"] = "inference/events"
        if "database_url" not in config_dict:
            config_dict["database_url"] = ""  # Populated in finalize_base

        cls._instance = cls.model_validate(config_dict)
        cls._instance.finalize()
        return cls._instance


class ComputeWorkerConfig(ComputeBaseConfig):
    """Configuration for the Compute Worker."""

    _instance: ClassVar[ComputeWorkerConfig | None] = None

    worker_id: str = "worker-default"
    compute_url: str = "http://localhost:8002"
    worker_poll_interval: float = 1.0
    worker_supported_tasks: list[str] | None = None
    log_level: str = "info"

    def finalize(self):
        """Finalize worker configuration."""
        self.finalize_base()

    @classmethod
    def from_args(cls) -> ComputeWorkerConfig:
        """Get or create the global ComputeWorkerConfig singleton."""
        if cls._instance is not None:
            return cls._instance

        parser = ArgumentParser(prog="compute-worker")
        parser.add_argument("--worker-id", "-w", default="worker-default")
        parser.add_argument("--tasks", "-t", default=None)
        # Worker connected to server at this URL
        parser.add_argument("--compute-url", default="http://localhost:8002")
        parser.add_argument("--worker-poll-interval", type=float, default=1.0)
        parser.add_argument("--mqtt-url", default="mqtt://localhost:1883")
        parser.add_argument("--log-level", default="info")
        parser.add_argument("--public-key-path", default="")
        parser.add_argument("--compute-storage-dir", default="")

        args, _ = parser.parse_known_args()
        config_dict = {k: v for k, v in vars(args).items() if v is not None}

        if "tasks" in config_dict and config_dict["tasks"]:
            config_dict["worker_supported_tasks"] = config_dict["tasks"].split(",")

        if config_dict.get("public_key_path"):
            config_dict["public_key_path"] = Path(config_dict["public_key_path"])
        if config_dict.get("compute_storage_dir"):
            config_dict["compute_storage_dir"] = Path(config_dict["compute_storage_dir"])

        cl_dir = utils.ensure_cl_server_dir(create_if_missing=True)
        config_dict["cl_server_dir"] = cl_dir

        # Ensure mandatory fields have values
        if "mqtt_url" not in config_dict:
            config_dict["mqtt_url"] = "mqtt://localhost:1883"
        if "mqtt_job_events_topic" not in config_dict:
            config_dict["mqtt_job_events_topic"] = "inference/events"
        if "database_url" not in config_dict:
            config_dict["database_url"] = ""  # Populated in finalize_base

        cls._instance = cls.model_validate(config_dict)
        cls._instance.finalize()
        return cls._instance


# Simplified alias for generic code
ComputeConfig = ComputeBaseConfig
