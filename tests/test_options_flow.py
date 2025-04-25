"""Test the Simple Integration config flow."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer import (
    config_flow as cf,
)
from custom_components.evse_load_balancer import (
    const,
)
from custom_components.evse_load_balancer import (
    options_flow as of,
)


@pytest.mark.asyncio
async def test_options_flow_init(hass):
    config_entry = MockConfigEntry(
        domain=const.DOMAIN,
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
    assert of.OPTION_CHARGE_LIMIT_HYSTERESIS in result["data_schema"].schema
