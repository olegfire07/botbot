"""Admin panel router package.

Assembles sub-routers from individual modules so that ``main.py`` can still do::

    from app.routers import admin
    app.include_router(admin.router)
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.templating import Jinja2Templates

from app.auth import require_csrf, require_roles
from app.models import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles(UserRole.admin)), Depends(require_csrf)],
)
templates = Jinja2Templates(directory="app/templates")

# Import sub-modules so their @router decorations take effect.
from app.routers.admin import crud  # noqa: E402, F401
from app.routers.admin import dashboard  # noqa: E402, F401
from app.routers.admin import demand  # noqa: E402, F401
from app.routers.admin import exports  # noqa: E402, F401
from app.routers.admin import history  # noqa: E402, F401
from app.routers.admin import super_admin  # noqa: E402, F401
