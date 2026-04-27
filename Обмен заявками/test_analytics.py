import sys
sys.path.append('.')
from sqlalchemy import select, func, text, case
from app.database import SessionLocal, apply_lightweight_migrations
from app.models import Request as GoodsRequest, RequestLine, DemandLine, DeliverySession, DeliverySessionLine, Item, Branch, DemandStatus, utc_now
from datetime import timedelta
apply_lightweight_migrations()
db = SessionLocal()

def _analytics(db, date_from=None, date_to=None):
    active_cond = DemandLine.status.in_((DemandStatus.active, DemandStatus.partially_delivered))
    active_res = db.execute(
        select(
            func.count(DemandLine.id),
            func.coalesce(func.sum(DemandLine.qty_remaining), 0),
            func.coalesce(func.sum(DemandLine.qty_remaining * Item.unit_cost), 0)
        ).select_from(DemandLine).join(Item).where(active_cond)
    ).first()
    active_positions, active_qty, active_cost = active_res or (0, 0, 0)

    req_query = select(
        func.coalesce(func.sum(RequestLine.qty_requested), 0),
        func.coalesce(func.sum(RequestLine.qty_requested * Item.unit_cost), 0)
    ).select_from(RequestLine).join(Item).join(GoodsRequest)
    
    if date_from:
        req_query = req_query.where(GoodsRequest.created_at >= date_from)
    if date_to:
        req_query = req_query.where(GoodsRequest.created_at < date_to + timedelta(days=1))
        
    requested_qty, requested_cost = db.execute(req_query).first() or (0, 0)

    del_query = select(
        func.coalesce(func.sum(DeliverySessionLine.qty_delivered_now), 0),
        func.coalesce(func.sum(DeliverySessionLine.qty_delivered_now * Item.unit_cost), 0)
    ).select_from(DeliverySessionLine).join(Item).join(DeliverySession)
    
    sess_query = select(func.count(DeliverySession.id))
    
    if date_from:
        del_query = del_query.where(DeliverySession.started_at >= date_from)
        sess_query = sess_query.where(DeliverySession.started_at >= date_from)
    if date_to:
        del_query = del_query.where(DeliverySession.started_at < date_to + timedelta(days=1))
        sess_query = sess_query.where(DeliverySession.started_at < date_to + timedelta(days=1))
        
    delivered_qty, delivered_cost = db.execute(del_query).first() or (0, 0)
    delivery_sessions_count = db.scalar(sess_query) or 0

    branch_rows_res = db.execute(
        select(
            Branch,
            func.count(DemandLine.id).label("positions"),
            func.sum(DemandLine.qty_remaining).label("qty"),
            func.sum(DemandLine.qty_remaining * Item.unit_cost).label("cost")
        ).select_from(DemandLine)
        .join(Branch)
        .join(Item)
        .where(active_cond)
        .group_by(Branch.id)
        .order_by(text("cost DESC"), text("qty DESC"))
        .limit(10)
    ).all()
    
    branch_rows = []
    max_branch_cost = 1
    if branch_rows_res:
        max_branch_cost = max(1, float(branch_rows_res[0].cost or 0))
    for row in branch_rows_res:
        branch_rows.append({
            "branch": row.Branch,
            "positions": row.positions,
            "qty": float(row.qty or 0),
            "cost": float(row.cost or 0),
            "percent": int((float(row.cost or 0) / max_branch_cost) * 100) if max_branch_cost else 0
        })

    item_rows_res = db.execute(
        select(
            Item,
            func.count(func.distinct(DemandLine.branch_id)).label("branches_count"),
            func.sum(DemandLine.qty_remaining).label("qty"),
            func.sum(DemandLine.qty_remaining * Item.unit_cost).label("cost")
        ).select_from(DemandLine)
        .join(Item)
        .where(active_cond)
        .group_by(Item.id)
        .order_by(text("cost DESC"), text("qty DESC"))
        .limit(10)
    ).all()

    item_rows = []
    max_item_cost = 1
    if item_rows_res:
        max_item_cost = max(1, float(item_rows_res[0].cost or 0))
    for row in item_rows_res:
        item_rows.append({
            "item": row.Item,
            "branches_count": row.branches_count,
            "qty": float(row.qty or 0),
            "cost": float(row.cost or 0),
            "percent": int((float(row.cost or 0) / max_item_cost) * 100) if max_item_cost else 0
        })

    active_branches = db.scalar(select(func.count(func.distinct(DemandLine.branch_id))).where(active_cond)) or 0

    return {
        "active_positions": active_positions,
        "active_branches": active_branches,
        "active_qty": float(active_qty),
        "active_cost": float(active_cost),
        "requested_qty": float(requested_qty),
        "requested_cost": float(requested_cost),
        "delivered_qty": float(delivered_qty),
        "delivered_cost": float(delivered_cost),
        "delivery_sessions_count": delivery_sessions_count,
        "branch_rows": branch_rows,
        "item_rows": item_rows,
    }

print(_analytics(db))
