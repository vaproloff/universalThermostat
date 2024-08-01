"""Thermostat windows dealing classes."""

import logging

from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)


class WindowController:
    """Coordinator for windows."""

    def __init__(self, window_conf: ConfigType) -> None:
        """Initialize the coordinator."""
        self._window_conf = window_conf
