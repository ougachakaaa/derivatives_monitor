"""Transport-neutral Data Provider failures."""


class DataProviderError(Exception):
    """Base class for expected Data Provider failures."""


class DataProviderInputError(DataProviderError):
    """The caller supplied an invalid data request."""


class DataNotFoundError(DataProviderError):
    """The requested published dataset does not exist."""


class DataUnavailableError(DataProviderError):
    """The requested data cannot be read safely right now."""
