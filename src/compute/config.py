"""Configuration management for the Compute service."""

from __future__ import annotations

import os
from argparse import ArgumentParser
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from .utils import ensure_cl_server_dir


class ComputeConfigBase(BaseModel):
    """Base configuration shared between Compute Server and Worker."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True, validate_assignment=True
    )

    # Logging & Debug
    debug: bool = False
    log_level: str = "info"

    # Paths (Derived from CL_SERVER_DIR)
    cl_server_dir: str
    public_key_path: str
    database_url: str
    compute_storage_dir: str

    # MQTT Settings
    mqtt_url: str = "mqtt://localhost:1883"
    mqtt_heartbeat_interval: float = 10.0
    capability_topic_prefix: str = "inference/workers"
    mqtt_job_events_topic: str = "inference/events"


class ComputeServerConfig(ComputeConfigBase):
    """Runtime configuration for the Compute Server."""

    _instance: ClassVar[ComputeServerConfig | None] = None

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8002
    reload: bool = False
    
    # Security
    auth_disabled: bool = False

    @classmethod
    def get_config(cls) -> ComputeServerConfig:
        """Get or create the unified ComputeServerConfig singleton."""
        if cls._instance is None:
            cls._instance = cls._from_cli_args()
        return cls._instance

    @classmethod
    def _from_cli_args(cls) -> ComputeServerConfig:
        """Parse CLI arguments and return a ComputeServerConfig instance."""
        parser = ArgumentParser(prog="compute-server")
        parser.add_argument("--port", "-p", type=int, default=8002)
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload (dev)")
        parser.add_argument("--debug", action="store_true", help="Enable debug mode")
        parser.add_argument("--log-level", default="info", help="Log level")
        parser.add_argument("--no-auth", action="store_true", dest="auth_disabled", help="Disable authentication checks")
        
        # MQTT args (common)
        parser.add_argument("--mqtt-url", default="mqtt://localhost:1883", help="MQTT broker URL")
        
        args, _ = parser.parse_known_args()

        # Initialize basic info needed for config
        try:
            cl_dir = ensure_cl_server_dir(create_if_missing=True)
        except SystemExit:
            # Re-raise if we can't determine the directory, as checking strictly is key.
            # In some test environments, ensure_cl_server_dir might raise SystemExit(1).
            raise

        cl_dir_path = Path(cl_dir)
        
        # Prepare Config Dict
        config_dict = {k: v for k, v in vars(args).items() if v is not None}
        
        # Populate Derived Paths
        config_dict["cl_server_dir"] = str(cl_dir_path)
        config_dict["public_key_path"] = str(cl_dir_path / "keys" / "public_key.pem")
        config_dict["database_url"] = f"sqlite:///{cl_dir_path / 'compute.db'}"
        config_dict["compute_storage_dir"] = str(cl_dir_path / "compute")

        config = cls.model_validate(config_dict)
        return config


class ComputeWorkerConfig(ComputeConfigBase):
    """Runtime configuration for the Compute Worker."""

    _instance: ClassVar[ComputeWorkerConfig | None] = None

    # Worker Settings
    worker_id: str = "worker-default"
    worker_poll_interval: float = 1.0
    worker_supported_tasks: list[str] | None = None
    compute_url: str = "http://localhost:8002"

    @classmethod
    def get_config(cls) -> ComputeWorkerConfig:
        """Get or create the unified ComputeWorkerConfig singleton."""
        if cls._instance is None:
            cls._instance = cls._from_cli_args()
        return cls._instance

    @classmethod
    def _from_cli_args(cls) -> ComputeWorkerConfig:
        """Parse CLI arguments and return a ComputeWorkerConfig instance."""
        parser = ArgumentParser(prog="compute-worker")
        parser.add_argument("--worker-id", "-w", default="worker-default", help="Unique worker identifier")
        parser.add_argument("--tasks", "-t", default=None, help="Comma-separated list of task types")
        parser.add_argument("--log-level", "-l", default="INFO", help="Logging level")
        parser.add_argument("--debug", action="store_true", help="Enable debug mode") # Typically worker sets log level directly, but debug flag helps.
        
        parser.add_argument("--compute-url", default="http://localhost:8002", help="Compute server URL")
        parser.add_argument("--worker-poll-interval", type=float, default=1.0, help="Polling interval")
        
        # MQTT args (common)
        parser.add_argument("--mqtt-url", default="mqtt://localhost:1883", help="MQTT broker URL")

        args, _ = parser.parse_known_args()

        # Initialize basic info needed for config
        try:
            # We don't necessarily create if missing for worker, but we need the path.
            # ensure_cl_server_dir checks env var primarily.
            # Mirroring logic: worker expects server to have set it up, but validation happens in main usually.
            # Here we just need the path to populate config.
            cl_dir = ensure_cl_server_dir(create_if_missing=False)
        except SystemExit:
            raise

        cl_dir_path = Path(cl_dir)

        # Prepare Config Dict
        config_dict = {k: v for k, v in vars(args).items() if v is not None}
        
        # Handle Tasks parsing
        if args.tasks:
            config_dict["worker_supported_tasks"] = args.tasks.split(",")
        
        # Populate Derived Paths
        config_dict["cl_server_dir"] = str(cl_dir_path)
        config_dict["public_key_path"] = str(cl_dir_path / "keys" / "public_key.pem")
        config_dict["database_url"] = f"sqlite:///{cl_dir_path / 'compute.db'}"
        config_dict["compute_storage_dir"] = str(cl_dir_path / "compute")

        # Map log level case if needed, but pydantic might handle string assignment.
        if hasattr(args, "log_level"):
             config_dict["log_level"] = args.log_level.lower()

        config = cls.model_validate(config_dict)
        return config
