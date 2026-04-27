import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import AuthRedirect, csrf_token
from app.database import Base, PROJECT_ROOT, SessionLocal, apply_lightweight_migrations, engine
from app.models import DemandStatus, DeliveryResultStatus, DeliverySessionStatus, RequestStatus
from app.routers import admin, appraiser, driver, home
from app.seed import seed_data


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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    apply_lightweight_migrations()
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
