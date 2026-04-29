"""Thermostat windows dealing classes."""

import logging
from typing import Any

from custom_components.universal_thermostat.const import ATTR_TIMEOUT, CONF_INVERTED
import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import condition, config_validation as cv
from homeassistant.helpers.template import Template

_LOGGER = logging.getLogger(__name__)

_WINDOW_TIMEOUT_WARNINGS: set[tuple[str, str, str]] = set()


def _warning_once(
    warning_key: tuple[str, str, str],
    message: str,
    *args: Any,
) -> None:
    """Log a warning once for a repeated window timeout problem."""
    if warning_key in _WINDOW_TIMEOUT_WARNINGS:
        return

    _WINDOW_TIMEOUT_WARNINGS.add(warning_key)
    _LOGGER.warning(message, *args)


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
                    _warning_once(
                        (self.entity_id, "render", str(self._timeout)),
                        "%s: unable to render window's timeout template: %s. Error: %s",
                        self.entity_id,
                        self._timeout,
                        e,
                    )
                    return None

                try:
                    return cv.positive_time_period(timeout)
                except vol.Invalid as e:
                    _warning_once(
                        (self.entity_id, "validate", str(self._timeout)),
                        "%s: unable to validate window's timeout template value: %s. Error: %s",
                        self.entity_id,
                        self._timeout,
                        e,
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

    def _is_window_opened(self, window: Window) -> bool:
        """Return if a window is currently open, ignoring delays."""
        return self._hass.states.is_state(
            window.entity_id, STATE_ON if not window.inverted else STATE_OFF
        )

    @property
    def is_opened(self) -> bool:
        """If any window is currently opened."""
        return any(self._is_window_opened(window) for window in self._windows)

    @property
    def is_safe_opened(self) -> bool:
        """If any of windows is opened."""
        for window in self._windows:
            is_now_opened = self._is_window_opened(window)
            timeout = window.timeout

            if timeout is not None:
                if (
                    is_now_opened
                    and condition.state(
                        self._hass,
                        window.entity_id,
                        STATE_ON if not window.inverted else STATE_OFF,
                        timeout,
                    )
                ) or (
                    not is_now_opened
                    and not condition.state(
                        self._hass,
                        window.entity_id,
                        STATE_OFF if not window.inverted else STATE_ON,
                        timeout,
                    )
                ):
                    return True

            elif is_now_opened:
                return True

        return False

    @property
    def max_timeout(self):
        """Return maximum timeout of all windows."""
        timeouts = []
        for window in self._windows:
            timeout = window.timeout
            if timeout is not None:
                timeouts.append(timeout)
        if timeouts:
            return max(timeouts)
        return None

    def find_by_entity_id(self, entity_id: str) -> Window | None:
        """Return window with entity_id if exists."""
        for window in self._windows:
            if entity_id == window.entity_id:
                return window
        return None
