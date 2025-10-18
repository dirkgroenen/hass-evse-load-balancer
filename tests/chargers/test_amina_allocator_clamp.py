"""Tests for Amina-specific allocator clamp behaviour."""

from custom_components.evse_load_balancer.power_allocator import PowerAllocator
from custom_components.evse_load_balancer.const import Phase
from tests.helpers.mock_charger import MockCharger


def test_amina_clamp_converts_small_alloc_to_zero(monkeypatch):
    """If the allocator would assign 1-5A to an Amina charger, it should be set to 0."""
    pa = PowerAllocator()

    # Create a charger that reports AMINA_HW_MAX_CURRENT via get_max_current_limit
    charger = MockCharger(initial_current=10, charger_id="amina1")
    charger.set_max_limits({Phase.L1: 32, Phase.L2: 32, Phase.L3: 32})
    charger.set_can_charge(True)

    pa.add_charger_and_initialize(charger)

    # Simulate allocator creating a small non-zero allocation < 6 amps
    # We'll bypass the private methods and directly craft the available_currents
    # such that _allocate_current will attempt to return a small value.
    # To force that behavior, we monkeypatch PowerAllocator._allocate_current to
    # return a small allocation for our charger and then call update_allocation

    def fake_allocate(_):
        return {"amina1": {Phase.L1: 3, Phase.L2: 3, Phase.L3: 3}}

    monkeypatch.setattr(PowerAllocator, "_allocate_current", lambda self, ac: fake_allocate(ac))

    res = pa.update_allocation({Phase.L1: 0, Phase.L2: 0, Phase.L3: 0})

    assert "amina1" in res
    # The allocator should convert the small non-zero allocation to 0
    assert res["amina1"] == {Phase.L1: 0, Phase.L2: 0, Phase.L3: 0}
