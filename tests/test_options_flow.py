"""Test the Simple Integration config flow."""

from custom_components.evse_load_balancer.options_flow import (
    OPTION_MAX_FUSE_LOAD_AMPS,
    OPTION_CHARGE_LIMIT_HYSTERESIS,
    EvseLoadBalancerOptionsFlow,
)
from custom_components.evse_load_balancer.const import DOMAIN
from custom_components.evse_load_balancer import config_flow as cf
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry_id",
        data={cf.CONF_FUSE_SIZE: 25},  # Original fuse size is 25A
        options={},  # No options set initially
    )


@pytest.fixture
def mock_config_entry_with_options():
    """Create a mock config entry with options already set."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry_id",
        data={cf.CONF_FUSE_SIZE: 25},  # Original fuse size is 25A
        options={OPTION_MAX_FUSE_LOAD_AMPS: 30},  # Override to 30A
    )


def test_get_option_value_uses_existing_option(mock_config_entry_with_options):
    """Test that get_option_value uses existing option when set."""
    result = EvseLoadBalancerOptionsFlow.get_option_value(
        mock_config_entry_with_options, OPTION_MAX_FUSE_LOAD_AMPS
    )
    assert result == 30  # Should use the explicitly set option


@pytest.mark.asyncio
async def test_options_schema_default_inherits_fuse_size(hass, mock_config_entry):
    """Test that the options schema default inherits from CONF_FUSE_SIZE."""
    mock_config_entry.add_to_hass(hass)

    # Use the proper HA flow initialization
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    # Get the default value for OPTION_MAX_FUSE_LOAD_AMPS by looking at the key's default
    for key in result["data_schema"].schema:
        if key.schema == OPTION_MAX_FUSE_LOAD_AMPS:
            assert key.default() == 25  # Should inherit from CONF_FUSE_SIZE
            break
    else:
        pytest.fail("OPTION_MAX_FUSE_LOAD_AMPS not found in schema")


@pytest.mark.asyncio
async def test_options_schema_default_uses_existing_option(hass, mock_config_entry_with_options):
    """Test that the options schema default uses existing option when set."""
    mock_config_entry_with_options.add_to_hass(hass)

    # Use the proper HA flow initialization
    result = await hass.config_entries.options.async_init(mock_config_entry_with_options.entry_id)

    # Get the default value for OPTION_MAX_FUSE_LOAD_AMPS by looking at the key's default
    for key in result["data_schema"].schema:
        if key.schema == OPTION_MAX_FUSE_LOAD_AMPS:
            assert key.default() == 30  # Should use the explicitly set option
            break
    else:
        pytest.fail("OPTION_MAX_FUSE_LOAD_AMPS not found in schema")


@pytest.mark.asyncio
async def test_validate_init_input_keeps_non_zero_fuse_override():
    """Test that validate_init_input keeps non-zero fuse override."""
    from custom_components.evse_load_balancer.options_flow import validate_init_input

    input_data = {
        "charge_limit_hysteresis": 15,
        OPTION_MAX_FUSE_LOAD_AMPS: 30  # This should be kept
    }

    result = await validate_init_input(None, input_data)

    assert result[OPTION_MAX_FUSE_LOAD_AMPS] == 30
    assert result["charge_limit_hysteresis"] == 15


@pytest.mark.asyncio
async def test_options_flow_init(hass):
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="unique_balancer_id",
        data={
            cf.CONF_CHARGER_DEVICE: "abc-123",
            cf.CONF_METER_DEVICE: "meter-123",
            cf.CONF_FUSE_SIZE: 25,
            cf.CONF_PHASE_COUNT: 3,
        },
    )
    config_entry.add_to_hass(hass)

    # show initial form
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["errors"] == {}
    assert OPTION_CHARGE_LIMIT_HYSTERESIS in result["data_schema"].schema
    assert OPTION_MAX_FUSE_LOAD_AMPS in result["data_schema"].schema
