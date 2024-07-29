"""Thermostat presets dealing classes."""

import logging

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_NONE,
    PRESET_SLEEP,
    HVACMode,
)
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template

from ..const import (
    DEFAULT_PRESET_AUTO_TEMP_DELTA,
    PRESET_NONE_HVAC_MODE,
    PRESET_NONE_TARGET_TEMP,
    PRESET_NONE_TARGET_TEMP_HIGH,
    PRESET_NONE_TARGET_TEMP_LOW,
)

_LOGGER = logging.getLogger(__name__)


class Preset:
    """Preset class."""

    def __init__(self, preset_config: dict) -> None:
        """Initialize the preset."""
        self._temp_delta_template: Template = preset_config.get("temp_delta")
        self._heat_delta_template: Template = preset_config.get("heat_delta")
        self._cool_delta_template: Template = preset_config.get("cool_delta")
        self._target_temp_template: Template = preset_config.get("target_temp")
        self._heat_target_temp_template: Template = preset_config.get(
            "heat_target_temp"
        )
        self._cool_target_temp_template: Template = preset_config.get(
            "cool_target_temp"
        )

    @property
    def _temp_delta(self) -> float | None:
        if self._temp_delta_template is not None:
            try:
                temp_delta = self._temp_delta_template.async_render(parse_result=False)
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._temp_delta_template,
                    e,
                )
                return None

            try:
                return float(temp_delta)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._temp_delta_template,
                    e,
                )

    @property
    def _heat_delta(self) -> float | None:
        if self._heat_delta_template is not None:
            try:
                heat_delta = self._heat_delta_template.async_render(parse_result=False)
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._heat_delta_template,
                    e,
                )
                return None

            try:
                return float(heat_delta)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._heat_delta_template,
                    e,
                )

    @property
    def _cool_delta(self) -> float | None:
        if self._cool_delta_template is not None:
            try:
                cool_delta = self._cool_delta_template.async_render(parse_result=False)
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._cool_delta_template,
                    e,
                )
                return None

            try:
                return float(cool_delta)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._cool_delta_template,
                    e,
                )

    @property
    def _target_temp(self) -> float | None:
        if self._target_temp_template is not None:
            try:
                target_temp = self._target_temp_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._target_temp_template,
                    e,
                )
                return None

            try:
                return float(target_temp)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._target_temp_template,
                    e,
                )

    @property
    def _heat_target_temp(self) -> float | None:
        if self._heat_target_temp_template is not None:
            try:
                heat_target_temp = self._heat_target_temp_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._heat_target_temp_template,
                    e,
                )
                return None

            try:
                return float(heat_target_temp)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._heat_target_temp_template,
                    e,
                )

    @property
    def _cool_target_temp(self) -> float | None:
        if self._cool_target_temp_template is not None:
            try:
                cool_target_temp = self._cool_target_temp_template.async_render(
                    parse_result=False
                )
            except (TemplateError, TypeError) as e:
                _LOGGER.warning(
                    "Unable to render template value: %s.\nError: %s",
                    self._cool_target_temp_template,
                    e,
                )
                return None

            try:
                return float(cool_target_temp)
            except ValueError as e:
                _LOGGER.warning(
                    "Unable to convert template value to float: %s.\nError: %s",
                    self._cool_target_temp_template,
                    e,
                )

    def get_hvac_mode(self, current_hvac_mode):
        """Return preset HVAC mode according to preset config."""
        if (
            self._temp_delta is not None
            or None not in (self._heat_delta, self._cool_delta)
            or self._target_temp is not None
        ):
            return current_hvac_mode

        if current_hvac_mode in (HVACMode.AUTO, HVACMode.HEAT_COOL):
            if self._heat_target_temp is None and self._cool_target_temp is not None:
                return HVACMode.COOL
            if self._heat_target_temp is not None and self._cool_target_temp is None:
                return HVACMode.HEAT
            return current_hvac_mode

        if (
            current_hvac_mode == HVACMode.HEAT
            and self._heat_target_temp is None
            and self._cool_target_temp is not None
        ):
            return HVACMode.COOL
        if (
            current_hvac_mode == HVACMode.COOL
            and self._heat_target_temp is None
            and self._cool_target_temp is not None
        ):
            return HVACMode.HEAT

        return current_hvac_mode

    def get_target_temp(self, current_hvac_mode, current_target_temp) -> float:
        """Return new target temp according to preset config."""
        if self._temp_delta is not None:
            return current_target_temp + self._temp_delta

        if current_hvac_mode == HVACMode.COOL and self._cool_delta is not None:
            return current_target_temp + self._cool_delta

        if current_hvac_mode == HVACMode.HEAT and self._heat_delta is not None:
            return current_target_temp + self._heat_delta

        if current_hvac_mode == HVACMode.COOL and self._cool_target_temp is not None:
            return self._cool_target_temp

        if current_hvac_mode == HVACMode.HEAT and self._heat_target_temp is not None:
            return self._heat_target_temp

        if current_hvac_mode == HVACMode.AUTO and None not in (
            self._heat_target_temp,
            self._cool_target_temp,
        ):
            return current_target_temp

        if self._target_temp is not None:
            return self._target_temp

        return current_target_temp

    def get_target_temp_low(self, current_target_temp_low) -> float:
        """Return new low target temp according to preset config."""
        if self._temp_delta is not None:
            return current_target_temp_low + self._temp_delta

        if self._heat_delta is not None:
            return current_target_temp_low + self._heat_delta

        if self._heat_target_temp is not None:
            return self._heat_target_temp

        if self._target_temp is not None:
            return self._target_temp

        return current_target_temp_low

    def get_target_temp_high(self, current_target_temp_high: float) -> float:
        """Return new high target temp according to preset config."""
        if self._temp_delta is not None:
            return current_target_temp_high + self._temp_delta

        if self._cool_delta is not None:
            return current_target_temp_high + self._cool_delta

        if self._cool_target_temp is not None:
            return self._cool_target_temp

        if self._target_temp is not None:
            return self._target_temp

        return current_target_temp_high

    def get_auto_heat_delta(self) -> float:
        """Return auto mode heat delta according to preset config."""
        if self._heat_delta is not None:
            return self._heat_delta
        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    def get_auto_cool_delta(self) -> float:
        """Return auto mode cool delta according to preset config."""
        if self._cool_delta is not None:
            return self._cool_delta
        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    def get_auto_heat_target(self) -> float | None:
        """Return auto mode heat delta according to preset config."""
        if None not in (self._heat_target_temp, self._cool_target_temp):
            return self._heat_target_temp

    def get_auto_cool_target(self) -> float | None:
        """Return auto mode cool delta according to preset config."""
        if None not in (self._heat_target_temp, self._cool_target_temp):
            return self._cool_target_temp


class PresetController:
    """Coordinator for presets if available."""

    def __init__(self, presets) -> None:
        """Initialize the coordinator."""
        self._preset: Preset | None = None
        self._preset_sleep: Preset | None = None
        self._preset_away: Preset | None = None
        self._preset_eco: Preset | None = None
        self._preset_mode: str = PRESET_NONE
        self._preset_modes = [PRESET_NONE]
        self._saved_hvac_mode: HVACMode | None = None
        self._saved_target_temp: float = None
        self._saved_target_temp_low: float = None
        self._saved_target_temp_high: float = None

        if presets.get(PRESET_SLEEP) is not None:
            self._preset_sleep = Preset(presets.get(PRESET_SLEEP))
            self._preset_modes.append(PRESET_SLEEP)
        if presets.get(PRESET_AWAY) is not None:
            self._preset_away = Preset(presets.get(PRESET_AWAY))
            self._preset_modes.append(PRESET_AWAY)
        if presets.get(PRESET_ECO) is not None:
            self._preset_eco = Preset(presets.get(PRESET_ECO))
            self._preset_modes.append(PRESET_ECO)

    @property
    def preset_mode(self):
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return self._preset_modes

    def set_preset(self, preset_mode) -> None:
        """Set preset."""
        if preset_mode == PRESET_SLEEP:
            self._preset_mode = PRESET_SLEEP
            self._preset = self._preset_sleep
        elif preset_mode == PRESET_AWAY:
            self._preset_mode = PRESET_AWAY
            self._preset = self._preset_away
        elif preset_mode == PRESET_ECO:
            self._preset_mode = PRESET_ECO
            self._preset = self._preset_eco
        else:
            self._preset_mode = PRESET_NONE
            self._preset = None

    def get_saved(
        self,
        hvac_mode: HVACMode,
        target_temp: float,
        target_temp_low: float,
        target_temp_high: float,
    ) -> dict:
        """Get saved parameters state dict."""
        self._saved_hvac_mode = hvac_mode
        self._saved_target_temp = target_temp
        self._saved_target_temp_low = target_temp_low
        self._saved_target_temp_high = target_temp_high

        if None not in (
            self._saved_hvac_mode,
            self._saved_target_temp,
            self._saved_target_temp_low,
            self._saved_target_temp_high,
        ):
            return {
                PRESET_NONE_HVAC_MODE: self._saved_hvac_mode,
                PRESET_NONE_TARGET_TEMP: self._saved_target_temp,
                PRESET_NONE_TARGET_TEMP_LOW: self._saved_target_temp_low,
                PRESET_NONE_TARGET_TEMP_HIGH: self._saved_target_temp_high,
            }

    def reset_saved(self) -> None:
        """Reset all saved parameters after falling back from preset."""
        self._saved_hvac_mode = None
        self._saved_target_temp = None
        self._saved_target_temp_low = None
        self._saved_target_temp_high = None

    def get_hvac_mode(self, hvac_mode: HVACMode) -> HVACMode | None:
        """Return current preset HVAC mode."""
        if self._preset is None:
            if self._saved_hvac_mode is not None:
                return self._saved_hvac_mode
            return hvac_mode

        if self._saved_hvac_mode:
            return self._preset.get_hvac_mode(self._saved_hvac_mode)

        return self._preset.get_hvac_mode(hvac_mode)

    def get_target_temp(self, hvac_mode: HVACMode, target_temp: float) -> float | None:
        """Return current preset new target temp."""
        if self._preset is None:
            if self._saved_target_temp is not None:
                return self._saved_target_temp
            return target_temp

        if self._saved_target_temp:
            return self._preset.get_target_temp(hvac_mode, self._saved_target_temp)

        return self._preset.get_target_temp(hvac_mode, target_temp)

    def get_target_temp_low(self, target_temp_low: float) -> float | None:
        """Return current preset new low target temp."""
        if self._preset is None:
            if self._saved_target_temp_low is not None:
                return self._saved_target_temp_low
            return target_temp_low

        if self._saved_target_temp_low:
            return self._preset.get_target_temp_low(self._saved_target_temp_low)

        return self._preset.get_target_temp_low(target_temp_low)

    def get_target_temp_high(self, target_temp_high: float) -> float | None:
        """Return current preset new high target temp."""
        if self._preset is None:
            if self._saved_target_temp_high is not None:
                return self._saved_target_temp_high
            return target_temp_high

        if self._saved_target_temp_high:
            return self._preset.get_target_temp_high(self._saved_target_temp_high)

        return self._preset.get_target_temp_high(target_temp_high)

    @property
    def auto_heat_delta(self) -> float:
        """Return current preset new auto heat delta."""
        if self._preset is not None:
            return self._preset.get_auto_heat_delta()

        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    @property
    def auto_cool_delta(self) -> float:
        """Return current preset new auto cool delta."""
        if self._preset is not None:
            return self._preset.get_auto_cool_delta()

        return DEFAULT_PRESET_AUTO_TEMP_DELTA

    @property
    def auto_heat_target(self) -> float | None:
        """Return current preset new auto heat target temperature."""
        if self._preset is not None:
            return self._preset.get_auto_heat_target()

    @property
    def auto_cool_target(self) -> float | None:
        """Return current preset new auto cool target temperature."""
        if self._preset is not None:
            return self._preset.get_auto_cool_target()