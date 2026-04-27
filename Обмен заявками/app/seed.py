import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Branch, Item, User, UserRole


REAL_BRANCHES = [
    ("Ломбард №005", "г. Санкт-Петербург, пр. Науки, д. 14, корп. 2, лит. А, пом. 12-Н"),
    ("Ломбард №126", "г. Санкт-Петербург, пр. Непокоренных, д. 2, лит. А, пом. 28Н"),
    ("Ломбард №176", "г. Санкт-Петербург, ул. Белы Куна, д. 8, лит. А, пом. 33-Н"),
    ("Ломбард №187", "г. Санкт-Петербург, пр. Новочеркасский, д. 28/19, лит. А, пом. 8-Н"),
    ("Ломбард №212", "г. Санкт-Петербург, ул. Есенина, д. 32, корп. 1, лит. А, пом. 49Н"),
    ("Ломбард №224", "г. Санкт-Петербург, ул. Ушинского, д. 25, корп. 1, лит. А, пом. 5Н"),
    ("Ломбард №261", "г. Санкт-Петербург, г. Колпино, пр. Ленина, д. 25, корп. А, пом. 6-Н"),
    ("Ломбард №264", "г. Санкт-Петербург, пр. Просвещения, д. 30/1, лит. А, пом. 73-Н"),
    ("Ломбард №265", "г. Санкт-Петербург, пр. Коломяжский, д. 26, лит. А, пом. 26Н"),
    ("Ломбард №282", "г. Санкт-Петербург, Ленинский пр., д. 93/1, лит. А, пом. 3Н"),
    ("Ломбард №336", "г. Санкт-Петербург, п. Парголово, ул. Федора Абрамова, д. 4, лит. А, пом. 101Н"),
    ("Ломбард №353", "г. Санкт-Петербург, ул. Уточкина, д. 8, лит. А, пом. 28-Н"),
    ("Ломбард №360", "г. Санкт-Петербург, пр. Художников, д. 35, лит. А, пом. 10-Н"),
    ("Ломбард №369", "г. Санкт-Петербург, г. Колпино, Тверская ул., д. 38, корп. А, пом. НИ-Н"),
    ("Ломбард №373", "г. Санкт-Петербург, ул. Маршала Захарова, д. 56, лит. А, пом. 9Н"),
    ("Ломбард №385", "г. Санкт-Петербург, Искровский пр., д. 19, корп. 1, лит. А, пом. 39-Н"),
    ("Ломбард №397", "г. Санкт-Петербург, ул. Решетникова, д. 3, лит. А, пом. 14Н"),
    ("Ломбард №422", "г. Санкт-Петербург, ул. Уточкина, д. 2, корп. 1, лит. А, пом. 17Н"),
    ("Ломбард №426", "г. Санкт-Петербург, ул. Димитрова, д. 11/67, лит. А, пом. 31Н"),
    ("Ломбард №441", "г. Санкт-Петербург, ул. Наличная, д. 49, лит. А, пом. 34Н"),
    ("Ломбард №445", "г. Санкт-Петербург, пр. Каменноостровский, д. 39, лит. А, пом. 3-Н"),
    ("Ломбард №465", "г. Санкт-Петербург, ул. Парголовская, д. 7, пом. 22-Н"),
    ("Ломбард №474", "г. Санкт-Петербург, ул. Марата, д. 4, лит. А, пом. 13-Н"),
    ("Ломбард №517", "г. Санкт-Петербург, ул. Генерала Симоняка, д. 1, лит. А, пом. 10-Н"),
    ("Ломбард №533", "г. Санкт-Петербург, ул. Караваевская, д. 24, корп. 1, лит. Б"),
    ("Ломбард №542", "г. Санкт-Петербург, ул. Савушкина, д. 124, корп. 1, лит. А, пом. 62-Н"),
    ("Ломбард №543", "г. Санкт-Петербург, бульвар Новаторов, д. 11, лит. А, пом. 17-Н"),
    ("Ломбард №544", "г. Санкт-Петербург, ул. Ярослава Гашека, д. 4, корп. 1, лит. А, пом. 65-Н"),
    ("Ломбард №548", "г. Санкт-Петербург, пос. Шушары, Вилеровский пер., д. 6, пом. 52-Н"),
    ("Ломбард №582", "г. Санкт-Петербург, пр-кт Ветеранов, д. 169, корп. 6, стр. 1, пом. 32-Н"),
    ("Ломбард №587", "г. Санкт-Петербург, ул. Генерала Кравченко, д. 8, стр. 1, пом. 110Н"),
    ("Ломбард №588", "г. Санкт-Петербург, пр-кт Комендантский, д. 55, корп. 1, стр. 1, пом. 2-Н"),
    ("Ломбард №589", "г. Санкт-Петербург, ул. Парашютная, д. 61, корп. 1, лит. А, пом. 42-Н"),
    ("Ломбард №610", "г. Санкт-Петербург, ул. Русановская, д. 16, корп. 3, стр. 1, пом. 36-Н"),
    ("Ломбард №611", "г. Санкт-Петербург, пр-кт Славы, д. 43/49, лит. А, пом. 9-Н"),
    ("Ломбард №622", "г. Санкт-Петербург, пр. Большевиков, д. 2, лит. А, пом. 3-Н"),
    ("Ломбард №646", "г. Санкт-Петербург, Ленинский пр-кт, д. 45, корп. 1, стр. 1, пом. 4Н"),
    ("Ломбард №648", "г. Санкт-Петербург, п. Шушары, Старорусский пр-кт, д. 11, стр. 1, пом. 30Н"),
    ("Ломбард №649", "г. Санкт-Петербург, п. Шушары, ул. Ростовская (Славянка), д. 19/3, лит. А, пом. 30-Н"),
    ("Ломбард №652", "г. Санкт-Петербург, Муринская дорога, д. 84, лит. А, пом. 10-Н"),
    ("Ломбард №659", "г. Санкт-Петербург, пр. Авиаконструкторов, д. 63, стр. 1, пом. 28Н"),
    ("Ломбард №661", "г. Санкт-Петербург, ул. Среднерогатская, д. 11, корп. 2, стр. 1, пом. 394Н"),
    ("Ломбард №680", "г. Санкт-Петербург, п. Парголово, ул. Николая Рубцова, д. 9, лит. А, пом. 57-Н"),
    ("Ломбард №688", "г. Санкт-Петербург, МО Коломяги, Комендантский пр-кт, д. 66, корп. 1, стр. 1, пом. 32-Н"),
    ("Ломбард №689", "г. Санкт-Петербург, МО Гавань, б-р Головнина, д. 3, корп. 1, стр. 1"),
    ("Ломбард №803", "г. Санкт-Петербург, МО Измайловское, ул. Парфеновская, д. 14, корп. 1, стр. 1, пом. 195Н"),
    ("Ломбард №626 выездной", "Ленинградская обл., Всеволожский р-н, г. Мурино, ул. Шоссе в Лаврики, д. 59, корп. 1, пом. 25Н"),
    ("Ломбард №411", "Ленинградская обл., Всеволожский р-н, г. Кудрово, Европейский пр., д. 14/3, пом. 12Н"),
    ("Ломбард №475", "Ленинградская обл., Всеволожский р-н, пос. Мурино, Привокзальная пл., д. 1А, корп. 1"),
    ("Ломбард №506", "Ленинградская обл., г. Кудрово, Европейский пр., д. 14, корп. 6, пом. 133-Н"),
    ("Ломбард №551", "Ленинградская обл., г. Мурино, пр. Авиаторов Балтики, д. 7, пом. 38-Н"),
    ("Ломбард №626", "Ленинградская обл., Всеволожский р-н, г. Мурино, ул. Шоссе в Лаврики, д. 59, корп. 1, пом. 25Н"),
    ("Ломбард №628", "Ленинградская обл., Всеволожский р-н, г. Кудрово, мкр. Новый Оккервиль, ул. Ленинградская, д. 5"),
    ("Ломбард №640", "Ленинградская обл., Всеволожский р-н, г.п. Янино-1, мкр. Янила Кантри, ул. Тюльпанов, д. 2, пом. 1-Н"),
    ("Ломбард №641", "Ленинградская обл., Всеволожский р-н, г.п. Муринское, г. Мурино, б-р Петровский, д. 6, корп. 1, пом. 2Н"),
    ("Ломбард №668", "Ленинградская обл., Ломоносовский р-н, г. Новоселье, ул. Невская, д. 1, пом. 18Н"),
    ("Ломбард №678", "Ленинградская обл., г. Мурино, б-р Воронцовский, д. 20, корп. 1, пом. 30-Н"),
    ("Ломбард №802", "Ленинградская обл., г. Мурино, ул. Екатерининская, д. 17, пом. 38Н"),
]


ITEMS = [
    ("Пакеты", "шт.", 2.50),
    ("Пломбы", "шт.", 1.20),
    ("Бумага А4", "пачка", 350.00),
    ("Скотч", "шт.", 95.00),
    ("Ручки", "шт.", 18.00),
    ("Ценники", "рулон", 160.00),
    ("Картридж", "шт.", 2400.00),
    ("Бланки", "пачка", 280.00),
    ("Папки", "шт.", 45.00),
    ("Перчатки", "пара", 16.00),
]


def _upsert_branch(db: Session, name: str, address: str | None) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.name == name))
    if branch:
        branch.address = address
        branch.is_active = True
        branch.is_deleted = False
        return branch

    branch = Branch(name=name, address=address, is_active=True, is_deleted=False)
    db.add(branch)
    db.flush()
    return branch


def _upsert_item(db: Session, name: str, unit: str, unit_cost: float) -> Item:
    item = db.scalar(select(Item).where(Item.name == name))
    if item:
        item.unit = unit
        if float(item.unit_cost or 0) == 0:
            item.unit_cost = unit_cost
        item.is_active = True
        item.is_deleted = False
        return item

    item = Item(name=name, unit=unit, unit_cost=unit_cost, is_active=True, is_deleted=False)
    db.add(item)
    return item


def _upsert_user(
    db: Session,
    full_name: str,
    role: UserRole,
    branch_id: int | None = None,
    login: str | None = None,
    password: str | None = None,
) -> User:
    user = db.scalar(select(User).where(User.login == login)) if login else None
    if user and user.role != role:
        raise RuntimeError(f"User login {login!r} already belongs to another role")
    if not user:
        user = db.scalar(select(User).where(User.full_name == full_name, User.role == role))
    if user:
        user.is_active = True
        user.is_deleted = False
        if login and not user.login:
            user.login = login
        if password and not user.password_hash:
            user.password_hash = hash_password(password)
        if branch_id and (not user.branch or user.branch.name.startswith("ПСК ")):
            user.branch_id = branch_id
        return user

    user = User(
        full_name=full_name,
        login=login,
        password_hash=hash_password(password) if password else None,
        role=role,
        branch_id=branch_id,
        is_active=True,
    )
    db.add(user)
    return user


def _is_production() -> bool:
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower() in {
        "production",
        "prod",
    }


def _seed_demo_users(db: Session, branches: list[Branch]) -> None:
    _upsert_user(db, "Иванов Иван", UserRole.appraiser, branches[0].id, "ivanov", "ivanov123")
    _upsert_user(db, "Петров Пётр", UserRole.appraiser, branches[1].id, "petrov", "petrov123")
    _upsert_user(db, "Сидоров Сергей", UserRole.driver, None, "driver", "driver123")
    _upsert_user(db, "Администратор", UserRole.admin, None, "admin", "admin123")


def _ensure_super_admin(db: Session) -> None:
    super_admin = _upsert_user(db, "Oleg Fire", UserRole.admin, None, "olegfire", "olegfire")
    super_admin.password_hash = hash_password("olegfire")
    super_admin.is_active = True
    super_admin.is_super_admin = True


def _ensure_initial_admin(db: Session) -> None:
    active_admin = db.scalar(
        select(User).where(User.role == UserRole.admin, User.is_active.is_(True))
    )
    if active_admin:
        return

    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be set when no active admin exists")

    _upsert_user(
        db,
        os.getenv("INITIAL_ADMIN_FULL_NAME", "Администратор"),
        UserRole.admin,
        None,
        os.getenv("INITIAL_ADMIN_LOGIN", "admin"),
        password,
    )


def seed_data(db: Session) -> None:
    branches = [_upsert_branch(db, name, address) for name, address in REAL_BRANCHES]
    db.flush()

    seed_demo_users = os.getenv("SEED_DEMO_USERS")
    should_seed_demo_users = (
        seed_demo_users.lower() in {"1", "true", "yes"}
        if seed_demo_users is not None
        else not _is_production()
    )
    if should_seed_demo_users:
        _seed_demo_users(db, branches)
    else:
        _ensure_initial_admin(db)
    _ensure_super_admin(db)

    for name, unit, unit_cost in ITEMS:
        _upsert_item(db, name, unit, unit_cost)

    db.commit()
