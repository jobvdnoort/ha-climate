"""Config flow and options flow for HA Climate."""

from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BASELINE_DAYS,
    CONF_COMFORT_TIME,
    CONF_DAY_TEMP,
    CONF_FIREPLACE_CLIMATE,
    CONF_FIREPLACE_TEMP_SENSOR,
    CONF_FIREPLACE_THRESHOLD,
    CONF_GAS_PRICE,
    CONF_GAS_PRICE_ENTITY,
    CONF_GAS_SENSOR,
    CONF_HEATING_LIMIT,
    CONF_NIGHT_END,
    CONF_NIGHT_OFFSET,
    CONF_NIGHT_START,
    CONF_NIGHT_TEMP,
    CONF_OPTIMUM_START,
    CONF_OUTDOOR_SENSOR,
    CONF_ROOM_CLIMATES,
    CONF_ROOM_ID,
    CONF_ROOM_NAME,
    CONF_ROOM_SELECT,
    CONF_ROOM_USE_GLOBAL,
    CONF_ROOMS,
    DEFAULT_BASELINE_DAYS,
    DEFAULT_COMFORT_TIME,
    DEFAULT_FIREPLACE_THRESHOLD,
    DEFAULT_HEATING_LIMIT,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_OFFSET,
    DEFAULT_NIGHT_START,
    DOMAIN,
    NAME,
)

# Optional fields that can be cleared in the UI.
OPTIONAL_GENERAL = (CONF_GAS_PRICE, CONF_GAS_PRICE_ENTITY)
OPTIONAL_FIREPLACE = (CONF_FIREPLACE_CLIMATE, CONF_FIREPLACE_TEMP_SENSOR)


def _suggest(values: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a suggested value description for optional fields."""
    if values.get(key) is None:
        return {}
    return {"suggested_value": values[key]}


def _general_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_OUTDOOR_SENSOR, default=values.get(CONF_OUTDOOR_SENSOR, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.TEMPERATURE
                )
            ),
            vol.Required(
                CONF_GAS_SENSOR, default=values.get(CONF_GAS_SENSOR, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.GAS
                )
            ),
            vol.Optional(
                CONF_GAS_PRICE, description=_suggest(values, CONF_GAS_PRICE)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=10,
                    step="any",
                    unit_of_measurement="€/m³",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_GAS_PRICE_ENTITY, description=_suggest(values, CONF_GAS_PRICE_ENTITY)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number", "number"])
            ),
            vol.Required(
                CONF_HEATING_LIMIT,
                default=values.get(CONF_HEATING_LIMIT, DEFAULT_HEATING_LIMIT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=25,
                    step=0.5,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_BASELINE_DAYS,
                default=values.get(CONF_BASELINE_DAYS, DEFAULT_BASELINE_DAYS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=14,
                    max=1095,
                    step=1,
                    unit_of_measurement="d",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _night_fields(values: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(
            CONF_NIGHT_START, default=values.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)
        ): selector.TimeSelector(),
        vol.Required(
            CONF_NIGHT_END, default=values.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)
        ): selector.TimeSelector(),
        vol.Required(
            CONF_NIGHT_OFFSET, default=values.get(CONF_NIGHT_OFFSET, DEFAULT_NIGHT_OFFSET)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-10,
                max=0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }


def _room_schema(values: dict[str, Any], defaults: dict[str, Any]) -> vol.Schema:
    night_defaults = {
        key: values.get(key, defaults.get(key))
        for key in (CONF_NIGHT_START, CONF_NIGHT_END, CONF_NIGHT_OFFSET)
        if values.get(key, defaults.get(key)) is not None
    }
    return vol.Schema(
        {
            vol.Required(
                CONF_ROOM_NAME, default=values.get(CONF_ROOM_NAME, vol.UNDEFINED)
            ): selector.TextSelector(),
            vol.Required(
                CONF_ROOM_CLIMATES, default=values.get(CONF_ROOM_CLIMATES, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate", multiple=True)
            ),
            vol.Required(
                CONF_ROOM_USE_GLOBAL, default=values.get(CONF_ROOM_USE_GLOBAL, True)
            ): selector.BooleanSelector(),
            **_night_fields(night_defaults),
            vol.Optional(
                CONF_DAY_TEMP, description=_suggest(values, CONF_DAY_TEMP)
            ): _temperature_selector(),
            vol.Optional(
                CONF_NIGHT_TEMP, description=_suggest(values, CONF_NIGHT_TEMP)
            ): _temperature_selector(),
            vol.Required(
                CONF_COMFORT_TIME,
                default=values.get(CONF_COMFORT_TIME) or DEFAULT_COMFORT_TIME,
            ): selector.TimeSelector(),
            vol.Required(
                CONF_OPTIMUM_START, default=values.get(CONF_OPTIMUM_START, False)
            ): selector.BooleanSelector(),
        }
    )


def _temperature_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=5,
            max=30,
            step=0.5,
            unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _fireplace_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_FIREPLACE_CLIMATE, description=_suggest(values, CONF_FIREPLACE_CLIMATE)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="climate")),
            vol.Optional(
                CONF_FIREPLACE_TEMP_SENSOR,
                description=_suggest(values, CONF_FIREPLACE_TEMP_SENSOR),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.TEMPERATURE
                )
            ),
            vol.Required(
                CONF_FIREPLACE_THRESHOLD,
                default=values.get(CONF_FIREPLACE_THRESHOLD, DEFAULT_FIREPLACE_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.1,
                    max=5,
                    step=0.1,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _validate_general(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if user_input[CONF_OUTDOOR_SENSOR] == user_input[CONF_GAS_SENSOR]:
        errors["base"] = "same_entity"
    return errors


def _normalize_general(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_BASELINE_DAYS] = int(data[CONF_BASELINE_DAYS])
    return data


class HaClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HaClimateOptionsFlow:
        """Return the options flow."""
        return HaClimateOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the sensors, gas price and heating limit."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_general(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_GAS_SENSOR])
                self._abort_if_unique_id_configured()
                self._data = _normalize_general(user_input)
                return await self.async_step_night()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _general_schema({}), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_night(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Global night setback settings."""
        if user_input is not None:
            options = {**user_input, CONF_ROOMS: []}
            return self.async_create_entry(title=NAME, data=self._data, options=options)
        return self.async_show_form(
            step_id="night", data_schema=vol.Schema(_night_fields({}))
        )


class HaClimateOptionsFlow(OptionsFlow):
    """Change every setting after installation."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._room_id: str | None = None

    @property
    def _values(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def _rooms(self) -> list[dict[str, Any]]:
        return [dict(room) for room in self._values.get(CONF_ROOMS, [])]

    def _save(self, changes: dict[str, Any], remove: tuple[str, ...] = ()) -> ConfigFlowResult:
        options = {**self.config_entry.options, **changes}
        for key in remove:
            if key not in changes:
                options.pop(key, None)
        # Values that live in entry.data are overridden through the options.
        return self.async_create_entry(data=options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main menu."""
        menu = ["general", "night", "add_room"]
        if self._rooms:
            menu += ["edit_room", "remove_room"]
        menu.append("fireplace")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sensors, gas price and heating limit."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_general(user_input)
            if not errors:
                return self._save(_normalize_general(user_input), OPTIONAL_GENERAL)
        values = user_input if user_input is not None else self._values
        return self.async_show_form(
            step_id="general", data_schema=_general_schema(values), errors=errors
        )

    async def async_step_night(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Global night setback settings."""
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="night", data_schema=vol.Schema(_night_fields(self._values))
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a room with one or more floor heating loops."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_room(user_input, None)
            if not errors:
                room = {CONF_ROOM_ID: uuid.uuid4().hex[:8], **user_input}
                return self._save({CONF_ROOMS: [*self._rooms, room]})
        return self.async_show_form(
            step_id="add_room",
            data_schema=_room_schema(user_input or {}, self._values),
            errors=errors,
        )

    async def async_step_edit_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the room to edit."""
        if user_input is not None:
            self._room_id = user_input[CONF_ROOM_SELECT]
            return await self.async_step_room()
        return self.async_show_form(
            step_id="edit_room", data_schema=self._room_select_schema()
        )

    async def async_step_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a room."""
        rooms = self._rooms
        room = next(r for r in rooms if r[CONF_ROOM_ID] == self._room_id)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_room(user_input, self._room_id)
            if not errors:
                room.update({CONF_DAY_TEMP: None, CONF_NIGHT_TEMP: None, **user_input})
                return self._save({CONF_ROOMS: rooms})
        return self.async_show_form(
            step_id="room",
            data_schema=_room_schema(user_input or room, self._values),
            errors=errors,
            description_placeholders={"room": room[CONF_ROOM_NAME]},
        )

    async def async_step_remove_room(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a room (lowered loops are restored automatically)."""
        if user_input is not None:
            rooms = [
                r for r in self._rooms if r[CONF_ROOM_ID] != user_input[CONF_ROOM_SELECT]
            ]
            return self._save({CONF_ROOMS: rooms})
        return self.async_show_form(
            step_id="remove_room", data_schema=self._room_select_schema()
        )

    async def async_step_fireplace(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fireplace thermostat and threshold."""
        if user_input is not None:
            return self._save(user_input, OPTIONAL_FIREPLACE)
        return self.async_show_form(
            step_id="fireplace", data_schema=_fireplace_schema(self._values)
        )

    def _room_select_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_ROOM_SELECT): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=r[CONF_ROOM_ID], label=r[CONF_ROOM_NAME]
                            )
                            for r in self._rooms
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

    def _validate_room(self, user_input: dict[str, Any], room_id: str | None) -> dict[str, str]:
        errors: dict[str, str] = {}
        name = user_input[CONF_ROOM_NAME].strip()
        if not name:
            errors[CONF_ROOM_NAME] = "name_required"
        elif any(
            r[CONF_ROOM_NAME].casefold() == name.casefold() and r[CONF_ROOM_ID] != room_id
            for r in self._rooms
        ):
            errors[CONF_ROOM_NAME] = "name_exists"
        if not user_input.get(CONF_ROOM_CLIMATES):
            errors[CONF_ROOM_CLIMATES] = "climates_required"
        else:
            used = {
                entity
                for r in self._rooms
                if r[CONF_ROOM_ID] != room_id
                for entity in r.get(CONF_ROOM_CLIMATES, [])
            }
            if used & set(user_input[CONF_ROOM_CLIMATES]):
                errors[CONF_ROOM_CLIMATES] = "climate_in_use"
        day, night = user_input.get(CONF_DAY_TEMP), user_input.get(CONF_NIGHT_TEMP)
        if day is not None and night is not None and night >= day:
            errors[CONF_NIGHT_TEMP] = "night_above_day"
        user_input[CONF_ROOM_NAME] = name
        return errors
