"""Configuration management for the Compute service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ComputeConfig:
    """Runtime configuration for the Compute service."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    reload: bool = False
    log_level: str = "info"

    # Paths
    cl_server_dir: str = ""
    public_key_path: str = ""
    
    # Worker Settings
    compute_storage_dir: str = ""
    worker_poll_interval: float = 1.0
    worker_supported_tasks: list[str] | None = None
    
    # MQTT Settings
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_heartbeat_interval: float = 10.0
    capability_topic_prefix: str = "capabilities"
    broadcast_type: str = "redis" # Default to redis as per shared config, or mqtt? Shared config says BROADCAST_TYPE.

    # Database
    database_url: str = "sqlite:///compute.db"

    # Security
    auth_disabled: bool = False

    @property
    def worker_database_url(self) -> str:
        """Alias for database_url, used by some shared logic."""
        return self.database_url

    @classmethod
    def from_cli_args(cls, args: object | None = None) -> ComputeConfig:
        """Create configuration from parsed CLI arguments.

        Args:
            args: Namespace object from argparse (optional)

        Returns:
            Configured ComputeConfig instance
        """
        if args is None:
            # Create empty object to allow getattr default fallback
            args = type("Args", (), {})()
            
        # Get CL_SERVER_DIR from env (set in main.py) or args
        cl_server_dir = os.getenv("CL_SERVER_DIR", "")
        
        # Derive compute storage dir
        compute_storage_dir = getattr(args, "compute_storage_dir", "")
        if not compute_storage_dir and cl_server_dir:
            compute_storage_dir = str(Path(cl_server_dir) / "compute")
        
        # Determine database URL
        db_url = getattr(args, "database_url", "")
        if not db_url:
            # Fallback to default in CL_SERVER_DIR if not provided
            if cl_server_dir:
                db_url = f"sqlite:///{Path(cl_server_dir) / 'compute.db'}"
            else:
                db_url = "sqlite:///compute.db"

        # Determine public key path
        pub_key = getattr(args, "public_key_path", "")
        if not pub_key and cl_server_dir:
            pub_key = str(Path(cl_server_dir) / "public_key.pem")

        return cls(
            host=getattr(args, "host", "0.0.0.0"),
            port=getattr(args, "port", 8002),
            debug=getattr(args, "debug", False),
            reload=getattr(args, "reload", False),
            log_level=getattr(args, "log_level", "info"),
            cl_server_dir=cl_server_dir,
            public_key_path=pub_key,
            database_url=db_url,
            auth_disabled=getattr(args, "auth_disabled", False),
            # Worker
            compute_storage_dir=compute_storage_dir,
            worker_poll_interval=getattr(args, "worker_poll_interval", 1.0),
            # MQTT
            mqtt_broker=getattr(args, "mqtt_broker", "localhost"),
            mqtt_port=getattr(args, "mqtt_port", 1883),
        )
