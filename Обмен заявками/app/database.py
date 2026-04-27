import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", PROJECT_ROOT / "sklad_requests.db"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH.as_posix()}")

if DATABASE_URL.startswith("sqlite:///") and DATABASE_URL != "sqlite:///:memory:":
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_lightweight_migrations() -> None:
    with engine.begin() as connection:
        item_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(items)")).fetchall()
        }
        if "unit_cost" not in item_columns:
            connection.execute(
                text("ALTER TABLE items ADD COLUMN unit_cost NUMERIC(12, 2) NOT NULL DEFAULT 0")
            )
        if "is_deleted" not in item_columns:
            connection.execute(
                text("ALTER TABLE items ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            )
        user_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        if "login" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN login VARCHAR(100)"))
        if "password_hash" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "is_super_admin" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT 0")
            )
        if "is_deleted" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_login_unique ON users(login)")
        )
        branch_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(branches)")).fetchall()
        }
        if "is_deleted" not in branch_columns:
            connection.execute(
                text("ALTER TABLE branches ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            )
        request_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(requests)")).fetchall()
        }
        if "is_deleted" not in request_columns:
            connection.execute(
                text("ALTER TABLE requests ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            )
        delivery_session_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(delivery_sessions)")).fetchall()
        }
        if "is_deleted" not in delivery_session_columns:
            connection.execute(
                text("ALTER TABLE delivery_sessions ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
            )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY,
                    actor_user_id INTEGER REFERENCES users(id),
                    action VARCHAR(100) NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    entity_id INTEGER,
                    details TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
