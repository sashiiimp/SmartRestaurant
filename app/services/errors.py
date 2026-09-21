"""Domain exceptions. Services raise these; controllers map them to HTTP status (ARCH 5.2)."""


class ServiceError(Exception):
    code = "error"

    def __init__(self, message: str = "", fields: dict | None = None, code: str | None = None, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}
        self.extra = extra or {}
        if code:
            self.code = code


class ValidationError(ServiceError):
    code = "validation_error"


class NotFoundError(ServiceError):
    code = "not_found"


class ConflictError(ServiceError):
    code = "conflict"


class AuthenticationError(ServiceError):
    code = "invalid_credentials"


class AccountLocked(ServiceError):
    code = "account_locked"
