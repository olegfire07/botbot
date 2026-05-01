from datetime import timedelta

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Request as GoodsRequest
from app.models import utc_now


def main() -> None:
    db = SessionLocal()
    try:
        today = utc_now().date()
        start_date = today - timedelta(days=29)
        req_counts = db.execute(
            select(func.date(GoodsRequest.created_at).label("d"), func.count(GoodsRequest.id))
            .where(GoodsRequest.created_at >= start_date)
            .group_by(func.date(GoodsRequest.created_at))
        ).all()
        print("Req counts:", req_counts)
    finally:
        db.close()


if __name__ == "__main__":
    main()
