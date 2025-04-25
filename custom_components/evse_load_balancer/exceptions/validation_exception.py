"""Validation Exception."""


class ValidationExceptionError(Exception):
    """Exception raised for validation errors."""

    def __init__(self, base: str, key: str) -> None:
        """Initialize ValidationException with a message."""
        super().__init__("Validation Exception for #{base} and #{key}")
        self.base = base
        self.key = key
