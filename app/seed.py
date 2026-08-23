import json
import os
from datetime import date
from sqlalchemy.orm import Session
from .models import User
from .config import settings


def seed_users_if_empty(db: Session):
    if db.query(User).count() > 0:
        return 0
    path = settings.seed_file
    if not os.path.exists(path):
        local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed", "users.json")
        path = local
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    count = 0
    for item in items:
        due = date.fromisoformat(item["due_date"]) if item.get("due_date") else None
        db.add(User(
            name=item["name"],
            phone=item.get("phone"),
            due_date=due,
            fee_toman=int(item.get("fee_toman") or 200000),
            payment_status=item.get("payment_status", "unpaid"),
            notes=item.get("notes", ""),
        ))
        count += 1
    db.commit()
    return count
