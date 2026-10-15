#!/usr/bin/env bash
# HESAB_BATCH_OPERATOR_OPEN_V4
# Works from existing native V2, with or without old V3 manual handoff.
# Does not send SMS, replay any job, or modify billing records during deployment.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: root required'; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for file in .env docker-compose.yml docker-compose.sms.yml sms_gateway/server.py patches/sms_native_v2.py; do
  [[ -s "$file" ]] || { echo "STOP: $file not found"; exit 3; }
done
c config -q
[[ -s "$SOURCE/sms_gateway/server.py" && -s "$SOURCE/patches/sms_native_v2.py" ]] || {
  echo 'STOP: source code missing'; exit 3;
}
python3 -m py_compile "$SOURCE/sms_gateway/server.py" "$SOURCE/patches/sms_native_v2.py"
grep -Fq '# NATIVE_SMS_V2_SEPARATE_QUEUE' sms_gateway/server.py || {
  echo 'STOP: native V2 not on this server. Do NOT run previous automatic-send installers.'; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || { echo 'STOP: V2 app mount absent'; exit 3; }
grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || {
  echo 'STOP: native admin patch absent'; exit 3;
}
c exec -T app grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py || {
  echo 'STOP: V2 admin not enabled in running container'; exit 3;
}
if grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py; then
  echo 'STOP: V4 marker already exists; inspect before installing twice'; exit 3
fi

python3 - "$SOURCE" <<'PY'
from pathlib import Path
import re,sys
source=Path(sys.argv[1])
live=Path("sms_gateway/server.py").read_text()
remote=(source/"sms_gateway/server.py").read_text()
assert remote.count("# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1")==1
assert remote.count("# GOOGLE_MESSAGES_SENT_FOLDER_V1")==1
assert remote.count("# GOOGLE_MESSAGES_BATCH_OPEN_V4")==1
assert remote.count('"/v4/drafts/pending"')==1
assert "# GOOGLE_MESSAGES_BATCH_OPEN_V4" not in live
if "# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1" in live:
    assert "class ManualDraftResult" in live
else:
    assert "# NATIVE_SMS_V2_SEPARATE_QUEUE" in live
p=Path("patches/sms_native_v2.py").read_text()
n=(source/"patches/sms_native_v2.py").read_text()
pattern=re.compile(r'_NS_SCRIPT\s*=\s*r"""<script>.*?</script>"""',re.S)
assert len(pattern.findall(p))==1, "STOP: cannot isolate live debt SMS Javascript"
assert len(pattern.findall(n))==1, "STOP: cannot isolate source debt SMS Javascript"
print("PASS: isolated V4 patch compatible with production")
PY

BACKUP="/opt/hesab-backups/manual-batch-v4-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a sms_gateway/server.py "$BACKUP/server.py"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo 'Creating a full PostgreSQL backup...'
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null

MODIFIED=0
rollback(){
  trap - ERR
  if [[ "$MODIFIED" == 1 ]]; then
    echo 'Deployment failure: rolling back V4 code only; never restoring DB without review.'
    cp -a "$BACKUP/server.py" sms_gateway/server.py
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c build sms-gateway || true
    c up -d --no-deps --no-build sms-gateway || true
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Backup: $BACKUP"; exit 1
}
trap rollback ERR
MODIFIED=1

python3 - "$SOURCE" <<'PY'
from pathlib import Path
import re,sys
source=Path(sys.argv[1])
f=Path("sms_gateway/server.py")
live=f.read_text()
latest=(source/"sms_gateway/server.py").read_text()
v3="# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1"
sent="# GOOGLE_MESSAGES_SENT_FOLDER_V1"
v4="# GOOGLE_MESSAGES_BATCH_OPEN_V4"
if v3 not in live:
    # Add only V3 model and draft APIs, never the sent-folder auto-detection.
    live=live.rstrip()+"\n\n"+v3+latest.split(v3,1)[1].split(sent,1)[0]
live=live.rstrip()+"\n\n"+v4+latest.split(v4,1)[1]
compile(live,str(f),"exec")
assert live.count(v4)==1 and live.count(v3)==1
f.write_text(live)
pf=Path("patches/sms_native_v2.py")
old=pf.read_text()
new=(source/"patches/sms_native_v2.py").read_text()
rx=re.compile(r'_NS_SCRIPT\s*=\s*r"""<script>.*?</script>"""',re.S)
replacement=rx.search(new).group()
patched,n=rx.subn(lambda _:replacement,old,count=1)
assert n==1
patched=patched.replace(
    "درخواست برای بازکردن Google Messages در گوشی ثبت شد؛ ارسال نهایی دستی است.",
    "پیامک در صف گوشی ثبت شد؛ با زدن بازکردن پیام در اپ، وضعیت در انتظار ثبت می‌شود.")
compile(patched,str(pf),"exec")
pf.write_text(patched)
PY

echo 'Rebuilding SMS API (no automatic sending) and refreshing admin UI...'
c build sms-gateway
c up -d --no-deps --no-build sms-gateway
c up -d --no-deps --no-build --force-recreate app
ok=0
for attempt in $(seq 1 40); do
  if c exec -T sms-gateway python - <<'PY' >/dev/null 2>&1
from server import app
paths={getattr(route,"path","") for route in app.routes}
assert "/v4/drafts/pending" in paths
assert "/v4/drafts/{job_id}/operator-open" in paths
PY
  then ok=1;break;fi
  sleep 2
done
test "$ok" == 1
ok=0
for attempt in $(seq 1 40); do
  if c exec -T app sh -lc 'grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py' >/dev/null 2>&1; then
    ok=1;break
  fi
  sleep 2
done
test "$ok" == 1
# Protected endpoint should challenge without gateway token, not 404.
http_code="$(curl -sS -o /dev/null -w '%{http_code}' \
  'https://hesab.filmjadiid.ir/sms-gateway/v4/drafts/pending?device_id=probe')"
echo "Public V4 check (without token): HTTP $http_code"
test "$http_code" == "401"
trap - ERR
echo 'SUCCESS: V4 pending queue installed. No SMS submitted and no debt state changed during install.'
echo "Backup: $BACKUP"
