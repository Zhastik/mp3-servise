"""Application failures independent of HTTP and any transport framework."""


class ApplicationError(Exception):
    def __init__(self, message: str, status_code: int, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}
