class RAGError(Exception):
    status_code = 500
    code = "internal_error"


class UnauthorizedError(RAGError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(RAGError):
    status_code = 403
    code = "forbidden"


class NotFoundError(RAGError):
    status_code = 404
    code = "not_found"


class ValidationError(RAGError):
    status_code = 400
    code = "invalid_request"

