"""Adds config flow (UI flow) for Universal THermostat component."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import split_entity_id
from homeassistant.helpers import selector

from . import DOMAIN
from .config_schema import SUPPORTED_TARGET_DOMAINS, SUPPORTED_WINDOW_DOMAINS
from .const import (
    ATTR_TIMEOUT,
    CONF_AUTO_MODE_DISABLED,
    CONF_CLIMATE_TEMP_DELTA,
    CONF_COLD_TOLERANCE,
    CONF_COOLER,
    CONF_HEAT_COOL_DISABLED,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_IGNORE_WINDOWS,
    CONF_INVERTED,
    CONF_KEEP_ALIVE,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_PID_MAX,
    CONF_PID_MIN,
    CONF_PID_SAMPLE_PERIOD,
    CONF_PID_SWITCH_ENTITY_ID,
    CONF_PID_SWITCH_INVERTED,
    CONF_PRESET_COOL_DELTA,
    CONF_PRESET_COOL_TARGET_TEMP,
    CONF_PRESET_HEAT_DELTA,
    CONF_PRESET_HEAT_TARGET_TEMP,
    CONF_PRESET_TARGET_TEMP,
    CONF_PRESET_TEMP_DELTA,
    CONF_PRESETS,
    CONF_PWM_SWITCH_PERIOD,
    CONF_SENSOR,
    CONF_WINDOWS,
    DEFAULT_CLIMATE_TEMP_DELTA,
    DEFAULT_COLD_TOLERANCE,
    DEFAULT_HOT_TOLERANCE,
    DEFAULT_NAME,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
)


class UniversalThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Universal Thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow lifecycle properties."""
        self._draft: dict[str, Any] = {
            CONF_NAME: None,
            CONF_SENSOR: None,
            CONF_MIN_TEMP: None,
            CONF_MAX_TEMP: None,
            CONF_HEATER: [],
            CONF_COOLER: [],
            CONF_HEAT_COOL_DISABLED: False,
            CONF_AUTO_MODE_DISABLED: False,
            CONF_WINDOWS: [],
            CONF_PRESETS: {},
        }

        self._current_controller_type: str | None = None
        self._current_entity_id: str | None = None
        self._current_domain: str | None = None
        self._current_controller: dict[str, Any] = {}

        self._current_window: dict[str, Any] = {}

        self._current_preset_name: str | None = None
        self._current_preset_type: str | None = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            min_temp = user_input[CONF_MIN_TEMP]
            max_temp = user_input[CONF_MAX_TEMP]

            if min_temp >= max_temp:
                errors["base"] = "invalid_temp_range"
            else:
                self._draft[CONF_NAME] = user_input[CONF_NAME]
                self._draft[CONF_SENSOR] = user_input[CONF_SENSOR]
                self._draft[CONF_MIN_TEMP] = user_input[CONF_MIN_TEMP]
                self._draft[CONF_MAX_TEMP] = user_input[CONF_MAX_TEMP]
                return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=self._draft[CONF_NAME] or DEFAULT_NAME,
                    ): str,
                    vol.Required(
                        CONF_SENSOR, default=self._draft[CONF_SENSOR]
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=[SENSOR_DOMAIN])
                    ),
                    vol.Required(
                        CONF_MIN_TEMP, default=self._draft[CONF_MIN_TEMP] or 18.0
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-50, max=100, step=1.0)
                    ),
                    vol.Required(
                        CONF_MAX_TEMP, default=self._draft[CONF_MAX_TEMP] or 30.0
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-50, max=100, step=1.0)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_controllers_menu(
        self, user_input: dict[str, Any] | None = None
    ):
        """Show added controllers and allow adding more."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input["action"]

            if action == "add":
                return await self.async_step_controller_add()

            if not self._draft[CONF_HEATER] and not self._draft[CONF_COOLER]:
                errors["base"] = "no_controllers"
            elif self._draft["heater"] and self._draft["cooler"]:
                return await self.async_step_features()
            else:
                return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="controllers_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["add", "done"],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="controllers_menu_selector",
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                "heaters": self._format_entities(self._draft[CONF_HEATER]),
                "coolers": self._format_entities(self._draft[CONF_COOLER]),
            },
        )

    async def async_step_controller_add(self, user_input: dict[str, Any] | None = None):
        """Add a heater or cooler entity."""
        if user_input is not None:
            entity_id = user_input[CONF_ENTITY_ID]
            self._current_controller_type = user_input["controller_type"]
            self._current_entity_id = entity_id
            self._current_domain = split_entity_id(entity_id)[0]
            self._current_controller = {CONF_ENTITY_ID: entity_id}

            if self._current_domain in (
                SWITCH_DOMAIN,
                INPUT_BOOLEAN_DOMAIN,
                CLIMATE_DOMAIN,
            ):
                return await self.async_step_controller_mode()

            return await self.async_step_controller_config_number_pid()

        return self.async_show_form(
            step_id="controller_add",
            data_schema=vol.Schema(
                {
                    vol.Required("controller_type"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[CONF_HEATER, CONF_COOLER],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="controller_add_selector",
                        )
                    ),
                    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=SUPPORTED_TARGET_DOMAINS)
                    ),
                }
            ),
        )

    async def async_step_controller_mode(
        self, user_input: dict[str, Any] | None = None
    ):
        """Choose controller mode depending on entity domain."""
        if user_input is not None:
            mode = user_input["controller_mode"]

            if self._current_domain in (SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN):
                if mode == "switch":
                    return await self.async_step_controller_config_switch()
                return await self.async_step_controller_config_pwm_switch()

            if self._current_domain == CLIMATE_DOMAIN:
                if mode == "switch":
                    return await self.async_step_controller_config_climate()
                return await self.async_step_controller_config_climate_pid()

        options: list[dict[str, str]] = []
        if self._current_domain in (SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN):
            options = ["switch", "pwm_switch"]
        elif self._current_domain == CLIMATE_DOMAIN:
            options = ["climate_switch", "climate_pid"]

        return self.async_show_form(
            step_id="controller_mode",
            data_schema=vol.Schema(
                {
                    vol.Required("controller_mode"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="controller_mode_selector",
                        )
                    )
                }
            ),
            description_placeholders={
                "current_entity_id": self._current_entity_id,
                "controller_type": self._current_controller_type,
            },
        )

    async def async_step_controller_config_switch(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure a simple switch controller."""
        if user_input is not None:
            self._append_current_controller(user_input)
            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_config_switch",
            data_schema=vol.Schema(
                {
                    **self._common_controller_schema(),
                    vol.Required(
                        CONF_COLD_TOLERANCE, default=DEFAULT_COLD_TOLERANCE
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=20, step=0.1)
                    ),
                    vol.Required(
                        CONF_HOT_TOLERANCE, default=DEFAULT_HOT_TOLERANCE
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=20, step=0.1)
                    ),
                    vol.Optional(CONF_MIN_DUR): selector.DurationSelector(),
                }
            ),
            description_placeholders={
                "current_entity_id": self._current_entity_id,
                "controller_type": self._current_controller_type,
            },
        )

    async def async_step_controller_config_pwm_switch(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure a PWM switch PID controller."""
        if user_input is not None:
            self._append_current_controller(user_input)
            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_config_pwm_switch",
            data_schema=vol.Schema(
                {
                    **self._common_controller_schema(),
                    vol.Required(
                        CONF_PID_KP, default=DEFAULT_PID_KP
                    ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
                    vol.Required(
                        CONF_PID_KI, default=DEFAULT_PID_KI
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.01)
                    ),
                    vol.Required(
                        CONF_PID_KD, default=DEFAULT_PID_KD
                    ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
                    vol.Optional(CONF_PID_SAMPLE_PERIOD): selector.DurationSelector(),
                    vol.Required(CONF_PWM_SWITCH_PERIOD): selector.DurationSelector(),
                }
            ),
            description_placeholders={
                "current_entity_id": self._current_entity_id,
                "controller_type": self._current_controller_type,
            },
        )

    async def async_step_controller_config_climate(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure a climate switch controller."""
        if user_input is not None:
            self._append_current_controller(user_input)
            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_config_climate",
            data_schema=vol.Schema(
                {
                    **self._common_controller_schema(),
                    vol.Required(
                        CONF_COLD_TOLERANCE, default=DEFAULT_COLD_TOLERANCE
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=20, step=0.1)
                    ),
                    vol.Required(
                        CONF_HOT_TOLERANCE, default=DEFAULT_HOT_TOLERANCE
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=20, step=0.1)
                    ),
                    vol.Required(
                        CONF_CLIMATE_TEMP_DELTA, default=DEFAULT_CLIMATE_TEMP_DELTA
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
                    ),
                    vol.Optional(CONF_MIN_DUR): selector.DurationSelector(),
                }
            ),
            description_placeholders={
                "current_entity_id": self._current_entity_id,
                "controller_type": self._current_controller_type,
            },
        )

    async def async_step_controller_config_climate_pid(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure a climate PID controller."""
        if user_input is not None:
            self._append_current_controller(user_input)
            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_config_climate_pid",
            data_schema=vol.Schema(
                {
                    **self._common_controller_schema(),
                    vol.Required(
                        CONF_PID_KP, default=DEFAULT_PID_KP
                    ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
                    vol.Required(
                        CONF_PID_KI, default=DEFAULT_PID_KI
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.01)
                    ),
                    vol.Required(
                        CONF_PID_KD, default=DEFAULT_PID_KD
                    ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
                    vol.Optional(CONF_PID_SAMPLE_PERIOD): selector.DurationSelector(),
                    vol.Optional(CONF_PID_MIN): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                    vol.Optional(CONF_PID_MAX): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                }
            ),
            description_placeholders={
                "current_entity_id": self._current_entity_id,
                "controller_type": self._current_controller_type,
            },
        )

    async def async_step_controller_config_number_pid(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure a number/input_number PID controller."""
        if user_input is not None:
            self._append_current_controller(user_input)
            return await self.async_step_controllers_menu()

        return self.async_show_form(
            step_id="controller_config_number_pid",
            data_schema=vol.Schema(
                {
                    **self._common_controller_schema(),
                    vol.Required(
                        CONF_PID_KP, default=DEFAULT_PID_KP
                    ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
                    vol.Required(
                        CONF_PID_KI, default=DEFAULT_PID_KI
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.01)
                    ),
                    vol.Required(
                        CONF_PID_KD, default=DEFAULT_PID_KD
                    ): selector.NumberSelector(selector.NumberSelectorConfig(step=0.1)),
                    vol.Optional(CONF_PID_SAMPLE_PERIOD): selector.DurationSelector(),
                    vol.Optional(CONF_PID_MIN): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                    vol.Optional(CONF_PID_MAX): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                    vol.Optional(CONF_PID_SWITCH_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=[SWITCH_DOMAIN, INPUT_BOOLEAN_DOMAIN]
                        )
                    ),
                    vol.Required(
                        CONF_PID_SWITCH_INVERTED, default=False
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "current_entity_id": self._current_entity_id,
                "controller_type": self._current_controller_type,
            },
        )

    async def async_step_features(self, user_input: dict[str, Any] | None = None):
        """Configure common thermostat features after controllers are added."""
        if user_input is not None:
            self._draft[CONF_HEAT_COOL_DISABLED] = user_input[CONF_HEAT_COOL_DISABLED]
            self._draft[CONF_HEAT_COOL_DISABLED] = user_input[CONF_HEAT_COOL_DISABLED]
            return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="features",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HEAT_COOL_DISABLED,
                        default=self._draft[CONF_HEAT_COOL_DISABLED],
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_AUTO_MODE_DISABLED,
                        default=self._draft[CONF_AUTO_MODE_DISABLED],
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_windows_menu(self, user_input: dict[str, Any] | None = None):
        """Show added windows and allow adding more."""
        if user_input is not None:
            if user_input["action"] == "add":
                return await self.async_step_window_add()
            return await self.async_step_presets_menu()

        return self.async_show_form(
            step_id="windows_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["add", "done"],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="windows_menu_selector",
                        )
                    )
                }
            ),
            description_placeholders={
                CONF_WINDOWS: self._format_entities(self._draft[CONF_WINDOWS])
            },
        )

    async def async_step_window_add(self, user_input: dict[str, Any] | None = None):
        """Add a window entity."""
        if user_input is not None:
            self._draft[CONF_WINDOWS].append(user_input)
            return await self.async_step_windows_menu()

        return self.async_show_form(
            step_id="window_add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=SUPPORTED_WINDOW_DOMAINS)
                    ),
                    vol.Required(
                        CONF_INVERTED, default=False
                    ): selector.BooleanSelector(),
                    vol.Optional(ATTR_TIMEOUT): selector.DurationSelector(),
                }
            ),
        )

    async def async_step_presets_menu(self, user_input: dict[str, Any] | None = None):
        """Show added presets and allow adding more."""
        if user_input is not None:
            if user_input["action"] == "add":
                return await self.async_step_preset_add()
            return await self.async_step_review()

        return self.async_show_form(
            step_id="presets_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["add", "done"],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="presets_menu_selector",
                        )
                    )
                }
            ),
            description_placeholders={CONF_PRESETS: self._format_presets()},
        )

    async def async_step_preset_add(self, user_input: dict[str, Any] | None = None):
        """Add a preset."""
        errors: dict[str, str] = {}

        if user_input is not None:
            preset_name = user_input["preset_name"]
            preset_type = user_input["preset_type"]

            if preset_name in self._draft["presets"]:
                errors["preset_name"] = "preset_exists"
            else:
                self._current_preset_name = preset_name
                self._current_preset_type = preset_type

                if preset_type == "temp_delta":
                    return await self.async_step_preset_config_temp_delta()
                if preset_type == "heat_cool_deltas":
                    return await self.async_step_preset_config_heat_cool_delta()
                return await self.async_step_preset_config_target_temp()

        return self.async_show_form(
            step_id="preset_add",
            data_schema=vol.Schema(
                {
                    vol.Required("preset_name"): str,
                    vol.Required("preset_type"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["temp_delta", "heat_cool_deltas", "target_temps"],
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="preset_add_selector",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_preset_config_temp_delta(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure temp_delta preset."""
        if user_input is not None:
            self._draft[CONF_PRESETS][self._current_preset_name] = {
                "temp_delta": user_input["temp_delta"]
            }
            self._reset_current_preset()
            return await self.async_step_presets_menu()

        return self.async_show_form(
            step_id="preset_config_temp_delta",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRESET_TEMP_DELTA): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
                    )
                }
            ),
            description_placeholders={"current_preset": self._current_preset_name},
        )

    async def async_step_preset_config_heat_cool_delta(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure heat/cool delta preset."""
        if user_input is not None:
            self._draft[CONF_PRESETS][self._current_preset_name] = {
                CONF_PRESET_HEAT_DELTA: user_input[CONF_PRESET_HEAT_DELTA],
                CONF_PRESET_COOL_DELTA: user_input[CONF_PRESET_COOL_DELTA],
            }
            self._reset_current_preset()
            return await self.async_step_presets_menu()

        return self.async_show_form(
            step_id="preset_config_heat_cool_delta",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRESET_HEAT_DELTA): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
                    ),
                    vol.Required(CONF_PRESET_COOL_DELTA): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=-20, max=20, step=0.1)
                    ),
                }
            ),
            description_placeholders={"current_preset": self._current_preset_name},
        )

    async def async_step_preset_config_target_temp(
        self, user_input: dict[str, Any] | None = None
    ):
        """Configure target temperature preset."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                key: value for key, value in user_input.items() if value is not None
            }

            if not data:
                errors["base"] = "preset_target_required"
            else:
                self._draft[CONF_PRESETS][self._current_preset_name] = data
                self._reset_current_preset()
                return await self.async_step_presets_menu()

        return self.async_show_form(
            step_id="preset_config_target_temp",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PRESET_TARGET_TEMP): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                    vol.Optional(CONF_PRESET_HEAT_TARGET_TEMP): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                    vol.Optional(CONF_PRESET_COOL_TARGET_TEMP): selector.NumberSelector(
                        selector.NumberSelectorConfig(step=0.1)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"current_preset": self._current_preset_name},
        )

    async def async_step_review(self, user_input: dict[str, Any] | None = None):
        """Final review step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not self._draft[CONF_HEATER] and not self._draft[CONF_COOLER]:
                errors["base"] = "no_controllers"
            else:
                return self.async_create_entry(
                    title=self._draft[CONF_NAME],
                    data=self._draft,
                )

        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "sensor": self._draft[CONF_SENSOR],
                "heaters": len(self._draft[CONF_HEATER]),
                "coolers": len(self._draft[CONF_COOLER]),
                "windows": len(self._draft[CONF_COOLER]),
                "presets": len(self._draft[CONF_COOLER]),
            },
        )

    def _common_controller_schema(self) -> dict:
        """Return common controller fields."""
        return {
            vol.Required(CONF_INVERTED, default=False): selector.BooleanSelector(),
            vol.Required(
                CONF_IGNORE_WINDOWS, default=False
            ): selector.BooleanSelector(),
            vol.Optional(CONF_KEEP_ALIVE): selector.DurationSelector(),
        }

    def _append_current_controller(self, data: dict[str, Any]) -> None:
        """Append current controller to heater/cooler draft."""
        controller = dict(self._current_controller)
        controller.update(data)
        self._draft[self._current_controller_type].append(controller)
        self._reset_current_controller()

    def _reset_current_controller(self) -> None:
        """Reset temporary controller state."""
        self._current_controller_type = None
        self._current_entity_id = None
        self._current_domain = None
        self._current_controller = {}

    def _reset_current_preset(self) -> None:
        """Reset temporary preset state."""
        self._current_preset_name = None
        self._current_preset_type = None

    def _format_entities(self, items: list[dict[str, Any]]) -> str:
        """Format entity list for descriptions."""
        if not items:
            return "—"
        return "\n".join(f"- {item['entity_id']}" for item in items)

    def _format_presets(self) -> str:
        """Format presets list for descriptions."""
        if not self._draft["presets"]:
            return "—"
        return "\n".join(f"- {name}" for name in self._draft["presets"])
