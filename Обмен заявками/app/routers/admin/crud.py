"""CRUD operations for branches, items, and users."""

import logging
from urllib.parse import quote

from fastapi import Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password, require_roles
from app.database import get_db
from app.models import Branch, Item, User, UserRole
from app.routers.admin import router
from app.routers.admin._helpers import (
    _active_admins,
    _audit,
    _super_admin_error,
    _validate_admin_password,
)
from app.routers.admin.demand import _cancel_demand_lines

logger = logging.getLogger(__name__)


# ─── Branches ────────────────────────────────────────────────────────────────

@router.post("/branches")
def add_branch(name: str = Form(...), address: str = Form(""), db: Session = Depends(get_db)):
    name = name.strip()
    if not name:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название подразделения')}#directories",
            status_code=303,
        )
    db.add(Branch(name=name, address=address.strip() or None))
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Подразделение добавлено')}#directories",
        status_code=303,
    )


@router.post("/branches/{branch_id}")
def update_branch(
    branch_id: int,
    name: str = Form(...),
    address: str = Form(""),
    db: Session = Depends(get_db),
):
    branch = db.get(Branch, branch_id)
    if not branch or branch.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Подразделение не найдено')}#directories",
            status_code=303,
        )
    name = name.strip()
    if not name:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название подразделения')}#directories",
            status_code=303,
        )
    branch.name = name
    branch.address = address.strip() or None
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Подразделение обновлено')}#directories",
        status_code=303,
    )


@router.post("/branches/{branch_id}/toggle")
def toggle_branch(branch_id: int, db: Session = Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if branch and not branch.is_deleted:
        branch.is_active = not branch.is_active
        db.commit()
    return RedirectResponse("/admin#directories", status_code=303)


@router.post("/branches/{branch_id}/delete")
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    branch = db.get(Branch, branch_id)
    if not branch or branch.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Подразделение не найдено')}#directories",
            status_code=303,
        )
    branch.is_deleted = True
    branch.is_active = False
    affected_users = 0
    for branch_user in db.scalars(
        select(User).where(User.branch_id == branch.id, User.is_deleted.is_(False))
    ).all():
        branch_user.is_active = False
        affected_users += 1
    cancelled = _cancel_demand_lines(
        db, current_user, branch_id=branch.id, reason="Подразделение удалено"
    )
    _audit(
        db,
        current_user,
        "delete",
        "branch",
        branch.id,
        f"Подразделение удалено, потребностей отменено: {cancelled}, пользователей отключено: {affected_users}",
    )
    db.commit()
    logger.info("Branch #%d deleted by user %d", branch.id, current_user.id)
    return RedirectResponse(
        f"/admin?message={quote('Подразделение удалено')}#directories",
        status_code=303,
    )


@router.get("/branches/{branch_id}/delete")
def delete_branch_get_fallback(branch_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#directories",
        status_code=303,
    )


# ─── Items ───────────────────────────────────────────────────────────────────

@router.post("/items")
def add_item(
    name: str = Form(...),
    unit: str = Form(...),
    unit_cost: float = Form(0),
    db: Session = Depends(get_db),
):
    name = name.strip()
    unit = unit.strip()
    if not name or not unit:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название и единицу измерения')}#items",
            status_code=303,
        )
    db.add(Item(name=name, unit=unit, unit_cost=max(unit_cost, 0)))
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Позиция добавлена')}#items",
        status_code=303,
    )


@router.post("/items/{item_id}")
def update_item(
    item_id: int,
    name: str = Form(...),
    unit: str = Form(...),
    unit_cost: float = Form(0),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item or item.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Позиция не найдена')}#items", status_code=303
        )
    name = name.strip()
    unit = unit.strip()
    if not name or not unit:
        return RedirectResponse(
            f"/admin?error={quote('Укажите название и единицу измерения')}#items",
            status_code=303,
        )
    item.name = name
    item.unit = unit
    item.unit_cost = max(unit_cost, 0)
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Позиция обновлена')}#items", status_code=303
    )


@router.post("/items/{item_id}/cost")
def update_item_cost(
    item_id: int,
    unit_cost: float = Form(0),
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if item and not item.is_deleted:
        item.unit_cost = max(unit_cost, 0)
        db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Цена позиции обновлена')}#items", status_code=303
    )


@router.post("/items/{item_id}/toggle")
def toggle_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item and not item.is_deleted:
        item.is_active = not item.is_active
        db.commit()
    return RedirectResponse("/admin#items", status_code=303)


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    item = db.get(Item, item_id)
    if not item or item.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Позиция не найдена')}#items", status_code=303
        )
    item.is_deleted = True
    item.is_active = False
    cancelled = _cancel_demand_lines(
        db, current_user, item_id=item.id, reason="Позиция удалена"
    )
    _audit(
        db,
        current_user,
        "delete",
        "item",
        item.id,
        f"Позиция удалена, потребностей отменено: {cancelled}",
    )
    db.commit()
    logger.info("Item #%d deleted by user %d", item.id, current_user.id)
    return RedirectResponse(
        f"/admin?message={quote('Позиция удалена')}#items", status_code=303
    )


@router.get("/items/{item_id}/delete")
def delete_item_get_fallback(item_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#items",
        status_code=303,
    )


# ─── Users ───────────────────────────────────────────────────────────────────

@router.post("/users")
def add_user(
    full_name: str = Form(...),
    login: str = Form(...),
    password: str = Form(...),
    role: UserRole = Form(...),
    branch_id: str = Form(""),
    db: Session = Depends(get_db),
):
    login = login.strip()
    password = password.strip()
    full_name = full_name.strip()
    if not full_name or not login:
        return RedirectResponse(
            f"/admin?error={quote('Укажите ФИО и логин')}#directories", status_code=303
        )
    if password_error := _validate_admin_password(password):
        return RedirectResponse(
            f"/admin?error={quote(password_error)}#directories", status_code=303
        )
    try:
        parsed_branch_id = int(branch_id) if branch_id.strip() else None
    except ValueError:
        return RedirectResponse(
            f"/admin?error={quote('Некорректное подразделение')}#directories",
            status_code=303,
        )
    if role == UserRole.appraiser and not parsed_branch_id:
        return RedirectResponse(
            f"/admin?error={quote('Для товароведа выберите подразделение')}#directories",
            status_code=303,
        )
    if parsed_branch_id:
        branch = db.get(Branch, parsed_branch_id)
        if not branch or branch.is_deleted or (role == UserRole.appraiser and not branch.is_active):
            return RedirectResponse(
                f"/admin?error={quote('Выбранное подразделение недоступно')}#directories",
                status_code=303,
            )
    existing_deleted = db.scalar(select(User).where(User.login == login, User.is_deleted.is_(True)))
    if existing_deleted:
        existing_deleted.full_name = full_name
        existing_deleted.password_hash = hash_password(password)
        existing_deleted.role = role
        existing_deleted.branch_id = parsed_branch_id if role == UserRole.appraiser else None
        existing_deleted.is_active = True
        existing_deleted.is_deleted = False
        db.commit()
        return RedirectResponse(
            f"/admin?message={quote('Пользователь восстановлен и обновлён')}#directories",
            status_code=303,
        )
    if db.scalar(select(User).where(User.login == login, User.is_deleted.is_(False))):
        return RedirectResponse(
            f"/admin?error={quote('Пользователь с таким логином уже есть')}#directories",
            status_code=303,
        )
    db.add(
        User(
            full_name=full_name,
            login=login,
            password_hash=hash_password(password),
            role=role,
            branch_id=parsed_branch_id if role == UserRole.appraiser else None,
        )
    )
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пользователь добавлен')}#directories", status_code=303
    )


@router.post("/users/{user_id}")
def update_user(
    user_id: int,
    full_name: str = Form(...),
    login: str = Form(...),
    role: UserRole = Form(...),
    branch_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )

    full_name = full_name.strip()
    login = login.strip()
    if not full_name or not login:
        return RedirectResponse(
            f"/admin?error={quote('Укажите ФИО и логин')}#directories", status_code=303
        )

    duplicate = db.scalar(
        select(User).where(User.login == login, User.id != user_id, User.is_deleted.is_(False))
    )
    if duplicate:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь с таким логином уже есть')}#directories",
            status_code=303,
        )

    try:
        parsed_branch_id = int(branch_id) if branch_id.strip() else None
    except ValueError:
        return RedirectResponse(
            f"/admin?error={quote('Некорректное подразделение')}#directories",
            status_code=303,
        )
    if role == UserRole.appraiser and not parsed_branch_id:
        return RedirectResponse(
            f"/admin?error={quote('Для товароведа выберите подразделение')}#directories",
            status_code=303,
        )
    if parsed_branch_id:
        branch = db.get(Branch, parsed_branch_id)
        if not branch or branch.is_deleted or (role == UserRole.appraiser and not branch.is_active):
            return RedirectResponse(
                f"/admin?error={quote('Выбранное подразделение недоступно')}#directories",
                status_code=303,
            )
    deleted_duplicate = db.scalar(
        select(User).where(User.login == login, User.id != user_id, User.is_deleted.is_(True))
    )
    if deleted_duplicate:
        return RedirectResponse(
            f"/admin?error={quote('Этот логин занят удалённым пользователем. Создайте пользователя с этим логином заново, чтобы восстановить запись.')}#directories",
            status_code=303,
        )

    if user.role == UserRole.admin and role != UserRole.admin and len(_active_admins(db)) <= 1:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя убрать роль у единственного активного администратора')}#directories",
            status_code=303,
        )

    user.full_name = full_name
    user.login = login
    user.role = role
    user.branch_id = parsed_branch_id if role == UserRole.appraiser else None
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пользователь обновлён')}#directories", status_code=303
    )


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )
    password = password.strip()
    if password_error := _validate_admin_password(password):
        return RedirectResponse(
            f"/admin?error={quote(password_error)}#directories", status_code=303
        )
    user.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Пароль обновлён')}#directories", status_code=303
    )


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user and not user.is_deleted:
        if user.role == UserRole.admin and user.is_active and len(_active_admins(db)) <= 1:
            return RedirectResponse(
                f"/admin?error={quote('Нельзя отключить единственного активного администратора')}#directories",
                status_code=303,
            )
        user.is_active = not user.is_active
        db.commit()
    return RedirectResponse("/admin#directories", status_code=303)


@router.post("/users/{user_id}/delete")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        return RedirectResponse(
            f"/admin?error={quote('Пользователь не найден')}#directories", status_code=303
        )
    if user.id == current_user.id:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя удалить текущего пользователя')}#directories",
            status_code=303,
        )
    if user.role == UserRole.admin and user.is_active and len(_active_admins(db)) <= 1:
        return RedirectResponse(
            f"/admin?error={quote('Нельзя удалить единственного активного администратора')}#directories",
            status_code=303,
        )
    user.is_deleted = True
    user.is_active = False
    user.is_super_admin = False
    _audit(db, current_user, "delete", "user", user.id, "Пользователь удалён")
    db.commit()
    logger.info("User #%d deleted by user %d", user.id, current_user.id)
    return RedirectResponse(
        f"/admin?message={quote('Пользователь удалён')}#directories",
        status_code=303,
    )


@router.get("/users/{user_id}/delete")
def delete_user_get_fallback(user_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#directories",
        status_code=303,
    )


# ─── Demand line delete ─────────────────────────────────────────────────────

@router.post("/demand-lines/{line_id}/delete")
def delete_demand_line(
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    if response := _super_admin_error(current_user):
        return response
    from app.models import DemandLine, DemandStatus, utc_now
    demand_line = db.get(DemandLine, line_id)
    if not demand_line:
        return RedirectResponse(
            f"/admin?error={quote('Потребность не найдена')}#demand", status_code=303
        )
    demand_line.qty_remaining = 0
    demand_line.status = DemandStatus.cancelled
    demand_line.last_updated_at = utc_now()
    _audit(db, current_user, "delete", "demand_line", demand_line.id, "Потребность удалена")
    db.commit()
    return RedirectResponse(
        f"/admin?message={quote('Потребность удалена')}#demand", status_code=303
    )


@router.get("/demand-lines/{line_id}/delete")
def delete_demand_line_get_fallback(line_id: int):
    return RedirectResponse(
        f"/admin?error={quote('Удаление выполняется только кнопкой формы. Обновите страницу и нажмите «Удалить» ещё раз.')}#demand",
        status_code=303,
    )
