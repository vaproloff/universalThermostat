"""Support for climate controllers with PID."""

from datetime import timedelta
import logging

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, SERVICE_TURN_OFF
from homeassistant.core import State
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import RenderInfo, Template

from ..const import (
    REASON_KEEP_ALIVE,
    REASON_THERMOSTAT_NOT_RUNNING,
    REASON_THERMOSTAT_STOP,
)
from . import AbstractPidController

_LOGGER = logging.getLogger(__name__)


class ClimatePidController(AbstractPidController):
    """PID climate controller class."""

    def __init__(
        self,
        name: str,
        mode,
        target_entity_id: str,
        pid_kp_template: Template,
        pid_ki_template: Template,
        pid_kd_template: Template,
        pid_sample_period: timedelta,
        inverted: bool,
        keep_alive: timedelta | None,
        output_min_template: Template,
        output_max_template: Template,
    ) -> None:
        """Initialize the controller."""
        super().__init__(
            name,
            mode,
            target_entity_id,
            pid_kp_template,
            pid_ki_template,
            pid_kd_template,
            pid_sample_period,
            inverted,
            keep_alive,
        )
        self._output_min_template = output_min_template
        self._output_max_template = output_max_template

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._output_min_template is not None:
            try:
                template_info: RenderInfo = (
                    self._output_min_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._output_min_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._output_max_template is not None:
            try:
                template_info: RenderInfo = (
                    self._output_max_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to get template info: %s.\nError: %s",
                    self._output_max_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    def _is_on(self):
        return self._hass.states.is_state(self._target_entity_id, self._mode)

    def _adapt_pid_output(self, value: float) -> float:
        min_output, max_output = self._get_output_limits()
        return min_output + (value * (max_output - min_output) / 100)

    def _round_to_target_precision(self, value: float) -> float:
        state: State = self._hass.states.get(self._target_entity_id)
        if not state:
            return value
        step = state.attributes.get(ATTR_TARGET_TEMP_STEP)
        return round(value / step) * step

    def _get_current_output(self):
        state = self._hass.states.get(self._target_entity_id)
        if state:
            return float(state.attributes.get(ATTR_TEMPERATURE))
        return None

    async def _async_turn_on(self, reason=None):
        _LOGGER.debug(
            "%s: %s - Setting HVAC mode to %s",
            self._thermostat_entity_id,
            self.name,
            self.mode,
        )
        data = {ATTR_ENTITY_ID: self._target_entity_id, ATTR_HVAC_MODE: self.mode}
        await self._hass.services.async_call(
            CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE, data, context=self._context
        )

    async def _async_turn_off(self, reason):
        _LOGGER.info(
            "%s: %s - Turning off climate %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        await self._hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self._target_entity_id},
            context=self._context,
        )

    async def _async_stop(self):
        await super()._async_stop()
        await self._async_turn_off(REASON_THERMOSTAT_STOP)

    async def _async_ensure_not_running(self):
        if self._is_on():
            await self._async_turn_off(REASON_THERMOSTAT_NOT_RUNNING)

    @property
    def _get_default_output_min(self) -> float | None:
        """Returns Default PID Output minimum value."""

        state: State = self._hass.states.get(self._target_entity_id)
        if state:
            return state.attributes.get(ATTR_MIN_TEMP)

    @property
    def output_min(self) -> float | None:
        """Returns PID Output minimum value."""

        if self._output_min_template is None:
            _LOGGER.debug(
                "PID Output minumum not provided in config. Returning Climate entity min_temp"
            )
            return self._get_default_output_min

        try:
            output_min = self._output_min_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning Climate entity min_temp",
                self._output_min_template,
                e,
            )
            return self._get_default_output_min

        try:
            output_min = float(output_min)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning Climate entity min_temp",
                output_min,
                e,
            )
            return self._get_default_output_min

        return max(output_min, self._get_default_output_min)

    @property
    def _get_default_output_max(self) -> float | None:
        """Returns Default PID Output maximum value."""

        state: State = self._hass.states.get(self._target_entity_id)
        if state:
            return state.attributes.get(ATTR_MAX_TEMP)

    @property
    def output_max(self) -> float | None:
        """Returns PID Output maximum value."""

        if self._output_max_template is None:
            _LOGGER.debug(
                "PID Output maximum not provided in config. Returning Climate entity max_temp"
            )
            return self._get_default_output_max

        try:
            output_max = self._output_max_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "Unable to render template value: %s. Error: %s. Returning Climate entity max_temp",
                self._output_max_template,
                e,
            )
            return self._get_default_output_max

        try:
            output_max = float(output_max)
        except ValueError as e:
            _LOGGER.warning(
                "Can't parse float value: %s. Error: %s. Returning Climate entity max_temp",
                output_max,
                e,
            )
            return self._get_default_output_max

        return min(output_max, self._get_default_output_max)

    def _get_output_limits(self) -> tuple[float | None, float | None]:
        if self.mode == HVACMode.COOL:
            return self.output_max, self.output_min
        return self.output_min, self.output_max

    async def _apply_output(self, output: float):
        await self._hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: self._target_entity_id, ATTR_TEMPERATURE: output},
            context=self._context,
        )

    async def _async_control(
        self,
        cur_temp,
        target_temp,
        time=None,
        force=False,
        reason=None,
    ):
        if not self._is_on() or reason == REASON_KEEP_ALIVE:
            await self._async_turn_on(reason=reason)
        await super()._async_control(
            cur_temp,
            target_temp,
            time,
            force,
            reason,
        )
