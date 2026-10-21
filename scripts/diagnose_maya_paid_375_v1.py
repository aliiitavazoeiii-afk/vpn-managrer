#!/usr/bin/env python3
"""Read-only verification why paid Maya3 #375 is not connected in X-UI.
No payment, control, financial, or client writes.
"""
import csv,io,json,os,socket,subprocess,sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
BASE=Path("/opt/vpn-control-center")
SOCK=BASE/"maya_extra_sync/live.sock"

def sql_read():
    query="""COPY (
      SELECT s.id, s.display_name, s.expiry_date, s.payment_status,
             COALESCE(s.debt_toman,0) AS debt_toman,
             (SELECT COUNT(*) FROM payments p WHERE p.subscription_id=s.id) AS payment_count,
             COALESCE((SELECT MAX(p.paid_at)::text FROM payments p WHERE p.subscription_id=s.id),'') AS last_payment_at
      FROM subscriptions s WHERE s.id=375
    ) TO STDOUT WITH CSV HEADER;"""
    cmd=["docker","compose","-f","docker-compose.yml","-f","docker-compose.sms.yml",
     "exec","-T","db","sh","-c",
     'PGOPTIONS="-c default_transaction_read_only=on" PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    p=subprocess.run(cmd,cwd=BASE,input=query,text=True,capture_output=True,timeout=60)
    if p.returncode:raise RuntimeError("Cannot read confirmed finance status")
    rows=list(csv.DictReader(io.StringIO(p.stdout)))
    if len(rows)!=1:raise RuntimeError("Billing ID #375 not found or ambiguous")
    return rows[0]

def xui_read():
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(90)
        sock.connect(str(SOCK))
        sock.sendall(b'{"op":"snapshot","server":"maya-s3"}\n')
        sock.shutdown(socket.SHUT_WR)
        raw=bytearray()
        while not raw.endswith(b"\n"):
            chunk=sock.recv(65536)
            if not chunk:break
            raw.extend(chunk)
            if len(raw)>3000000:raise RuntimeError("Oversized XUI response")
    result=json.loads(raw)
    if result.get("ok") is not True or result.get("snapshot",{}).get("server")!="maya-s3":
        raise RuntimeError("Live Maya3 unavailable")
    found=[x for x in result["snapshot"]["clients"] if x.get("email","").casefold()=="amanolahi bakhtiyari"]
    if len(found)!=1:raise RuntimeError("Cannot identify one specific Maya3 user")
    return found[0]

def main():
    if os.geteuid()!=0:raise RuntimeError("sudo/root required")
    import maya_multi_panel_sync as module
    accounts={int(r["id"]):r for r in module.dashboard()}
    finance=sql_read()
    remote=xui_read()
    state=accounts[375]["state"]
    today=datetime.now(ZoneInfo("Asia/Tehran")).date()
    print("ACCOUNT: #375 amanolahi bakhtiyari")
    print("BILLING: payment_status=",finance["payment_status"],
          "debt_toman=",finance["debt_toman"],
          "expiry_date=",finance["expiry_date"],
          "followup_state=",state)
    print("PAYMENTS: recorded_count=",finance["payment_count"],
          "last_recorded_at=",finance["last_payment_at"] or "NONE")
    print("XUI: client_enabled=",remote.get("client_enabled"),
          "inbound_enabled=",remote.get("inbound_enabled"),
          "effective_enabled=",remote.get("enabled"),
          "ambiguous=",remote.get("control_ambiguous",False))
    print("XUI LIMITS: quota_bytes=",remote.get("quota_bytes"),
          "used_bytes=",int(remote.get("up_bytes") or 0)+int(remote.get("down_bytes") or 0),
          "traffic_expiry_ms=",remote.get("traffic_expiry_ms"))
    if finance["payment_status"]=="paid" and int(finance["debt_toman"])==0 and state!="removed":
        print("BILLING_PAID_CONFIRMED_IN_DB: YES")
    else:
        print("BILLING_PAID_CONFIRMED_IN_DB: NO_OR_CONFLICT")
    if remote.get("client_enabled") is False:
        print("XUI_STATE: client enable switch is OFF; payment did not switch it ON")
    elif not remote.get("enabled"):
        print("XUI_STATE: client switch ON, but effective access OFF; check inbound and limits")
    else:
        print("XUI_STATE: client is ENABLED; inspect device/access traffic")
    print("READ_ONLY: no panel or financial data changed")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("DIAGNOSE_STOP:",type(e).__name__,str(e)[:160],file=sys.stderr)
        sys.exit(1)
