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
        self._min_output_template = output_min_template
        self._max_output_template = output_max_template

    @property
    def _min_output(self) -> float | None:
        """Returns PID Output minimum value."""
        if self._min_output_template is None:
            _LOGGER.warning(
                "%s - %s: min_output template is none. Return default: %s",
                self._thermostat_entity_id,
                self.name,
                self._default_min_output,
            )
            return self._default_min_output

        try:
            min_output = self._min_output_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "%s - %s: unable to render min_output template: %s. Return default: %s. Error: %s",
                self._thermostat_entity_id,
                self.name,
                self._min_output_template,
                self._default_min_output,
                e,
            )
            return self._default_min_output

        try:
            min_output = float(min_output)
        except ValueError as e:
            _LOGGER.warning(
                "%s - %s: unable to convert min_output template value to float: %s. Return default: %s. Error: %s",
                self._thermostat_entity_id,
                self.name,
                min_output,
                self._default_min_output,
                e,
            )
            return self._default_min_output

        return max(min_output, self._default_min_output)

    @property
    def _default_min_output(self) -> float | None:
        """Returns Default PID Output minimum value."""
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            try:
                return float(state.attributes.get(ATTR_MIN_TEMP))
            except ValueError as e:
                _LOGGER.warning(
                    "%s - %s: unable to convert target entity min_temp to float: %s. Error: %s",
                    self._thermostat_entity_id,
                    self.name,
                    state.attributes.get(ATTR_MIN_TEMP),
                    e,
                )

        _LOGGER.warning(
            "%s - %s: unable to get target entity min_temp. Return default: %s",
            self._thermostat_entity_id,
            self.name,
            self._thermostat.min_temp,
        )
        return self._thermostat.min_temp

    @property
    def _max_output(self) -> float | None:
        """Returns PID Output maximum value."""
        if self._max_output_template is None:
            _LOGGER.warning(
                "%s - %s: max_output template is none. Return default: %s",
                self._thermostat_entity_id,
                self.name,
                self._default_max_output,
            )
            return self._default_max_output

        try:
            max_output = self._max_output_template.async_render(parse_result=False)
        except (TemplateError, TypeError) as e:
            _LOGGER.warning(
                "%s - %s: unable to render max_output template: %s. Return default: %s. Error: %s",
                self._thermostat_entity_id,
                self.name,
                self._max_output_template,
                self._default_max_output,
                e,
            )
            return self._default_max_output

        try:
            max_output = float(max_output)
        except ValueError as e:
            _LOGGER.warning(
                "%s - %s: unable to convert max_output template value to float: %s. Return default: %s. Error: %s",
                self._thermostat_entity_id,
                self.name,
                max_output,
                self._default_max_output,
                e,
            )
            return self._default_max_output

        return min(max_output, self._default_max_output)

    @property
    def _default_max_output(self) -> float | None:
        """Returns Default PID Output maximum value."""
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            try:
                return float(state.attributes.get(ATTR_MAX_TEMP))
            except ValueError as e:
                _LOGGER.warning(
                    "%s - %s: unable to convert target entity max_temp to float: %s. Error: %s",
                    self._thermostat_entity_id,
                    self.name,
                    state.attributes.get(ATTR_MAX_TEMP),
                    e,
                )

        _LOGGER.warning(
            "%s - %s: unable to get target entity max_temp. Return default: %s",
            self._thermostat_entity_id,
            self.name,
            self._thermostat.max_temp,
        )
        return self._thermostat.max_temp

    @property
    def _is_on(self) -> bool:
        return self._hass.states.is_state(self._target_entity_id, self._mode)

    @property
    def is_active(self) -> bool:
        """Is controller entity HVAC active."""
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state is not None:
            hvac_action = state.attributes.get(ATTR_HVAC_ACTION)
            if hvac_action is not None:
                return (
                    hvac_action == HVACAction.COOLING
                    if self._mode
                    == (HVACMode.COOL if not self._inverted else HVACMode.HEAT)
                    else hvac_action == HVACAction.HEATING
                )

        return super().is_active

    def get_used_template_entity_ids(self) -> list[str]:
        """Add used template entities to track state change."""
        tracked_entities = super().get_used_template_entity_ids()

        if self._min_output_template is not None:
            try:
                template_info: RenderInfo = (
                    self._min_output_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "%s - %s: unable to get output_min template info: %s. Error: %s",
                    self._thermostat_entity_id,
                    self.name,
                    self._min_output_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        if self._max_output_template is not None:
            try:
                template_info: RenderInfo = (
                    self._max_output_template.async_render_to_info()
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "%s - %s: unable to get output_max template info: %s. Error: %s",
                    self._thermostat_entity_id,
                    self.name,
                    self._max_output_template,
                    e,
                )
            else:
                tracked_entities.extend(template_info.entities)

        return tracked_entities

    def _adapt_pid_output(self, value: float) -> float:
        min_output, max_output = self._get_output_limits()
        return min_output + (value * (max_output - min_output) / 100)

    def _round_to_target_precision(self, value: float) -> float:
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            step = state.attributes.get(ATTR_TARGET_TEMP_STEP)
            if step:
                try:
                    step = float(step)
                except ValueError as e:
                    _LOGGER.warning(
                        "%s - %s: unable to convert climate temp_step value to float: %s. Return default: %s. Error: %s",
                        self._thermostat_entity_id,
                        self.name,
                        step,
                        value,
                        e,
                    )
                else:
                    return round(value / step) * step

        return value

    def _get_current_output(self):
        state: State | None = self._hass.states.get(self._target_entity_id)
        if state:
            try:
                return float(state.attributes.get(ATTR_TEMPERATURE))
            except ValueError as e:
                _LOGGER.warning(
                    "%s - %s: unable to convert target_temp value to float: %s. Error: %s",
                    self._thermostat_entity_id,
                    self.name,
                    state.attributes.get(ATTR_TEMPERATURE),
                    e,
                )

    async def _async_turn_on(self, reason=None):
        _LOGGER.debug(
            "%s - %s: turning on %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service_data = {
            ATTR_ENTITY_ID: self._target_entity_id,
            ATTR_HVAC_MODE: self._mode,
        }
        await self._hass.services.async_call(
            domain=CLIMATE_DOMAIN,
            service=SERVICE_SET_HVAC_MODE,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_turn_off(self, reason):
        _LOGGER.debug(
            "%s - %s: turning off %s (%s)",
            self._thermostat_entity_id,
            self.name,
            self._target_entity_id,
            reason,
        )

        service_data = {ATTR_ENTITY_ID: self._target_entity_id}
        await self._hass.services.async_call(
            domain=CLIMATE_DOMAIN,
            service=SERVICE_TURN_OFF,
            service_data=service_data,
            blocking=True,
            context=self._context,
        )

    async def _async_stop(self):
        await super()._async_stop()
        await self._async_turn_off(REASON_THERMOSTAT_STOP)

    async def _async_ensure_not_running(self):
        if self._is_on:
            await self._async_turn_off(REASON_THERMOSTAT_NOT_RUNNING)

    def _get_output_limits(self) -> tuple[float | None, float | None]:
        if self.mode == HVACMode.COOL:
            return self._max_output, self._min_output
        return self._min_output, self._max_output

    async def _apply_output(self, output: float):
        service_data = {
            ATTR_ENTITY_ID: self._target_entity_id,
            ATTR_TEMPERATURE: output,
        }
        await self._hass.services.async_call(
            domain=CLIMATE_DOMAIN,
            service=SERVICE_SET_TEMPERATURE,
            service_data=service_data,
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
        await super()._async_control(
            cur_temp,
            target_temp,
            time,
            force,
            reason,
        )

        if not self._is_on or reason == REASON_KEEP_ALIVE:
            await self._async_turn_on(reason=reason)
