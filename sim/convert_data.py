"""
Convert data coming from Home Assistant to a simulation format.

Used for testing!
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

_LOGGER = logging.getLogger(__name__)

# Ask the user for the name of the input file
input_file_name = input(
    "Provide the name of the input data located in ./input (e.g., history2.csv): "
)
input_path = Path.resolve(Path(__file__).parent / "input" / input_file_name)

# Check if the file exists
if not input_path.exists():
    msg = f"'{input_file_name}' not found in 'input'"
    raise FileNotFoundError(msg)

# Load data
df_raw = pd.read_csv(input_path)

# Round last_changed to full seconds, remove milliseconds
df_raw["last_changed"] = pd.to_datetime(df_raw["last_changed"]).dt.floor("s")

# Filter relevant sensor data
relevant_entities = [
    "sensor.available_current_l1",
    "sensor.available_current_l2",
    "sensor.available_current_l3",
    "sensor.easee_thuis_circuit_current",
]
df_filtered = df_raw[df_raw["entity_id"].isin(relevant_entities)]

# Sort and keep only the first measurement per second per entity
df_filtered = df_filtered.sort_values("last_changed").drop_duplicates(
    subset=["last_changed", "entity_id"], keep="first"
)

# Pivot to wide format: sensors become columns
df_pivot = df_filtered.pivot_table(
    index="last_changed", columns="entity_id", values="state"
)

# Convert all states to float (coerce 'unavailable' to NaN)
df_pivot = df_pivot.apply(pd.to_numeric, errors="coerce")

# Reindex to ensure we have every second represented
full_index = pd.date_range(
    start=df_pivot.index.min(), end=df_pivot.index.max(), freq="1s"
)
df_pivot = df_pivot.reindex(full_index)

# Forward-fill missing values
df_pivot = df_pivot.ffill()

# Drop rows where any of the required sensors are still missing (e.g., at beginning)
required_cols = [
    "sensor.available_current_l1",
    "sensor.available_current_l2",
    "sensor.available_current_l3",
    "sensor.easee_thuis_circuit_current",
]
df_pivot = df_pivot.dropna(subset=required_cols)

# Compute corrected values per phase
df_pivot["corrected_l1"] = (
    df_pivot["sensor.available_current_l1"]
    + df_pivot["sensor.easee_thuis_circuit_current"]
)
df_pivot["corrected_l2"] = (
    df_pivot["sensor.available_current_l2"]
    + df_pivot["sensor.easee_thuis_circuit_current"]
)
df_pivot["corrected_l3"] = (
    df_pivot["sensor.available_current_l3"]
    + df_pivot["sensor.easee_thuis_circuit_current"]
)

# Prepare output
df_result = df_pivot[["corrected_l1", "corrected_l2", "corrected_l3"]]
df_result.index.name = "last_changed"

# Export to a new CSV
current_date = datetime.now(tz=datetime.UTC).strftime("%d-%m-%Y")
output_path = Path.resolve(Path(__file__).parent / "data" / f"sim_{input_file_name}")
df_result.to_csv(output_path)

_LOGGER.info("Simulation data successfully saved to: {output_path}")
