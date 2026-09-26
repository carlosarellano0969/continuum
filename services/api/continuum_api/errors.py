class ContinuumError(Exception):
    """Base application error safe to expose through the API."""


class NotFoundError(ContinuumError):
    pass


class ConflictError(ContinuumError):
    pass


class DependencyError(ContinuumError):
    pass

