#!/usr/bin/env python3
"""SHAHAN_SSH_READONLY_PROBE_V1

Run ON SHAHAN VPS once as root; no daemon, cron, service restart, panel HTTP,
credential dump, or any changes to Shahan's database.

Read MariaDB metadata and at most 2000 user rows via local Unix socket.
Only selected allowlisted nonsecret fields are exported root-only.
"""
import csv
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path

OUT=Path("/root/shahan_users_review.tsv")
USERNAME_COLUMNS=("username","user_name","user","sshusername","ssh_user","login","name")
STATUS_COLUMNS=("status","userstatus","active","enabled","enable","is_active","is_enabled","disabled","is_disabled","useractive","state")
ID_COLUMNS=("id","userid","user_id")
SAFE_FIELD=re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")

def run_sql(statement,timeout=9):
    cmd=shutil.which("mariadb") or shutil.which("mysql")
    if not cmd:raise RuntimeError("MariaDB/MySQL client not installed")
    p=subprocess.run([cmd,"--protocol=socket","--connect-timeout=3",
       "--default-character-set=utf8mb4","--batch","--raw",
       "--skip-column-names","--silent","-e",statement],
       capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("Local MariaDB read-only query failed; inspect socket/root access")
    if len(p.stdout)>650000:raise RuntimeError("Database result too large")
    return [x.split("\t") for x in p.stdout.splitlines()]

def q(s):
    if not SAFE_FIELD.fullmatch(s):raise RuntimeError("Unsafe schema identifier")
    return chr(96)+s+chr(96)

def main():
    if os.geteuid()!=0:
        raise RuntimeError("Run with sudo/root on Shahan VPS")
    print("SHAHAN PROBE V1: READ ONLY; no panel HTTP requests, config changes or restarts",flush=True)
    dbs=run_sql("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
      "WHERE LOWER(SCHEMA_NAME)='shahan' LIMIT 2")
    if len(dbs)!=1 or len(dbs[0])!=1:
        print("DB NOT FOUND: check panel installation / MariaDB access")
        return
    schema=dbs[0][0]
    if not SAFE_FIELD.fullmatch(schema):raise RuntimeError("Unsafe schema name")
    rows=run_sql("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
      "WHERE TABLE_SCHEMA="+repr(schema)+" AND LOWER(TABLE_NAME)='users' LIMIT 2")
    if len(rows)!=1:raise RuntimeError("Shahan users table not found or ambiguous")
    table=rows[0][0]
    columns=run_sql("SELECT COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
      "WHERE TABLE_SCHEMA="+repr(schema)+" AND TABLE_NAME="+repr(table)+" "
      "ORDER BY ORDINAL_POSITION LIMIT 100")
    types={name.lower():(name,ty) for name,ty in columns if len(name)<=64}
    print("DB:",schema,"TABLE:",table)
    print("COLUMN_NAMES_AND_TYPES (no secret values):")
    for name,typ in columns:
        print(" ",name,":",typ)
    uname=next((types[x][0] for x in USERNAME_COLUMNS if x in types),None)
    state=next((types[x][0] for x in STATUS_COLUMNS if x in types),None)
    ident=next((types[x][0] for x in ID_COLUMNS if x in types),None)
    if not uname:
        print("UNKNOWN USERNAME COLUMN: no user details exported")
        return
    cols=[uname]+([ident] if ident and ident!=uname else [])+([state] if state and state not in (uname,ident) else [])
    query="SELECT "+",".join(q(c) for c in cols)+" FROM "+q(schema)+"."+q(table)+" LIMIT 2000"
    data=run_sql(query,timeout=10)
    if len(data)==2000:
        print("WARNING: 2000-row safety limit reached; snapshot incomplete")
    unix={p.pw_name:p.pw_shell for p in pwd.getpwall()}  # never reads shadow hashes
    exported=[]
    for r in data:
        if len(r)!=len(cols):continue
        record=dict(zip(cols,r))
        username=str(record[uname]).strip()
        if not username or len(username)>128 or "\n" in username:continue
        exported.append({
            "ssh_username":username,
            "shahan_user_id":record.get(ident,"") if ident else "",
            "shahan_state_raw":record.get(state,"") if state else "",
            "linux_account_exists":str(username in unix).lower(),
            "linux_shell":unix.get(username,"").rsplit("/",1)[-1],
        })
    if OUT.exists():
        raise RuntimeError("Export exists; refusing overwrite. Rename it before re-run.")
    fd=os.open(OUT,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=[
          "ssh_username","shahan_user_id","shahan_state_raw","linux_account_exists","linux_shell"],
          delimiter="\t")
        w.writeheader();w.writerows(exported)
    print("SHAHAN USER ROWS:",len(exported))
    print("MATCHING UNIX ACCOUNTS:",sum(x["linux_account_exists"]=="true" for x in exported))
    print("SAVED:",OUT,"MODE: 0600")
    print("No passwords, hashes, API tokens or financial data exported.")
    print("FINISHED READ ONLY; no service or user changes.")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("SHAHAN_PROBE_STOP:",type(e).__name__,str(e)[:160],file=sys.stderr)
        sys.exit(1)
