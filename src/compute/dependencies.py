"""FastAPI dependencies for Compute service."""

from typing import cast
from fastapi import Request
from cl_ml_tools import MQTTBroadcaster


def get_mqtt_broadcaster(request: Request) -> MQTTBroadcaster | None:
    """Get initialized MQTT broadcaster from app state.
    
    Returns:
        MQTTBroadcaster if initialized, None otherwise.
        Note: In production lifespan, it should always be initialized.
    """
    if hasattr(request.app.state, "broadcaster"):
        return cast(MQTTBroadcaster, request.app.state.broadcaster)
    return None
