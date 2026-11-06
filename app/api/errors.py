from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def api_error_response(
    status_code: int,
    code: str,
    message: str,
    detail=None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content = {
        "success": False,
        "error": {"code": code, "message": message},
    }
    if detail is not None:
        content["detail"] = detail
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(content),
        headers=headers,
    )


def api_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "authentication_required",
        403: "access_denied",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        503: "service_unavailable",
    }.get(status_code, "request_failed")