"""HTTP adapter failures owned by Query."""


class QueryError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message
