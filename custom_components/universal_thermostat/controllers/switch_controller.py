"""Support for simple switch controllers."""

from datetime import timedelta
import logging
from typing import Optional

from homeassistant.components.climate import HVACMode
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import DOMAIN as HA_DOMAIN
from homeassistant.exceptions import ConditionError, TemplateError
from homeassistant.helpers import condition
from homeassistant.helpers.template import RenderInfo, Template

from ..const import (
    DEFAULT_COLD_TOLERANCE,
    DEFAULT_HOT_TOLERANCE,
    REASON_KEEP_ALIVE,
    REASON_THERMOSTAT_NOT_RUNNING,
    REASON_THERMOSTAT_STOP,
)
from . import AbstractController

_LOGGER = logging.getLogger(__name__)


class SwitchController(AbstractController):
    """Simple switch controller class."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        cold_tolerance_template: Template,
        hot_tolerance_template: Template,
        inverted: bool,
        keep_alive: Optional[timedelta],
        min_cycle_duration,
    ) -> None:
        """Initialize the controller."""
        super().__init__(name, mode, target_entity_id, inverted, keep_alive)
        self._cold_tolerance_template = cold_tolerance_template
        self._hot_tolerance_template = hot_tolerance_template
        self._min_cycle_duration = min_cycle_duration

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._cold_tolerance_template is not None:
            try:
                template_info: RenderInfo = (
                    self._cold_tolerance_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._cold_tolerance_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._hot_tolerance_template is not None:
            try:
                template_info: RenderInfo = (
                    self._hot_tolerance_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._hot_tolerance_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    @property
    def cold_tolerance(self) -> float:
        """Returns Cold tolerance."""

        if self._cold_tolerance_template is not None:
            try:
                cold_tolerance = self._cold_tolerance_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._cold_tolerance_template,
                    e,
                )
                return float(DEFAULT_COLD_TOLERANCE)

            try:
                return float(cold_tolerance)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._cold_tolerance_template,
                    e,
                )

        return float(DEFAULT_COLD_TOLERANCE)

    @property
    def hot_tolerance(self) -> float:
        """Returns Hot tolerance."""

        if self._hot_tolerance_template is not None:
            try:
                hot_tolerance = self._hot_tolerance_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._hot_tolerance_template,
                    e,
                )
                return float(DEFAULT_HOT_TOLERANCE)

            try:
                return float(hot_tolerance)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._hot_tolerance_template,
                    e,
                )

        return float(DEFAULT_HOT_TOLERANCE)

    async def _async_turn_on(self, reason):
        _LOGGER.info(
            "%s: %s - Turning on switch %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service = SERVICE_TURN_ON if not self._inverted else SERVICE_TURN_OFF
        await self._hass.services.async_call(
            HA_DOMAIN,
            service,
            {ATTR_ENTITY_ID: self._target_entity_id},
            context=self._context,
        )

    async def _async_turn_off(self, reason):
        _LOGGER.info(
            "%s: %s - Turning off switch %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service = SERVICE_TURN_OFF if not self._inverted else SERVICE_TURN_ON
        await self._hass.services.async_call(
            HA_DOMAIN,
            service,
            {ATTR_ENTITY_ID: self._target_entity_id},
            context=self._context,
        )

    def _is_on(self):
        return self._hass.states.is_state(
            self._target_entity_id, STATE_ON if not self._inverted else STATE_OFF
        )

    async def _async_start(self, cur_temp, target_temp) -> bool:
        return True

    async def _async_stop(self):
        await self._async_turn_off(reason=REASON_THERMOSTAT_STOP)

    async def _async_ensure_not_running(self):
        if self._is_on():
            await self._async_turn_off(REASON_THERMOSTAT_NOT_RUNNING)

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        # If the `force` argument is True, we
        # ignore `min_cycle_duration`.
        if not force and reason == REASON_KEEP_ALIVE and self._min_cycle_duration:
            if self._is_on():
                current_state = STATE_ON
            else:
                current_state = HVACMode.OFF
            try:
                long_enough = condition.state(
                    self._hass,
                    self._target_entity_id,
                    current_state,
                    self._min_cycle_duration,
                )
            except ConditionError:
                long_enough = False

            if not long_enough:
                return

        too_cold = cur_temp <= target_temp - self.cold_tolerance
        too_hot = cur_temp >= target_temp + self.hot_tolerance

        need_turn_on = (too_hot and self._mode == HVACMode.COOL) or (
            too_cold and self._mode == HVACMode.HEAT
        )

        need_turn_off = (too_cold and self._mode == HVACMode.COOL) or (
            too_hot and self._mode == HVACMode.HEAT
        )

        _LOGGER.debug(
            "%s: %s - too_hot: %s, too_cold: %s, need_turn_on: %s, need_turn_off: %s, is on: %s, cur: %s, target: %s, cold_tolerance: %s, hot_tolerance: %s (%s)",
            self._thermostat_entity_id,
            self.name,
            too_hot,
            too_cold,
            need_turn_on,
            need_turn_off,
            self._is_on(),
            cur_temp,
            target_temp,
            self.cold_tolerance,
            self.hot_tolerance,
            reason,
        )

        if self._is_on():
            if need_turn_off:
                await self._async_turn_off(reason=reason)
            elif reason == REASON_KEEP_ALIVE:
                # The time argument is passed only in keep-alive case
                await self._async_turn_on(reason=reason)
        elif need_turn_on:
            await self._async_turn_on(reason=reason)
        elif reason == REASON_KEEP_ALIVE:
            await self._async_turn_off(reason=reason)
