#!/usr/bin/env python3
"""Prepare dedicated MANUAL transfer-test identity on the account host.
This does not SSH, run probes, alter Dual monitoring key, or change any service.
"""
import os
from pathlib import Path
import subprocess
import sys

KEY=Path("/root/.ssh/hesab_transfer_test_v1")
CORRECT={"maya1":"94.184.4.38","maya-s3":"185.215.230.221",
         "maya4":"5.10.249.206"}

def main():
    if os.geteuid()!=0:
        raise PermissionError("root required")
    sys.path.insert(0,"/opt/vpn-control-center/scripts")
    from maya_dual_hourly_collect_v1 import validate_config
    config=validate_config()
    for name,ip in CORRECT.items():
        if name not in config or config[name]["host"]!=ip:
            raise ValueError("Dual V1 Maya host mapping differs from verified source")
    KEY.parent.mkdir(mode=0o700,exist_ok=True)
    if KEY.is_symlink() or KEY.with_suffix(".pub").is_symlink():
        raise ValueError("Refusing symlink identity")
    if not KEY.exists():
        subprocess.run(["/usr/bin/ssh-keygen","-q","-t","ed25519","-N","",
                        "-C","hesab-fixed-transfer-v1","-f",str(KEY)],
                       check=True,stdin=subprocess.DEVNULL,timeout=20)
    if KEY.stat().st_mode&0o077:
        raise PermissionError("Private key file permissions unsafe")
    public=Path(str(KEY)+".pub")
    if not public.is_file():
        raise ValueError("Public key file missing")
    value=public.read_text(encoding="ascii").strip()
    if not value.startswith("ssh-ed25519 "):
        raise ValueError("Unexpected public key")
    print("=== COPY THIS PUBLIC KEY FOR ALL 3 IRAN SERVERS ===")
    print(value)
    print("=== END PUBLIC KEY ===")
    print("PREPARED_HOSTS=maya1,maya-s3,maya4")
    print("CURRENT_DUAL_SSH_IDENTITY_UNCHANGED=YES")
    print("ACTIVE_DOWNLOAD_TESTS_EXECUTED=NO")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,PermissionError,subprocess.CalledProcessError) as e:
        print("TRANSFER_PREP_STOP",type(e).__name__,str(e)[:120])
        raise SystemExit(1)
