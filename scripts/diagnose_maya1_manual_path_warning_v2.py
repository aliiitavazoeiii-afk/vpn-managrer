#!/usr/bin/env python3
"""Read-only, redacted source diagnosis for manual Mieru/Backhaul2 false warning.

The two production-only scripts are not present in the checked Git branch.
This prints only relevant function/condition fragments, never runs probes, and
does not access VPN data plane, systemd, sockets, SSH, credentials or DB.
"""
import ast
import hashlib
import re
from pathlib import Path

ROOT=Path("/opt/vpn-control-center")
TARGETS=(
 "scripts/hesab_manual_path_test_broker_v1.py",
 "scripts/maya_dual_passive_quality_v1.py",
 "patches/maya1_control.py",
)
MATCH=re.compile(
 r"mieru|backhaul|21002|21102|manual.path|test.path|test.path|"
 r"probe|quality|check|warning|هشدار|تست مسیر|/control-room/.{0,45}(test|path)",
 re.I)
SENSITIVE=re.compile(
 r"passwd|password|secret|token|bearer|authorization|"
 r"ssh_identity|private.key|api.key|cookie|credential|"
 r"client.email|user.email|phone|شماره",re.I)
EXTREME=re.compile(r"[A-Za-z0-9+/=]{100,}")
MAX_PER_FILE=100
MAX_CHARS=210

def scrub(line):
    if SENSITIVE.search(line):
        return "[REDACTED: sensitive source line]"
    line=EXTREME.sub("[REDACTED-LONG-STRING]",line)
    return line[:MAX_CHARS]+("..." if len(line)>MAX_CHARS else "")

def walk(path):
    print("\n=== "+str(path.relative_to(ROOT))+" ===")
    if not path.is_file() or path.is_symlink():
        print("MISSING_OR_SYMLINK");return
    data=path.read_bytes()
    if len(data)>1000000:
        print("STOP: source unexpectedly large");return
    src=data.decode("utf-8")
    lines=src.splitlines()
    print("SHA256="+hashlib.sha256(data).hexdigest())
    print("LINES="+str(len(lines)))
    try:
        tree=ast.parse(src)
        relevant=[]
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                definition="def "+node.name
                if MATCH.search(node.name):
                    relevant.append(definition+" @ "+str(node.lineno))
        if relevant:
            print("RELEVANT_FUNCTIONS="+", ".join(relevant[:30]))
    except SyntaxError:
        print("SOURCE_SYNTAX=UNPARSEABLE")
    matched=[i for i,line in enumerate(lines) if MATCH.search(line)]
    print("MATCHING_LINES="+str(len(matched)))
    if not matched:return
    # One source line of context around relevant matches, bounded output.
    show=set()
    for i in matched[:MAX_PER_FILE//2]:
        show.update((max(i-1,0),i,min(i+1,len(lines)-1)))
    for idx in sorted(show)[:MAX_PER_FILE]:
        print(str(idx+1).rjust(5)+" "+scrub(lines[idx]))
    if len(matched)>MAX_PER_FILE//2:
        print("MORE_MATCHES_HIDDEN="+str(len(matched)-MAX_PER_FILE//2))

for name in TARGETS:
    walk(ROOT/name)
print("\nMANUAL_PATH_WARNING_READ_ONLY_DIAGNOSTIC_COMPLETE")
