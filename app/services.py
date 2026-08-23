from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import ServerSnapshot


def positive_delta(a: int, b: int) -> int:
    d = int(b or 0) - int(a or 0)
    return d if d >= 0 else 0


def _snaps(db: Session, server_id: int, since: datetime):
    return db.query(ServerSnapshot).filter(
        ServerSnapshot.server_id == server_id,
        ServerSnapshot.captured_at >= since,
    ).order_by(ServerSnapshot.captured_at.asc()).all()


def _series(snaps, bucket: str):
    buckets = defaultdict(int)
    total = 0
    prev = None
    for s in snaps:
        if prev:
            delta = positive_delta(prev.client_up_total + prev.client_down_total, s.client_up_total + s.client_down_total)
            total += delta
            if bucket == "day":
                key = s.captured_at.date()
            else:
                key = s.captured_at.replace(minute=0, second=0, microsecond=0)
            buckets[key] += delta
        prev = s
    points = []
    for k in sorted(buckets):
        label = k.strftime("%m/%d") if bucket == "day" else k.strftime("%H:%M")
        points.append({"label": label, "value": buckets[k]})
    return total, points


def traffic_summary(db: Session, server_id: int, hours: int = 24):
    snaps = _snaps(db, server_id, datetime.utcnow() - timedelta(hours=hours))
    total, points = _series(snaps, "hour")
    return {"total": total, "points": points, "snapshots": snaps}


def traffic_daily(db: Session, server_id: int, days: int = 7):
    snaps = _snaps(db, server_id, datetime.utcnow() - timedelta(days=days))
    total, points = _series(snaps, "day")
    return {"total": total, "points": points, "snapshots": snaps}
