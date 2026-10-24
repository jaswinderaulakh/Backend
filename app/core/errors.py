"""Plain-English errors. main.py turns each one into the right web response."""


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class BadRequestError(AppError):
    status_code = 400


class AuthError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


class RateLimitError(AppError):
    status_code = 429


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class TooLargeError(AppError):
    status_code = 413
