#!/usr/bin/env python3
"""Print a ready-to-paste remote setup command using the dedicated PUBLIC key.
No SSH connection, no test download; run on account management host only.
"""
from pathlib import Path
import re
import shlex
import sys

PUB=Path("/root/.ssh/hesab_transfer_test_v1.pub")
def main():
    if len(sys.argv)!=2 or not re.fullmatch(r"[0-9a-f]{40}",sys.argv[1]):
        raise ValueError("Pass the reviewed GitHub commit SHA")
    if not PUB.is_file():
        raise ValueError("Generate dedicated transfer-test public key first")
    public=PUB.read_text(encoding="ascii").strip()
    if not public.startswith("ssh-ed25519 "):
        raise ValueError("Unexpected dedicated key")
    base=("https://raw.githubusercontent.com/"
          "aliiitavazoeiii-afk/vpn-managrer/"+sys.argv[1])
    print("=== COPY THE FOLLOWING SAME COMMAND ON EACH OF THE THREE MAYA IRAN SERVERS ===")
    print("set -Eeuo pipefail")
    print("D=/root/hesab-fixed-path-test")
    print("mkdir -p \"$D\"")
    for f in ("hesab_path_test_remote_v1.py","install_hesab_path_test_remote_v1.py"):
        print("curl -fsSLo \"$D/"+f+"\" "+shlex.quote(base+"/scripts/"+f))
    print("python3 \"$D/install_hesab_path_test_remote_v1.py\" "+shlex.quote(public))
    print("=== END COMMAND (RUN ON MAYA1, MAYA3, MAYA4) ===")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError) as e:
        print("BOOTSTRAP_PRINT_STOP",type(e).__name__)
        raise SystemExit(1)
