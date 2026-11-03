#!/usr/bin/env bash
# HESAB_MONTHLY_VALUE_AUDIT_READONLY_V1
# Read-only live comparison of the dashboard monthly recurring fee SUM.
# NO billing refresh, POST, DB write, XUI action, credentials or names output.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center || exit 2
dc(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
echo "=== HESAB MONTHLY SUBSCRIPTION VALUE AUDIT (READ-ONLY) ==="
dc exec -T app python - <<'PY'
from collections import Counter,defaultdict
from datetime import datetime,timezone
from sqlalchemy import text
from app import main as m
import inspect, unicodedata

g=m.get_db()
db=next(g)
try:
    db.execute(text("SET TRANSACTION READ ONLY"))
    states=m._followup_states(db)
    subscriptions=db.query(m.Subscription).order_by(m.Subscription.id).all()
    today=m.today_local()
    routes=[r for r in m.app.routes if getattr(r,"path",None)=="/"
        and "GET" in (getattr(r,"methods",set()) or set())]
    print("DATE_LOCAL",today.isoformat())
    print("DASHBOARD_GET_ROUTES",len(routes))
    for r in routes:
        func=r.endpoint
        print("DASHBOARD_HANDLER",getattr(func,"__name__","unknown"))
    template=m.TEMPLATES.get("ref_dashboard.html","")
    print("DASHBOARD_DISPLAYS_MONTHLY_INCOME", "stats.monthly_income" in template)
    print("SUBSCRIPTIONS_TOTAL",len(subscriptions))
    groups=defaultdict(lambda:{"n":0,"amount":0})
    included=[]
    included_wrong=[]
    details=[]
    normalize=lambda s:"".join(unicodedata.normalize("NFKC",str(s or "")).casefold().split())
    name_groups=defaultdict(list)
    fee_hist=Counter()
    no_fee=[]
    inactive_expired=[]
    anomalous=[]
    for s in subscriptions:
        sid=int(s.id)
        free=bool(s.is_free)
        fee=int(s.monthly_fee_toman or 0)
        state=states.get(sid) or "normal"
        if state not in ("normal","waiting","cut"):
            state="other"
        group=("free_" if free else "")+state
        groups[group]["n"]+=1
        groups[group]["amount"]+=fee
        if state!="cut" and not free:
            included.append((sid,fee,state))
            fee_hist[fee]+=1
            if fee<=0:
                no_fee.append((sid,fee,state))
            if fee>=1000000 or fee<0:
                anomalous.append((sid,fee,state))
            if s.expiry_date and s.expiry_date<today:
                inactive_expired.append((sid,fee,state))
            key=normalize(s.display_name)
            if key:name_groups[key].append((sid,fee,state))
        details.append((sid,fee,state,free))
    shown=sum(fee for _,fee,_ in included)
    print("=== EXACT CURRENT DASHBOARD RULE: not cut AND not free ===")
    print("DASHBOARD_MONTHLY_VALUE_TOMAN",shown)
    print("DASHBOARD_INCLUDED_PAID_SUBSCRIPTIONS",len(included))
    print("=== STATUS BREAKDOWN (fee sums, not payments) ===")
    for group,stats in sorted(groups.items()):
        print("CATEGORY",group,"count",stats["n"],"sum_toman",stats["amount"])
    waiting=sum(fee for _,fee,state in included if state=="waiting")
    waiting_n=sum(state=="waiting" for _,fee,state in included)
    normal=shown-waiting
    normal_n=len(included)-waiting_n
    print("NON_FREE_NON_CUT_NORMAL_VALUE_TOMAN",normal)
    print("NON_FREE_NON_CUT_NORMAL_COUNT",normal_n)
    print("NON_FREE_WAITING_VALUE_TOMAN",waiting)
    print("NON_FREE_WAITING_COUNT",waiting_n)
    print("REMOVING_WAITING_WOULD_CHANGE_TOTAL_BY_TOMAN",waiting)
    print("=== FEE DISTRIBUTION (ALL INCLUDED) ===")
    for fee,count in sorted(fee_hist.items(),key=lambda a:(-a[1],-a[0])):
        print("FEE_TOMAN",fee,"accounts",count,"contribution_toman",fee*count)
    print("=== ACCOUNTS NEEDING REVIEW (ID AND FEE ONLY) ===")
    print("NONPOSITIVE_FEES_COUNT",len(no_fee))
    for sid,fee,state in no_fee[:30]:
        print("NONPOSITIVE_FEE",sid,fee,state)
    print("FEES_1M_OR_MORE_COUNT",len(anomalous))
    for sid,fee,state in anomalous[:30]:
        print("HIGH_FEE",sid,fee,state)
    print("EXPIRED_BUT_NOT_CUT_COUNT",len(inactive_expired))
    print("EXPIRED_BUT_NOT_CUT_FEE_SUM",sum(fee for _,fee,_ in inactive_expired))
    for sid,fee,state in inactive_expired[:15]:
        print("EXPIRED_NOT_CUT",sid,fee,state)
    duplicates=[(k,v) for k,v in name_groups.items() if len(v)>1]
    print("DUPLICATE_EXACT_NORMALIZED_NAME_GROUPS",len(duplicates))
    print("NOTE: repeat names may be legitimate separate subscriptions; NO dedup performed.")
    for key,items in sorted(duplicates,key=lambda x:len(x[1]),reverse=True)[:12]:
        print("SAME_NAME_SUBS",",".join(str(i[0]) for i in items),
              "fees",",".join(str(i[1]) for i in items))
    print("=== CROSSCHECK RAW READ-ONLY SQL ===")
    sql=db.execute(text("SELECT COUNT(*),COALESCE(SUM(monthly_fee_toman),0) FROM subscriptions")).one()
    orm_count=len(details)
    orm_sum=sum(fee for _,fee,_,_ in details)
    print("RAW_TABLE_COUNT",sql[0],"ORM_COUNT",orm_count)
    print("RAW_TABLE_FEES_TOMAN",sql[1],"ORM_TABLE_FEES_TOMAN",orm_sum)
    assert sql[0]==orm_count and int(sql[1])==orm_sum,"Unexpected aggregate discrepancy"
    print("AUDIT_SUCCESS_READONLY")
except Exception as exc:
    print("AUDIT_ERROR",type(exc).__name__,str(exc)[:160])
    raise
finally:
    db.rollback()
    g.close()
PY
echo "=== DONE: NO ACCOUNT/BILLING/FINANCE CHANGES ==="
