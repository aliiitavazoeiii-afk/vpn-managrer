#!/usr/bin/env bash
# HESAB_MOBILE_DASHBOARD_V12_ROLLBACK
# Only revert the two UI source files from the exact install backup.
# Refuse if someone changed them after the install.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$#" == 1 ]] || {
 echo "USAGE=bash rollback_mobile_dashboard_v12.sh /root/hesab-mobile-dashboard-v12-YYYYMMDDTHHMMSSZ-PID"
 exit 2
}
BACKUP="$1"
case "$BACKUP" in
 /root/hesab-mobile-dashboard-v12-*) ;;
 *) echo "STOP=INVALID_BACKUP_DIRECTORY";exit 3 ;;
esac
[[ -d "$BACKUP" && ! -L "$BACKUP" ]] || { echo "STOP=BACKUP_MISSING";exit 3; }
for f in maya1_control.py login_activity.py installed-sha256.txt;do
 [[ -s "$BACKUP/$f" && ! -L "$BACKUP/$f" ]] ||
 { echo "STOP=INCOMPLETE_BACKUP $f";exit 3; }
done
ROOT=/opt/vpn-control-center
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
[[ -f patches/maya1_control.py && -f customer_portal/login_activity.py ]] ||
 { echo "STOP=SOURCE_FILES_MISSING";exit 3; }
grep -Fq '# HESAB_MOBILE_DASHBOARD_V12' patches/maya1_control.py ||
 { echo "STOP=ADMIN_MODULE_NOT_PRESENT";exit 3; }
grep -Fq '# HESAB_MOBILE_CUSTOMER_V12' customer_portal/login_activity.py ||
 { echo "STOP=CUSTOMER_MODULE_NOT_PRESENT";exit 3; }
sha256sum -c "$BACKUP/installed-sha256.txt" ||
 { echo "STOP=PRODUCTION_CHANGED_AFTER_INSTALL_NO_AUTO_OVERWRITE";exit 3; }
compose config -q
BEFORE="/root/hesab-mobile-v12-pre-rollback-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BEFORE"
cp -a patches/maya1_control.py "$BEFORE/maya1_control.py"
cp -a customer_portal/login_activity.py "$BEFORE/login_activity.py"
restore_current(){
 code=$?
 trap - EXIT
 if ((code!=0));then
   echo "ROLLBACK_FAILURE=RESTORE_INSTALLED_MOBILE_SOURCE"
   cp -a "$BEFORE/maya1_control.py" patches/maya1_control.py
   cp -a "$BEFORE/login_activity.py" customer_portal/login_activity.py
   compose up -d --no-deps --no-build --force-recreate app customer-portal ||
     echo "WARNING=RESTORE_RECREATE_FAILED"
 fi
 exit "$code"
}
trap restore_current EXIT
cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
cp -a "$BACKUP/login_activity.py" customer_portal/login_activity.py
python3 -m py_compile patches/maya1_control.py customer_portal/login_activity.py
compose up -d --no-deps --no-build --force-recreate app customer-portal
for name in app customer-portal;do
 ok=0
 for i in $(seq 1 30);do
  if [[ "$(compose ps --status running -q "$name")" != "" ]];then ok=1;break;fi
  sleep 2
 done
 [[ "$ok" == 1 ]] || { echo "STOP=ROLLBACK_SERVICE_FAILED $name";false; }
done
trap - EXIT
echo "SUCCESS=MOBILE_DASHBOARD_V12_ROLLED_BACK"
echo "RESTORED_FROM=$BACKUP"
echo "BEFORE_ROLLBACK_SOURCE=$BEFORE"
