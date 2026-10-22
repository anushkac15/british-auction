class AppError(Exception):
    """Domain error mapped to a JSON response by the API layer."""

    def __init__(self, status_code: int, message: str, code: str, field: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.field = field


def not_found(what: str) -> AppError:
    return AppError(404, f"{what} not found", "not_found")


def invalid(message: str, field: str | None = None) -> AppError:
    return AppError(422, message, "validation_error", field)


def conflict(message: str, code: str = "conflict") -> AppError:
    return AppError(409, message, code)
