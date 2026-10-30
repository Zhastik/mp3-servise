"""Translate application failures into the public HTTP error contract."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import ApplicationError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse({"detail": error.message}, status_code=error.status_code, headers=error.headers)
