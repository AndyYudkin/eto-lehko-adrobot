from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.creator.refs import ConfigError
from app.keitaro.client import KeitaroError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConfigError)
    async def _config_error(_: Request, exc: ConfigError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(KeitaroError)
    async def _keitaro_error(_: Request, exc: KeitaroError) -> JSONResponse:
        detail = f"Keitaro error: {exc.status} {exc.body[:200]}"
        return JSONResponse({"detail": detail}, status_code=502)
