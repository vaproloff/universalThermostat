"""Abstract controller class."""

import abc
from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any, final

from homeassistant.components.climate import HVACMode
from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, split_entity_id
from homeassistant.helpers.event import async_track_time_interval

from ..const import REASON_KEEP_ALIVE

_LOGGER = logging.getLogger(__name__)


class Thermostat(abc.ABC):
    """Abstract class for universal thermostat entity."""

    @property
    @abc.abstractmethod
    def hvac_mode(self) -> HVACMode:
        """Get thermostat HVAC mode."""

    @abc.abstractmethod
    def get_entity_id(self) -> str:
        """Get Entity name instance."""

    @abc.abstractmethod
    def get_context(self) -> Context:
        """Get Context instance."""

    @abc.abstractmethod
    def get_ctrl_target_temperature(self, ctrl_hvac_mode) -> float:
        """Return controller's target temperature."""
        return self.precision

    @property
    @abc.abstractmethod
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""

    @property
    @abc.abstractmethod
    def precision(self) -> float:
        """Return the precision of the system."""

    @property
    @abc.abstractmethod
    def current_temperature(self) -> float:
        """Return the sensor temperature."""

    @property
    @abc.abstractmethod
    def min_temp(self) -> float:
        """Return the minimum temperature."""

    @property
    @abc.abstractmethod
    def max_temp(self) -> float:
        """Return the maximum temperature."""

    @abc.abstractmethod
    def async_write_ha_state(self) -> None:
        """Write thermostat state."""

    @abc.abstractmethod
    def async_on_remove(self, func: CALLBACK_TYPE) -> None:
        """Add callback."""


class AbstractController(abc.ABC):
    """Abstract controller."""

    def __init__(
        self,
        name: str,
        mode: str,
        target_entity_id: str,
        inverted: bool,
        keep_alive: timedelta | None,
    ) -> None:
        """Initialize the controller."""
        self._thermostat: Thermostat | None = None
        self.name = name
        self._mode = mode
        self._target_entity_id = target_entity_id
        self._inverted = inverted
        self._keep_alive = keep_alive
        self.__running = False
        self._hass: HomeAssistant | None = None

        if mode not in [HVACMode.COOL, HVACMode.HEAT]:
            raise ValueError(f"Unsupported mode: '{mode}'")

    def set_thermostat(self, thermostat):
        """Set parent universal thermostat entity."""
        self._thermostat = thermostat

    @property
    def _context(self) -> Context:
        return self._thermostat.get_context()

    @property
    @final
    def _thermostat_entity_id(self) -> str:
        return self._thermostat.get_entity_id()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return controller's extra attributes for thermostat entity."""
        return None

    @property
    @final
    def mode(self) -> str:
        """Return controller HVAC mode."""
        return self._mode

    @property
    def running(self):
        """If controller is turned on now."""
        return self.__running

    @property
    @abc.abstractmethod
    def _is_on(self) -> bool:
        """Is controller entity turned on."""

    @property
    def is_active(self) -> bool:
        """Is controller entity HVAC active."""
        return self._is_on

    async def async_added_to_hass(self, hass: HomeAssistant, attrs: Mapping[str, Any]):
        """Add controller when adding thermostat entity."""
        self._hass = hass

        if self._keep_alive:
            _LOGGER.info(
                "%s - %s: setting up keep_alive (%s)",
                self._thermostat_entity_id,
                self.name,
                self._keep_alive,
            )
            self._thermostat.async_on_remove(
                async_track_time_interval(
                    self._hass, self.__async_keep_alive, self._keep_alive
                )
            )

    def get_unique_id(self):
        """Get unique ID, for attrs storage."""
        return "ctrl_" + split_entity_id(self._target_entity_id)[1]

    def get_target_entity_ids(self) -> list[str]:
        """Get all target entity IDs to subscribe state change on them."""
        return [self._target_entity_id]

    def get_used_template_entity_ids(self) -> list[str]:
        """Get all used template entity IDs to subscribe state change on them."""
        return []

    @final
    async def async_start(self):
        """Turn on the controller."""
        cur_temp = self._thermostat.current_temperature
        target_temp = self._thermostat.get_ctrl_target_temperature(self._mode)

        _LOGGER.debug(
            "%s - %s: trying to start controller, current: %s, target: %s ",
            self._thermostat_entity_id,
            self.name,
            cur_temp,
            target_temp,
        )

        if await self._async_start(cur_temp, target_temp):
            self.__running = True
            _LOGGER.debug(
                "%s - %s: controller started, current: %s, target: %s",
                self._thermostat_entity_id,
                self.name,
                cur_temp,
                target_temp,
            )
        else:
            _LOGGER.error(
                "%s - %s: Error starting controller, current: %s, target: %s",
                self._thermostat_entity_id,
                self.name,
                cur_temp,
                target_temp,
            )

    @final
    async def async_stop(self):
        """Turn off the controller."""
        _LOGGER.debug(
            "%s - %s: stopping controller", self._thermostat_entity_id, self.name
        )
        await self._async_stop()
        self.__running = False

    def _round_to_target_precision(self, value: float) -> float:
        """Round output to target precision."""
        return value

    @abc.abstractmethod
    async def _async_start(self, cur_temp, target_temp) -> bool:
        """Start controller implementation."""

    @abc.abstractmethod
    async def _async_stop(self):
        """Stop controller implementation."""

    @abc.abstractmethod
    async def _async_ensure_not_running(self):
        """Ensure that target is off."""

    @final
    async def async_control(self, time=None, force=False, reason=None):
        """Proccess tasks reacting on changes as the thermostat callback."""

        cur_temp = self._thermostat.current_temperature
        target_temp = self._thermostat.get_ctrl_target_temperature(self._mode)

        if not self.__running:
            await self._async_ensure_not_running()
        elif None not in (cur_temp, target_temp):
            await self._async_control(
                cur_temp,
                target_temp,
                time=time,
                force=force,
                reason=reason,
            )

    @abc.abstractmethod
    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        """Control method implementation."""

    @final
    async def __async_keep_alive(self, time=None):
        await self.async_control(time=time, reason=REASON_KEEP_ALIVE)
