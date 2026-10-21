# HESAB_MAYA_MANUAL_LINKS_V1
# Override ONLY the in-memory XUI->subscription resolution. No financial writes.
# Never toggle a VPN client here. Approval data stays on management host, not git.
import json as _ma_json
import stat as _ma_stat
from pathlib import Path as _ma_Path

_MA_FILE=_ma_Path("/srv/maya-live/approved_links.json")

def _ma_approved():
    if not _MA_FILE.exists():return {}
    if _MA_FILE.stat().st_mode & (_ma_stat.S_IRWXG | _ma_stat.S_IRWXO):
        raise ValueError("Maya approved mapping must be 0600")
    if _MA_FILE.stat().st_size>120000:
        raise ValueError("Maya approved mapping too large")
    obj=_ma_json.loads(_MA_FILE.read_text(encoding="utf8"))
    if obj.get("format")!="HESAB_MAYA_APPROVALS_V1":
        raise ValueError("Unknown Maya mapping format")
    servers=obj.get("servers")
    if not isinstance(servers,dict) or any(s not in _ML_SERVERS for s in servers):
        raise ValueError("Unknown Maya server in approval file")
    for server,links in servers.items():
        if not isinstance(links,dict):
            raise ValueError("Invalid Maya approval map")
        ids=set()
        for key,item in links.items():
            if not isinstance(key,str) or not key or key!=key.casefold():
                raise ValueError("Invalid normalized Maya XUI account")
            if not isinstance(item,dict) or (
              (set(item)=={"sid"} and type(item["sid"]) is int and item["sid"]>0) is False
              and (set(item)=={"exclude"} and item["exclude"] is True) is False
            ):
                raise ValueError("Invalid Maya approval entry")
            if "sid" in item:
                if item["sid"] in ids:
                    raise ValueError("Duplicate subscription approval on one Maya server")
                ids.add(item["sid"])
    return servers

def _ml_resolve(server,clients,db):
    index,active,old,states=_ml_financial_mapping(db)
    approved=_ma_approved().get(server,{})
    seen_emails=set()
    # Reserve manual IDs before matching: automatic guesses must never outrank
    # user-approved links, even when the XUI roster order changes.
    reserved={int(v["sid"]) for k,v in approved.items() if "sid" in v}
    used=set()
    rows=[]
    for c in clients:
        email=str(c.get("email") or "").strip()
        key=email.casefold()
        if not email or key in seen_emails:
            raise ValueError("Missing/duplicate Maya XUI email")
        seen_emails.add(key)
        sid=None
        reason="unmatched_review"
        explicit=approved.get(key)
        prior=old.get(key) if server=="maya1" else None
        if explicit is not None:
            if explicit.get("exclude") is True:
                reason="manual_excluded"
            else:
                desired=int(explicit["sid"])
                if desired not in active:
                    reason="approved_account_not_active"
                elif desired in used:
                    reason="approved_duplicate"
                else:
                    sid=desired
                    used.add(sid)
                    reason="manual_approved"
        elif server=="maya1" and isinstance(prior,dict):
            if prior.get("id") is None:
                reason="legacy_excluded"
            elif (prior.get("reason") in ("confirmed","exact_approved")
                 and type(prior.get("id")) is int
                 and prior["id"] in active and prior["id"] not in reserved
                 and prior["id"] not in used):
                sid=prior["id"]
                used.add(sid)
                reason="approved_maya1"
            else:
                reason="legacy_unavailable"
        else:
            matches=index.get(_ml_normalize(email),[])
            if len(matches)==1:
                candidate=int(matches[0].id)
                if candidate not in used and candidate not in reserved:
                    sid=candidate
                    used.add(sid)
                    reason="exact_name"
                else:
                    reason="exact_name_conflict"
        sub=active.get(sid) if sid else None
        def intval(v):
            try:return max(0,int(v or 0))
            except (TypeError,ValueError):return 0
        rows.append({
          "email":email,"sid":sid,
          "name":sub.display_name if sub else "",
          "finance_state":(states.get(sid) or "normal") if sub else "",
          "expiry":sub.expiry_date.isoformat() if sub and sub.expiry_date else "",
          "reason":reason,
          "control_ambiguous":bool(c.get("control_ambiguous",False)),
          "client_enabled":bool(c.get("client_enabled",c.get("enabled",False))),
          "enabled":bool(c.get("enabled",False)),
          "up":intval(c.get("up_bytes")),"down":intval(c.get("down_bytes")),
          "quota":intval(c.get("quota_bytes")),
          "last_online":intval(c.get("last_online_ms"))
        })
    return rows
