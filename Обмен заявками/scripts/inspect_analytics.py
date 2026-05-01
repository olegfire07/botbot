from app.database import SessionLocal, apply_lightweight_migrations
from app.routers.admin import _analytics


def main() -> None:
    apply_lightweight_migrations()
    db = SessionLocal()
    try:
        print(_analytics(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
