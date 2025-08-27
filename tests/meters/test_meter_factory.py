"""Tests for the meter_factory function in meters/__init__.py."""

import pytest
from unittest.mock import MagicMock, patch
from custom_components.evse_load_balancer.meters import meter_factory
from custom_components.evse_load_balancer.meters.custom_meter import CustomMeter
from custom_components.evse_load_balancer.meters.amshan_meter import AmshanMeter
from custom_components.evse_load_balancer.meters.dsmr_meter import DsmrMeter
from custom_components.evse_load_balancer.meters.homewizard_meter import HomeWizardMeter
from custom_components.evse_load_balancer.const import METER_DOMAIN_AMSHAN, METER_DOMAIN_DSMR, METER_DOMAIN_HOMEWIZARD, SUPPORTED_METER_DEVICE_DOMAINS


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
def mock_config_entry():
    return MagicMock()


@pytest.fixture
def mock_device_entry():
    device = MagicMock()
    return device


@pytest.mark.asyncio
async def test_meter_factory_custom_meter(mock_hass, mock_config_entry):
    meter = await meter_factory(mock_hass, mock_config_entry, True, None)
    assert isinstance(meter, CustomMeter)


@pytest.mark.asyncio
@patch("custom_components.evse_load_balancer.meters.dr.async_get")
async def test_meter_factory_dsmr_meter(mock_async_get, mock_hass, mock_config_entry, mock_device_entry):
    mock_device_entry.identifiers = {(METER_DOMAIN_DSMR, "id1")}
    mock_async_get.return_value.async_get.return_value = mock_device_entry
    meter = await meter_factory(mock_hass, mock_config_entry, False, "device_id")
    assert isinstance(meter, DsmrMeter)


@pytest.mark.asyncio
@patch("custom_components.evse_load_balancer.meters.dr.async_get")
async def test_meter_factory_homewizard_meter(mock_async_get, mock_hass, mock_config_entry, mock_device_entry):
    mock_device_entry.identifiers = {(METER_DOMAIN_HOMEWIZARD, "id2")}
    mock_async_get.return_value.async_get.return_value = mock_device_entry
    meter = await meter_factory(mock_hass, mock_config_entry, False, "device_id")
    assert isinstance(meter, HomeWizardMeter)

@pytest.mark.asyncio
@patch("custom_components.evse_load_balancer.meters.dr.async_get")
async def test_meter_factory_amshan_meter(mock_async_get, mock_hass, mock_config_entry, mock_device_entry):
    mock_device_entry.identifiers = {(METER_DOMAIN_AMSHAN, "id3")}
    mock_async_get.return_value.async_get.return_value = mock_device_entry
    meter = await meter_factory(mock_hass, mock_config_entry, False, "device_id")
    assert isinstance(meter, AmshanMeter)

@pytest.mark.asyncio
@patch("custom_components.evse_load_balancer.meters.dr.async_get")
async def test_meter_factory_implements_all_supported_meters(mock_async_get, mock_hass, mock_config_entry, mock_device_entry):
    for domain in SUPPORTED_METER_DEVICE_DOMAINS:
        mock_device_entry.identifiers = {(domain, "id2")}
        mock_async_get.return_value.async_get.return_value = mock_device_entry
        try:
            await meter_factory(mock_hass, mock_config_entry, False, "device_id")
        except Exception as e:
            pytest.fail(f"meter_factory raised an exception for domain {domain}: {e}")


@pytest.mark.asyncio
@patch("custom_components.evse_load_balancer.meters.dr.async_get")
async def test_meter_factory_unsupported_manufacturer(mock_async_get, mock_hass, mock_config_entry, mock_device_entry):
    mock_device_entry.identifiers = {("unsupported", "id3")}
    mock_async_get.return_value.async_get.return_value = mock_device_entry
    with pytest.raises(ValueError, match="Unsupported manufacturer"):
        await meter_factory(mock_hass, mock_config_entry, False, "device_id")


@pytest.mark.asyncio
@patch("custom_components.evse_load_balancer.meters.dr.async_get")
async def test_meter_factory_device_not_found(mock_async_get, mock_hass, mock_config_entry):
    mock_async_get.return_value.async_get.return_value = None
    with pytest.raises(ValueError, match="Device with ID device_id not found in registry."):
        await meter_factory(mock_hass, mock_config_entry, False, "device_id")
