#!/usr/bin/env python3
"""SHAHAN_AUTH_READONLY_PROBE_V1
Root-only ONE-SHOT local read check; no panel HTTP calls, no database mutations,
no shadow contents, no authentication attempts, no service restarts.
"""
import os,pwd,re,shutil,subprocess,sys
from pathlib import Path

DB="ShaHaN"
CHECK=("hodi","hadihoda","davari2")
HANDLERS=("/var/www/html/p/expire.php","/var/www/html/p/killusers.sh",
          "/var/www/html/p/user.php","/var/www/html/p/users.php")
TOKENS=(
  ("LINUX_ACCOUNT_CONTROL",("usermod","passwd -l","passwd -u","chage ","usermod -L","usermod -U")),
  ("DB_ENABLE_CONTROL",("update users","set enable","enable='false'","enable = 'false'")),
  ("SESSION_TERMINATION",("pkill","killall","kill -9","fuser","loginctl terminate")),
)
def run(args,timeout=6):
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                         text=True,timeout=timeout,env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin"})
        if p.returncode:return "UNAVAILABLE"
        return p.stdout.strip()[:180]
    except Exception:return "UNAVAILABLE"
def main():
    if os.geteuid()!=0:raise RuntimeError("Run as root on Shahan SSH server")
    print("READ-ONLY Shahan SSH user authentication diagnostics")
    for user in CHECK:
        try:
            info=pwd.getpwnam(user)
        except KeyError:
            print("USER",user,"NOT PRESENT");continue
        stat=run(["passwd","-S",user])
        tokens=stat.split()
        status=tokens[1] if len(tokens)>1 and tokens[0]==user else "UNKNOWN"
        print("USER",user,"LINUX_UID",info.pw_uid,
              "SHELL",Path(info.pw_shell).name,"PASSWD_STATUS",status)
    for name in ("ssh","sshd","dropbear"):
        print("SERVICE",name,"STATE",run(["systemctl","is-active",name]))
    print("SHAHAN_HANDLER_STATIC_SIGNS (presence only, never contents):")
    for file in HANDLERS:
        path=Path(file)
        if not path.is_file():
            print(Path(file).name,"ABSENT");continue
        if path.stat().st_size>400000:
            print(Path(file).name,"TOO_LARGE");continue
        try:
            content=path.read_bytes().lower()
        except OSError:
            print(Path(file).name,"UNREADABLE");continue
        results=[label for label,terms in TOKENS if any(x.encode() in content for x in terms)]
        print(Path(file).name,"bytes",len(content),"hints",",".join(results) if results else "NONE_OR_COMPILED")
    print("CHECK COMPLETE: no writes, no account changes")
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("SHAHAN_AUTH_STOP:",type(ex).__name__,str(ex)[:150],file=sys.stderr)
        sys.exit(1)
