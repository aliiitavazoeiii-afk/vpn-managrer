#!/usr/bin/env python3
"""Install ONE read-only fixed-command SSH key on an Iran host (no restart).
Run locally as root with a PUBLIC key argument. Never asks for private keys.
Changes only: /usr/local/libexec/hesab_path_test_remote_v1.py and root authorized_keys.
"""
import base64
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

SRC=Path(__file__).with_name("hesab_path_test_remote_v1.py")
DEST=Path("/usr/local/libexec/hesab_path_test_remote_v1.py")
SSH_DIR=Path("/root/.ssh")
AUTH=SSH_DIR/"authorized_keys"
FORCED='/usr/bin/python3 /usr/local/libexec/hesab_path_test_remote_v1.py'

def atomic_copy(path,payload,mode):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing to overwrite symlink")
    fd,temp=tempfile.mkstemp(prefix=".hesab-probe-",dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,"wb") as file:
            file.write(payload);file.flush();os.fsync(file.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def run():
    if os.geteuid()!=0:
        raise PermissionError("Root required")
    if len(sys.argv)!=2:
        raise ValueError("Usage: installer.py 'ssh-ed25519 PUBLICKEY comment'")
    pub=sys.argv[1].strip().split()
    if len(pub) not in (2,3) or pub[0]!="ssh-ed25519":
        raise ValueError("Only ed25519 public key accepted")
    if not re.fullmatch(r"[A-Za-z0-9+/]{40,160}={0,2}",pub[1]):
        raise ValueError("Invalid public-key string")
    try:
        raw=base64.b64decode(pub[1],validate=True)
        if not raw or len(raw)>150:
            raise ValueError("Invalid key size")
    except Exception:
        raise ValueError("Invalid encoded public key")
    if not SRC.is_file() or SRC.is_symlink() or SRC.stat().st_size>20000:
        raise ValueError("Reviewed probe source not found")
    if not Path("/usr/bin/curl").is_file():
        raise ValueError("curl must be installed; will not install packages")
    import ast
    ast.parse(SRC.read_text(encoding="utf8"))
    keypart=" ".join(pub[:2])
    option='restrict,command="'+FORCED+'" '
    desired=option+keypart+" hesab-transfer-readonly"
    if SSH_DIR.is_symlink() or (SSH_DIR.exists() and not SSH_DIR.is_dir()):
        raise ValueError("Unexpected /root/.ssh type")
    if not SSH_DIR.exists():
        SSH_DIR.mkdir(mode=0o700)
    if AUTH.is_symlink():
        raise ValueError("Refusing symlink authorized_keys")
    old=AUTH.read_text(encoding="utf8") if AUTH.is_file() else ""
    matches=[line for line in old.splitlines() if pub[1] in line]
    if matches and matches!=[desired]:
        raise ValueError("Existing same SSH key has different authorization; refusing to modify")
    if not matches:
        backup=AUTH.with_name("authorized_keys.before-hesab-path-test-"+time.strftime("%Y%m%d%H%M%S"))
        if AUTH.is_file():
            shutil.copy2(AUTH,backup)
        amended=old.rstrip("\n")+"\n"+desired+"\n"
        atomic_copy(AUTH,amended.encode(),0o600)
        print("SSH_KEY=INSTALLED_RESTRICTED")
    else:
        print("SSH_KEY=ALREADY_RESTRICTED")
    atomic_copy(DEST,SRC.read_bytes(),0o755)
    print("PATH_TEST_REMOTE=INSTALLED")
    print("PERMITTED_COMMANDS=hesab-path-test-preflight,hesab-path-test-v1")
    print("SCHEDULED_PROBES=NO")
    print("TUNNEL_SERVICES_CHANGED=NO")
    print("FIRST_ACTIVE_TEST=ONLY_WHEN_DASHBOARD_BUTTON_CLICKED")

if __name__=="__main__":
    try:run()
    except (OSError,ValueError,PermissionError) as exc:
        print("PATH_TEST_INSTALL_STOP",type(exc).__name__,str(exc)[:100])
        sys.exit(1)
