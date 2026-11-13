#!/usr/bin/env bash
# HESAB_CUSTOMER_SERVER_STATUS_ROLLBACK_V1
# Restore ONLY the exact UI files and compose overlay from a given backup.
# Abort if any of them changed after the original status installation.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$#" == 1 ]] || {
  echo "USAGE: bash $0 /root/hesab-customer-status-v1-TIMESTAMP-PID";exit 2;
}
BACKUP="$1"
case "$BACKUP" in /root/hesab-customer-status-v1-*) ;; *)
 echo "STOP=INVALID_STATUS_BACKUP_DIR";exit 3;; esac
[[ -d "$BACKUP" && ! -L "$BACKUP" ]] || {
 echo "STOP=BACKUP_NOT_AVAILABLE";exit 3; }
for f in maya1_control.py login_activity.py docker-compose.sms.yml installed-sha256.txt;do
 [[ -s "$BACKUP/$f" && ! -L "$BACKUP/$f" ]] ||
 { echo "STOP=INCOMPLETE_BACKUP $f";exit 3; }
done
cd /opt/vpn-control-center
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
grep -Fq HESAB_CUSTOMER_SERVER_STATUS_BRIDGE_V1 patches/maya1_control.py ||
 { echo "STOP=STATUS_ADMIN_MODULE_ABSENT";exit 3; }
grep -Fq HESAB_CUSTOMER_SERVER_STATUS_PORTAL_V1 customer_portal/login_activity.py ||
 { echo "STOP=STATUS_CUSTOMER_MODULE_ABSENT";exit 3; }
sha256sum -c "$BACKUP/installed-sha256.txt" ||
 { echo "STOP=PRODUCTION_FILES_CHANGED_SINCE_INSTALL";exit 3; }
compose config -q
BEFORE="/root/hesab-customer-status-pre-rollback-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BEFORE"
cp -a patches/maya1_control.py "$BEFORE/maya1_control.py"
cp -a customer_portal/login_activity.py "$BEFORE/login_activity.py"
cp -a docker-compose.sms.yml "$BEFORE/docker-compose.sms.yml"
restore(){
 code=$?
 trap - EXIT
 if ((code!=0));then
   echo "ROLLBACK_FAILED=RESTORING_PREVIOUS_DEPLOYMENT"
   cp -a "$BEFORE/maya1_control.py" patches/maya1_control.py
   cp -a "$BEFORE/login_activity.py" customer_portal/login_activity.py
   cp -a "$BEFORE/docker-compose.sms.yml" docker-compose.sms.yml
   compose up -d --no-deps --no-build --force-recreate app customer-portal ||
     echo "WARNING=RESTART_AFTER_ROLLBACK_FAILED"
 fi
 exit "$code"
}
trap restore EXIT
cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
cp -a "$BACKUP/login_activity.py" customer_portal/login_activity.py
cp -a "$BACKUP/docker-compose.sms.yml" docker-compose.sms.yml
python3 -m py_compile patches/maya1_control.py customer_portal/login_activity.py
compose config -q
compose up -d --no-deps --no-build --force-recreate app customer-portal
for svc in app customer-portal;do
 ok=0
 for i in $(seq 1 30);do
  if [[ -n "$(compose ps --status running -q "$svc")" ]];then ok=1;break;fi
  sleep 2
 done
 [[ "$ok" == 1 ]] || { echo "STOP=ROLLBACK_SERVICE_NOT_RUNNING $svc";false; }
done
trap - EXIT
echo "SUCCESS=CUSTOMER_SERVER_STATUS_V1_ROLLED_BACK"
echo "BACKUP_RESTORED=$BACKUP"
echo "PRE_ROLLBACK_COPY=$BEFORE"
echo "NOTE=OLD_ROOT_ONLY_HMAC_FILE_LEFT_IN_PLACE_FOR_SAFE_MANUAL_CLEANUP"
