def combined_conf_key(*conf_keys: list) -> str:
    """Combine configuration keys into a single string."""
    return ".".join(conf_keys)
