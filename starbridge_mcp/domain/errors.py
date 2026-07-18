from __future__ import annotations


class DomainValidationError(ValueError):
    """A persisted project or workflow value violates the public domain contract."""


class RecordNotFoundError(LookupError):
    """A project or job does not exist in the configured application data store."""


class ConfirmationRequiredError(PermissionError):
    """A local write was requested without the required explicit confirmation."""
