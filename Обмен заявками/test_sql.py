import sys
sys.path.append('.')
from sqlalchemy import select, func, text, case
from app.database import SessionLocal
from app.models import Request as GoodsRequest, RequestLine, DemandLine, DeliverySession, DeliverySessionLine, Item, Branch, DemandStatus, utc_now
from datetime import timedelta
db = SessionLocal()

today = utc_now().date()
start_date = today - timedelta(days=29)

req_counts = db.execute(
    select(
        func.date(GoodsRequest.created_at).label("d"),
        func.count(GoodsRequest.id)
    ).where(GoodsRequest.created_at >= start_date)
    .group_by(func.date(GoodsRequest.created_at))
).all()

print("Req counts:", req_counts)
