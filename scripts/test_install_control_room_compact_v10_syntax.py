#!/usr/bin/env python3
"""Check V10 shell preflight's Python, including Bash quoting (prior outage).
No container, SSH or production writes.
"""
import ast
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INSTALLER=ROOT/"scripts/install_control_room_compact_v10.sh"
source=INSTALLER.read_text(encoding="utf8")
subprocess.run(["bash","-n",str(INSTALLER)],check=True)
start='cat "$PATCH" | compose exec -T app python -c \''
stop="'\necho \"=== VERIFY EXISTING 500GB PURCHASE EXACTLY ONCE ===\""
assert source.count(start)==1,start
offset=source.index(start)+len(start)
end=source.index(stop,offset)
py=source[offset:end]
assert "'" not in py, "Bash single-quoted Python -c code contains a quote"
ast.parse(py,filename="<real_v10_preflight_python_code>")
assert 'id=\\"c3-mode\\"' in py
assert 'id=\\"c2-users\\"' in py
assert 'b"id=\\"t9-topup-panel\\""' in py
assert "V10_ACTUAL_PAGE_RENDER_PREFLIGHT_OK" in py
heredocs=re.findall(r"<<'PY'[^\n]*\n([\s\S]*?)\nPY(?:\n|$)",source)
assert len(heredocs)==3,(len(heredocs),"unexpected V10 Python heredoc count")
for i,block in enumerate(heredocs):
    ast.parse(block,filename=f"<V10-heredoc-{i}>")
print("V10_BASH_SYNTAX_AND_ACTUAL_PYTHON_PREFLIGHT_AST_PASS")
