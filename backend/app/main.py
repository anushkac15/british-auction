import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.clock import get_clock
from app.config import settings
from app.errors import AppError
from app.events import broadcaster, libpq_conninfo
from app.routers import auth, rfqs, stream


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.sse_enabled:
        broadcaster.start(asyncio.get_running_loop(), libpq_conninfo(settings.database_url))
    yield
    if settings.sse_enabled:
        broadcaster.stop()


docs_enabled = not settings.is_production
app = FastAPI(
    title="British Auction RFQ",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _server_now(request: Request):
    clock_factory = request.app.dependency_overrides.get(get_clock, get_clock)
    return clock_factory().now()


def _error(request: Request, status_code: int, body: dict) -> JSONResponse:
    body["server_now"] = _server_now(request)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error(request, exc.status_code, {"detail": exc.message, "code": exc.code, "field": exc.field})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header")]
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        errors.append({"field": loc[-1] if loc else None, "message": message})
    detail = "; ".join(e["message"] if not e["field"] else f"{e['field']}: {e['message']}" for e in errors)
    return _error(request, 422, {"detail": detail, "code": "validation_error", "errors": errors})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error(request, exc.status_code, {"detail": exc.detail, "code": "http_error"})


@app.get("/api/health")
def health(request: Request) -> dict:
    return {"status": "ok", "server_now": _server_now(request)}


for router in (auth.router, rfqs.router, stream.router):
    app.include_router(router, prefix="/api")
