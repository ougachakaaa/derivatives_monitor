"""Transport-neutral Analytics failures."""


class AnalyticsError(Exception):
    """Base class for expected Analytics failures."""


class AnalyticsRequestError(AnalyticsError):
    """The caller supplied an invalid Analytics request."""


class AnalyticsUnavailableError(AnalyticsError):
    """Analytics could not complete within its contracted boundary."""
