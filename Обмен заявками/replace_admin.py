import re

with open("app/routers/admin.py", "r") as f:
    content = f.read()

# 1. Replace _analytics
old_analytics = re.search(r"def _analytics\(.*?\)\s*->\s*dict\[str,\s*object\]:.*?return \{.*?\}", content, re.DOTALL)

new_analytics = """from sqlalchemy import func, text, case

def _analytics(db: Session, date_from: datetime | None = None, date_to: datetime | None = None) -> dict[str, object]:
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
    }"""
content = content.replace(old_analytics.group(0), new_analytics)

# 2. Update export_summary_xlsx
content = content.replace(
"""    branches = list(db.scalars(select(Branch).order_by(Branch.name)).all())
    requests = list(
        db.scalars(
            select(GoodsRequest)
            .options(selectinload(GoodsRequest.lines).selectinload(RequestLine.item))
        ).all()
    )
    demand_lines = list(
        db.scalars(
            select(DemandLine)
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
        ).all()
    )
    sessions = list(
        db.scalars(
            select(DeliverySession)
            .options(selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item))
        ).all()
    )
    analytics = _analytics(branches, requests, demand_lines, sessions)""",
"""    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    analytics = _analytics(db, df, dt)"""
)

# 3. Update export_summary.csv
content = content.replace(
"""    branches = list(db.scalars(select(Branch).order_by(Branch.name)).all())
    requests = list(
        db.scalars(
            select(GoodsRequest)
            .options(selectinload(GoodsRequest.lines).selectinload(RequestLine.item))
            .order_by(GoodsRequest.created_at.desc())
        ).all()
    )
    demand_lines = list(
        db.scalars(
            select(DemandLine)
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
        ).all()
    )
    sessions = list(
        db.scalars(
            select(DeliverySession)
            .options(selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item))
        ).all()
    )
    analytics = _analytics(branches, requests, demand_lines, sessions)""",
"    analytics = _analytics(db)"
)

# 4. Update admin_dashboard charts and calls
old_dashboard_start = """    requests = list(
        db.scalars(
            select(GoodsRequest)
            .options(
                selectinload(GoodsRequest.branch),
                selectinload(GoodsRequest.created_by),
                selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
            )
            .order_by(GoodsRequest.created_at.desc())
        ).all()
    )
    demand_lines = list(
        db.scalars(
            select(DemandLine)
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
            .order_by(DemandLine.last_updated_at.desc())
        ).all()
    )
    sessions = list(
        db.scalars(
            select(DeliverySession)
            .options(
                selectinload(DeliverySession.branch),
                selectinload(DeliverySession.driver),
                selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item),
            )
            .order_by(DeliverySession.started_at.desc())
        ).all()
    )
    analytics = _analytics(branches, requests, demand_lines, sessions)

    # Chart data: requests per day (last 30 days)
    chart_labels = []
    chart_requests = []
    chart_deliveries = []
    today = utc_now().date()
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        chart_labels.append(d.strftime("%d.%m"))
        chart_requests.append(sum(1 for r in requests if r.created_at.date() == d))
        chart_deliveries.append(sum(1 for s in sessions if s.started_at.date() == d))"""

new_dashboard_start = """    requests = list(
        db.scalars(
            select(GoodsRequest)
            .options(
                selectinload(GoodsRequest.branch),
                selectinload(GoodsRequest.created_by),
                selectinload(GoodsRequest.lines).selectinload(RequestLine.item),
            )
            .order_by(GoodsRequest.created_at.desc())
            .limit(50)
        ).all()
    )
    demand_lines = list(
        db.scalars(
            select(DemandLine)
            .options(selectinload(DemandLine.branch), selectinload(DemandLine.item))
            .order_by(DemandLine.last_updated_at.desc())
            .limit(50)
        ).all()
    )
    sessions = list(
        db.scalars(
            select(DeliverySession)
            .options(
                selectinload(DeliverySession.branch),
                selectinload(DeliverySession.driver),
                selectinload(DeliverySession.lines).selectinload(DeliverySessionLine.item),
            )
            .order_by(DeliverySession.started_at.desc())
            .limit(50)
        ).all()
    )
    analytics = _analytics(db)

    # Chart data: requests per day (last 30 days) using SQL
    today = utc_now().date()
    start_date = today - timedelta(days=29)
    req_counts = db.execute(
        select(
            func.date(GoodsRequest.created_at).label("d"),
            func.count(GoodsRequest.id)
        ).where(GoodsRequest.created_at >= start_date)
        .group_by(func.date(GoodsRequest.created_at))
    ).all()
    del_counts = db.execute(
        select(
            func.date(DeliverySession.started_at).label("d"),
            func.count(DeliverySession.id)
        ).where(DeliverySession.started_at >= start_date)
        .group_by(func.date(DeliverySession.started_at))
    ).all()
    req_map = {row[0]: row[1] for row in req_counts}
    del_map = {row[0]: row[1] for row in del_counts}

    chart_labels = []
    chart_requests = []
    chart_deliveries = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        chart_labels.append(d.strftime("%d.%m"))
        chart_requests.append(req_map.get(d_str, 0))
        chart_deliveries.append(del_map.get(d_str, 0))"""
        
content = content.replace(old_dashboard_start, new_dashboard_start)

with open("app/routers/admin.py", "w") as f:
    f.write(content)
