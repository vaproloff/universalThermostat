"""Support for climate switch controllers."""

from datetime import timedelta
import logging

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import DOMAIN as HA_DOMAIN, State
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import RenderInfo, Template

from ..const import DEFAULT_CLIMATE_TEMP_DELTA
from . import SwitchController

_LOGGER = logging.getLogger(__name__)


class ClimateSwitchController(SwitchController):
    """Climate switch controller class."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        cold_tolerance_template: Template,
        hot_tolerance_template: Template,
        temp_delta_template: Template | None,
        inverted: bool,
        keep_alive: timedelta | None,
        min_cycle_duration,
    ) -> None:
        """Initialize the controller."""
        super().__init__(
            name,
            mode,
            target_entity_id,
            cold_tolerance_template,
            hot_tolerance_template,
            inverted,
            keep_alive,
            min_cycle_duration,
        )
        self._temp_delta_template = temp_delta_template

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._temp_delta_template is not None:
            try:
                template_info: RenderInfo = (
                    self._temp_delta_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._temp_delta_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    @property
    def temp_delta(self) -> float | None:
        """Returns Temperature Delta."""

        if self._temp_delta_template is not None:
            try:
                temp_delta = self._temp_delta_template.async_render(parse_result=False)
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._temp_delta_template,
                    e,
                )
                return float(DEFAULT_CLIMATE_TEMP_DELTA)

            try:
                return float(temp_delta)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._temp_delta_template,
                    e,
                )

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        await super()._async_control(
            cur_temp,
            target_temp,
            time,
            force,
            reason,
        )

        if self._is_on() and self.temp_delta is not None:
            if self.mode == HVACMode.COOL:
                target_temp -= self.temp_delta
            else:
                target_temp += self.temp_delta

            state: State = self._hass.states.get(self._target_entity_id)
            if state:
                min_target_temp = state.attributes.get(ATTR_MIN_TEMP)
                max_target_temp = state.attributes.get(ATTR_MAX_TEMP)
                if None not in (min_target_temp, max_target_temp):
                    target_temp = min(
                        max(target_temp, min_target_temp), max_target_temp
                    )

            service_data = {
                ATTR_ENTITY_ID: self._target_entity_id,
                ATTR_TEMPERATURE: target_temp,
            }

            await self._hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                service_data,
                context=self._context,
            )

    async def _async_turn_on(self, reason):
        _LOGGER.debug(
            "%s: %s - Turning on climate entity %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        hvac_mode = self.mode if not self._inverted else HVACMode.OFF
        data = {ATTR_ENTITY_ID: self._target_entity_id, ATTR_HVAC_MODE: hvac_mode}
        await self._hass.services.async_call(
            CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, data, context=self._context
        )

    async def _async_turn_off(self, reason):
        _LOGGER.debug(
            "%s: %s - Turning off climate entity %s (%s)",
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

        hvac_mode = HVACMode.OFF if not self._inverted else self.mode
        data = {ATTR_ENTITY_ID: self._target_entity_id, ATTR_HVAC_MODE: hvac_mode}
        await self._hass.services.async_call(
            CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, data, context=self._context
        )

    def _is_on(self):
        state: State = self._hass.states.get(self._target_entity_id)
        if not state:
            return False

        return state.state == self._mode
