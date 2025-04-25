"""Test the Simple Integration config flow."""

from unittest import mock

from homeassistant import config_entries

from custom_components.evse_load_balancer import config_flow, const


async def test_form(hass):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"


async def test_flow_user_init(hass):
    """Test the initialization of the form in the first step of the config flow."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    expected = {
        "data_schema": config_flow.STEP_INIT_SCHEMA,
        "description_placeholders": None,
        "errors": {},
        "flow_id": mock.ANY,
        "handler": "evse_load_balancer",
        "last_step": None,
        "step_id": "user",
        "type": "form",
        "preview": None,
    }
    assert expected == result


async def test_flow_user_init_validation(hass):
    """Test validation for missing meter_device or custom_phase_config"""
    _result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"],
        user_input={
            config_flow.CONF_PHASE_COUNT: 3,
            config_flow.CONF_FUSE_SIZE: 25,
            config_flow.CONF_CHARGER_DEVICE: "abc-123",
            config_flow.CONF_CUSTOM_PHASE_CONFIG: True,
        },
    )
    assert result["step_id"] == "power"
    assert result["type"] == "form"


async def test_flow_user_init_with_meter_device(hass):
    """Test if we create the entity when a meter is selected"""
    _result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"],
        user_input={
            config_flow.CONF_PHASE_COUNT: 3,
            config_flow.CONF_FUSE_SIZE: 25,
            config_flow.CONF_CHARGER_DEVICE: "abc-123",
            config_flow.CONF_METER_DEVICE: "meter-123",
        },
    )
    expected = {
        "version": 1,
        "type": "create_entry",
        "flow_id": mock.ANY,
        "handler": "evse_load_balancer",
        "title": "EVSE Load Balancer",
        "data": {
            config_flow.CONF_PHASE_COUNT: 3,
            config_flow.CONF_FUSE_SIZE: 25,
            config_flow.CONF_CHARGER_DEVICE: "abc-123",
            config_flow.CONF_METER_DEVICE: "meter-123",
        },
        "description": None,
        "description_placeholders": None,
        "result": mock.ANY,
        "context": {"source": "user"},
        "minor_version": 1,
        "options": {},
        "subentries": (),
    }
    assert result == expected


async def test_flow_user_init_data_custom_phase_step(hass):
    """Test we advance to custom phase step when data is valid and PHASE_CONFIG is true."""
    _result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"],
        user_input={
            config_flow.CONF_PHASE_COUNT: 3,
            config_flow.CONF_FUSE_SIZE: 25,
            config_flow.CONF_CHARGER_DEVICE: "abc-123",
        },
    )
    assert result["errors"] == {"base": "metering_selection_required"}


async def test_flow_power_init_form(hass):
    """Test the initialization of the form in the power step of the config flow."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "power"}
    )
    expected = {
        "data_schema": mock.ANY,
        "description_placeholders": None,
        "errors": {},
        "flow_id": mock.ANY,
        "handler": "evse_load_balancer",
        "step_id": "power",
        "last_step": None,
        "type": "form",
        "preview": None,
    }
    assert expected == result


async def test_flow_power_step(hass):
    """Test if correct number of phase config options are created based on first input"""
    _result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"],
        user_input={
            config_flow.CONF_PHASE_COUNT: 3,
            config_flow.CONF_FUSE_SIZE: 25,
            config_flow.CONF_CHARGER_DEVICE: "abc-123",
            config_flow.CONF_CUSTOM_PHASE_CONFIG: True,
        },
    )
    assert config_flow.CONF_PHASE_KEY_ONE in result["data_schema"].schema
    assert config_flow.CONF_PHASE_KEY_TWO in result["data_schema"].schema
    assert config_flow.CONF_PHASE_KEY_THREE in result["data_schema"].schema
