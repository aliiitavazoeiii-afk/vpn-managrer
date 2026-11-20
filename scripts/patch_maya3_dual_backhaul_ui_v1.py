#!/usr/bin/env python3
"""Patch ONLY already-deployed Dual Hourly V1 overlay in Control Room.

Keeps legacy server roles for Maya1/Maya4. Maya3 with mode=dual_backhaul
shows Backhaul 1 / Backhaul 2, never a fake Mieru-down warning.
Does not change any API route, CSRF policy, DB, Xray or tunnel settings.
The installer is responsible for backup, restart and rollback.
"""
from pathlib import Path
import ast
import sys

MARK="# HESAB_MAYA3_DUAL_BACKHAUL_VISUAL_V1"
ANCHOR='# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1'
OLD_OUTPUT='''                        "state": state, "age_s": age,
                        "paths": {role: _dh1_clean_path(paths.get(role))'''
NEW_OUTPUT='''                        "state": state, "age_s": age,
                        "mode": "dual_backhaul" if info.get("mode") == "dual_backhaul" else "legacy",
                        "paths": {role: _dh1_clean_path(paths.get(role))'''
OLD_ROLE='''add(row,"span",role==="backhaul"?"Backhaul":"Mieru","dh1-role");'''
NEW_ROLE='''const title=item.mode==="dual_backhaul"?
    (role==="backhaul"?"Backhaul 1":"Backhaul 2"):
    (role==="backhaul"?"Backhaul":"Mieru");
   add(row,"span",title,"dh1-role");'''
OLD_META='''add(card,"div",role+" · میانگین HTTPS: "+latency,"dh1-meta");'''
NEW_META='''add(card,"div",title+" · میانگین HTTPS: "+latency,"dh1-meta");'''

def transform(src):
    if MARK in src:
        raise ValueError("Maya3 dual-backhaul overlay already installed")
    if src.count(ANCHOR)!=1:
        raise ValueError("Expected one V1 Dual Hourly overlay")
    head, tail = src.split(ANCHOR,1)
    for old,name in ((OLD_OUTPUT,"snapshot mode"),(OLD_ROLE,"dual lane label"),
                     (OLD_META,"dual lane latency caption")):
        if tail.count(old)!=1:
            raise ValueError("Unexpected live V1 UI layout: "+name)
    tail=tail.replace(OLD_OUTPUT,NEW_OUTPUT,1)
    tail=tail.replace(OLD_ROLE,NEW_ROLE,1)
    tail=tail.replace(OLD_META,NEW_META,1)
    out=head+ANCHOR+tail+"\n"+MARK+"\n"
    ast.parse(out)
    return out

def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_maya3_dual_backhaul_ui_v1.py LIVE_ADMIN_OVERLAY_PATH")
    p=Path(sys.argv[1])
    if not p.is_file() or p.is_symlink():
        raise SystemExit("STOP: overlay missing or symlink")
    original=p.read_text(encoding="utf-8")
    revised=transform(original)
    p.write_text(revised,encoding="utf-8")
    print("MAYA3_ROLE_UI_PATCHED: Backhaul1 + Backhaul2; other Maya servers unchanged")

if __name__=="__main__":
    main()
