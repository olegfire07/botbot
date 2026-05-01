import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.auth import AuthRedirect, csrf_token
from app.database import Base, PROJECT_ROOT, SessionLocal, apply_lightweight_migrations, engine
from app.models import DemandStatus, DeliveryResultStatus, DeliverySessionStatus, RequestStatus
from app.routers import admin, appraiser, driver, home
from app.seed import seed_data
from app.services.websocket_service import manager


def _session_secret() -> str:
    secret = os.getenv("SESSION_SECRET_KEY")
    env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    if secret:
        return secret
    if env in {"production", "prod"}:
        raise RuntimeError("SESSION_SECRET_KEY must be set in production")
    return "local-dev-change-me"


app = FastAPI(title="Фианит Снаб")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    https_only=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app/static"), name="static")


STATUS_LABELS = {
    DemandStatus.active: "ожидает доставки",
    DemandStatus.partially_delivered: "частично доставлено",
    DemandStatus.delivered: "доставлено",
    DemandStatus.cancelled: "отменено",
    RequestStatus.new: "новая",
    RequestStatus.processed: "обработана",
    RequestStatus.closed: "закрыта",
    DeliverySessionStatus.open: "открыт",
    DeliverySessionStatus.closed: "закрыт",
    DeliveryResultStatus.full: "полностью",
    DeliveryResultStatus.partial: "частично",
    DeliveryResultStatus.none: "не доставлено",
}


def status_label(status: object) -> str:
    return STATUS_LABELS.get(status, str(status))


def qty(value: object) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def dt(value: object) -> str:
    if not value:
        return "-"
    return value.strftime("%d.%m.%Y %H:%M")


def money(value: object) -> str:
    number = float(value or 0)
    return f"{number:,.0f}".replace(",", " ")


for router in (home.router, appraiser.router, driver.router, admin.router):
    app.include_router(router)

for templates in (home.templates, appraiser.templates, driver.templates, admin.templates):
    templates.env.filters["status_label"] = status_label
    templates.env.filters["qty"] = qty
    templates.env.filters["dt"] = dt
    templates.env.filters["money"] = money
    templates.env.globals["csrf_token"] = csrf_token


@app.exception_handler(AuthRedirect)
def auth_redirect_handler(request, exc: AuthRedirect):
    return RedirectResponse(exc.url, status_code=303)


@app.get("/health", include_in_schema=False)
def health_check():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "database": "unavailable", "detail": exc.__class__.__name__},
            status_code=503,
        )
    finally:
        db.close()
    return {"status": "ok", "database": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse("/static/favicon.svg", status_code=307)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session = websocket.session
    if not session or not session.get("user_id"):
        await websocket.close(code=1008)
        return
        
    db = SessionLocal()
    try:
        from app.models import User
        user_id = int(session["user_id"])
        user = db.get(User, user_id)
        if not user or not user.is_active or user.is_deleted:
            await websocket.close(code=1008)
            return
        role = user.role.value
    except Exception:
        db.close()
        await websocket.close(code=1008)
        return
    finally:
        db.close()

    await manager.connect(websocket, role)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, role)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    apply_lightweight_migrations()
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
