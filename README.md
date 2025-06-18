[![easee_hass](https://img.shields.io/github/release/dirkgroenen/hass-evse-load-balancer.svg?1)](https://github.com/dirkgroenen/hass-evse-load-balancer) ![Validate with hassfest](https://github.com/dirkgroenen/hass-evse-load-balancer/workflows/Validate%20with%20Hassfest%20and%20HACS/badge.svg) ![Maintenance](https://img.shields.io/maintenance/yes/2025.svg) [![Easee_downloads](https://img.shields.io/github/downloads/dirkgroenen/hass-evse-load-balancer/total)](https://github.com/dirkgroenen/hass-evse-load-balancer) [![easee_hass_downloads](https://img.shields.io/github/downloads/dirkgroenen/hass-evse-load-balancer/latest/total)](https://github.com/dirkgroenen/hass-evse-load-balancer)


# EVSE Load Balancer for Home Assistant 🚗⚡️ 

**EVSE Load Balancer** is an integration for [Home Assistant](https://www.home-assistant.io/) that provides a **universal load balancing solution for electric vehicle (EV) chargers**. It eliminates the need for additional vendor-specific hardware (and endless P1-port device clutter) by leveraging existing energy meters and sensors in your Home Assistant setup.

- No more need of custom automation scripts trying to protect your main fuse 
- No more additional hardware on your P1 port.

---

> **⚠️ Looking for early adopters:** who can help me test the component, extend its capabilities and provide feedback.
> Feel free to share your feedback in the [Home Assistant Community](https://community.home-assistant.io/t/evse-load-balancer-a-universal-load-balancer-for-your-ev-chargers/883863), or via Github. 

---

## Table of Contents

- [Features](#features)
- [Roadmap](#roadmap)
- [Supported Devices](#supported-devices)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
- [Events and Logging](#events-and-logging)
- [Contributing](#contributing)

## Features

- **Dynamic Load Balancing**: Automatically adjusts the charging current of your EV charger based on the available power in your home.
- **Broad Meter Support**: Works with DSMR-compatible meters or allows manual configuration based on existing entities for advanced setups.
- **Flexible Charger Integration**: Compatible with a range of EV chargers, such as Easee, Zaptec, Amina, ....

### Roadmap

- **Force PV Usage**: Introduce an option to prioritize the use of produced power (e.g., solar PV) for charging the EV, minimizing grid dependency.
- **Dynamic Tariff-Based Charging**: Enable the creation of charge plans that optimize charging times based on dynamic electricity tariffs, ensuring charging occurs at the lowest possible cost.

## Supported Devices

> **⚠️ Important notice:** I can personally only test the DSMR and Easee integration. Support 
> from the community is well appreciated to test other chargers and make contributions where required.
> Chargers and meters are implemented with best-effort, but often purely based on API documentation and available code.

### Energy Meters
- DSMR-compatible meters (via [DSMR Smart Meter](https://www.home-assistant.io/integrations/dsmr/))
- Custom configurations using existing Home Assistant sensors (1-3 Phase support)

### EV Chargers
- Easee Chargers (via [nordicopen/easee_hass](https://github.com/nordicopen/easee_hass))
- Zaptec Chargers (via [custom-components/zaptec](https://github.com/custom-components/zaptec))
- Amina S Chargers (via [Zigbee2MQTT/amina_S](https://www.zigbee2mqtt.io/devices/amina_S.html))
- Keba Charging Station (BMW Wallbox) (via [keba](https://www.home-assistant.io/integrations/keba/))
- ... additional chargers to be added ...

## How It Works

During setup of the EVSE Load Balancer integration it expects to be provided with a meter source, charger device and main fuse parameters. It will then monitor the power consumption and production in your home and dynamically adjusts the charging current of your EV charger to ensure that your home's power usage stays within safe limits.

Key parts of the process include:

- **Real-Time Monitoring:**  
  The balancer reads your meter's current consumption on each phase and calculates the remaining “available current”, which is basically the difference between your fuse’s capacity and your current load.

- **Risk-Based Adjustments:**  
  When the available current drops below zero (indicating potential overload), the algorithm quickly increases an accumulated "risk" factor. Once this risk exceeds a preset threshold, the charger’s current limit is immediately reduced to protect your circuit. 
  
  These "risk presets" are derived from the thermal behavior of B- and C-character circuit breakers. The algorithm tolerates brief overcurrent spikes, accumulating risk over time; if these spikes are too frequent or severe, the risk level exceeds a set threshold and the charger’s limit is immediately reduced to protect your fuse. Conversely, when surplus power is detected, the system only restores charging power after confirming that recovery conditions are stable over a configurable time period (a minimum of 15 minutes, extendable during periods of unstable usage).
  
- **Per-Phase Balancing:**  
  All calculations are performed separately for each electrical phase, ensuring that the load is balanced and your circuit remains safe under varying conditions. The ability to make use of this depends on your charger's capabilities though.

This adaptive approach allows the EVSE Load Balancer to optimize charging power while preventing overloads, making the most of your available energy, putting the least amount of stress on your charger, car and circuit breaker. 

## Installation

### HACS installation
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dirkgroenen&repository=hass-evse-load-balancer)

1. Search for "EVSE Load Balancer" in **HACS > Integrations**
2. Download the integration and restart Home Assistant.
3. Add the integration via **Settings > Devices & Services > Add Integration** and search for "EVSE Load Balancer."

### Manual
1. Copy the `custom_components/evse_load_balancer` folder to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration via **Settings > Devices & Services > Add Integration** and search for "EVSE Load Balancer."

## Configuration

During setup, you will be prompted to:
- Select your EV charger.
- Select your energy meter or provide custom sensors.
- Specify the fuse size and number of phases in your home.

### Advanced Configuration
For homes without a compatible energy meter, you can manually configure sensors for each phase, including:
- Power consumption
- Power production
- Voltage

## Events and Logging

The integration emits events to Home Assistant's event log whenever the charger current limit is adjusted. These events can be used to create automations or monitor the system's behavior.


## Contributing

Contributions are welcome! If you encounter any issues or have ideas for improvements, feel free to open an issue or submit a pull request on the [GitHub repository](https://github.com/dirkgroenen/hass-evse-load-balancer).

### Adding Charger or Meter support 
You can support EVSE Load Balancer by adding and testing additional chargers or meters. A brief overview of the steps required to follow:

1. **Create a New Charger Class**:
   - Create a new file in the `chargers` directory (e.g., `my_charger.py`).
   - Implement the `Charger` abstract base class from [`charger.py`](custom_components/evse_load_balancer/chargers/charger.py).

2. **Example**:
   Refer to the [`EaseeCharger`](custom_components/evse_load_balancer/chargers/easee_charger.py) implementation for an example of how to integrate a charger.

3. **Register the Charger**:
   - Update the `charger_factory` function in [`chargers/__init__.py`](custom_components/evse_load_balancer/chargers/__init__.py) to include your new charger class.
   - Add logic to detect the new charger based on its manufacturer or other identifiers.

#### Adding a New Meter

1. **Create a New Meter Class**:
   - Create a new file in the `meters` directory (e.g., `my_meter.py`).
   - Implement the `Meter` abstract base class from [`meter.py`](custom_components/evse_load_balancer/meters/meter.py).

2. **Example**:
   Refer to the [`DsmrMeter`](custom_components/evse_load_balancer/meters/dsmr_meter.py) implementation for an example of how to integrate a meter.

3. **Register the Meter**:
   - Update the `meter_factory` function in [`meters/__init__.py`](custom_components/evse_load_balancer/meters/__init__.py) to include your new meter class.
   - Add logic to detect the new meter based on its manufacturer or other identifiers.


