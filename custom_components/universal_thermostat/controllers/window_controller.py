"""Thermostat windows dealing classes."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import condition, config_validation as cv
from homeassistant.helpers.template import Template

from ..const import ATTR_TIMEOUT, CONF_INVERTED

_LOGGER = logging.getLogger(__name__)


class Window:
    """Window entity."""

    def __init__(
        self,
        entity_id: str,
        timeout=None,
        inverted: bool = False,
    ) -> None:
        """Initialize a window."""
        self._entity_id = entity_id
        self._timeout = timeout
        self._inverted = inverted

    @property
    def entity_id(self) -> str:
        """Return entity_id of the window."""
        return self._entity_id

    @property
    def timeout(self):
        """Return timeout of the window."""
        if self._timeout is not None:
            if isinstance(self._timeout, Template):
                try:
                    timeout = self._timeout.async_render(parse_result=False)
                except (TemplateError, TypeError) as e:
                    _LOGGER.warning(
                        "%s: unable to render window's timeout template: %s. Error: %s",
                        self.entity_id,
                        self._timeout,
                        e,
                    )
                    return None

                try:
                    return cv.positive_time_period(timeout)
                except vol.Invalid:
                    _LOGGER.warning(
                        "%s: unable to validate window's timeout template value: %s",
                        self.entity_id,
                        self._timeout,
                    )
                    return None

        return self._timeout

    @property
    def inverted(self) -> bool:
        """Return if window is inverted."""
        return self._inverted


class WindowController:
    """Coordinator for windows."""

    def __init__(
        self, hass: HomeAssistant, windows: str | list[str | dict[str, Any]]
    ) -> None:
        """Initialize the coordinator."""
        self._hass = hass
        self._thermostat_entity_id = None
        self._windows: list[Window] = []

        if isinstance(windows, str):
            self._windows.append(Window(windows))
        else:
            for window in windows:
                if isinstance(window, str):
                    self._windows.append(Window(window))
                else:
                    self._windows.append(
                        Window(
                            entity_id=window.get(ATTR_ENTITY_ID),
                            timeout=window.get(ATTR_TIMEOUT),
                            inverted=window.get(CONF_INVERTED, False),
                        )
                    )

    @property
    def entity_ids(self) -> list[str]:
        """Return a list of window entities."""
        return [window.entity_id for window in self._windows]

    @property
    def is_safe_opened(self) -> bool:
        """If any of windows is opened."""
        for window in self._windows:
            is_now_opened = self._hass.states.is_state(
                window.entity_id, STATE_ON if not window.inverted else STATE_OFF
            )

            if window.timeout is not None:
                if (
                    is_now_opened
                    and condition.state(
                        self._hass,
                        window.entity_id,
                        STATE_ON if not window.inverted else STATE_OFF,
                        window.timeout,
                    )
                    or not is_now_opened
                    and not condition.state(
                        self._hass,
                        window.entity_id,
                        STATE_OFF if not window.inverted else STATE_ON,
                        window.timeout,
                    )
                ):
                    return True

            elif is_now_opened:
                return True

        return False

    def find_by_entity_id(self, entity_id: str) -> Window | None:
        """Return window with entity_id if exists."""
        for window in self._windows:
            if entity_id == window.entity_id:
                return window
