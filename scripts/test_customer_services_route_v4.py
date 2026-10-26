"""Regression tests for customer services V4 / login activity precedence."""
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
patch=(ROOT/"customer_portal/services_after_login_activity_v4.py").read_text(encoding="utf8")
activity=(ROOT/"customer_portal/login_activity.py").read_text(encoding="utf8")
compile(activity+"\n"+patch,"login_activity_with_services_v4.py","exec")

def old(request): return "old"
def new(request): return "new"
def audit(request): return "audited"
route=SimpleNamespace(path="/",methods={"GET"},endpoint=audit,dependant=SimpleNamespace(call=audit))
namespace={
    "__builtins__":__builtins__,
    "app":SimpleNamespace(router=SimpleNamespace(routes=[route])),
    "v2_home":old,
    "_sv2_landing":new,
    "_pla_home_with_activity":audit,
    "_pla_previous_home":old,
}
exec(compile(patch,"services_after_login_activity_v4.py","exec"),namespace)
assert namespace["_pla_previous_home"] is new
assert route.endpoint is audit and route.dependant.call is audit
# Changed route handler must abort rather than silently overriding another patch.
bad_route=SimpleNamespace(path="/",methods={"GET"},endpoint=old,dependant=SimpleNamespace(call=old))
fail={**namespace, "app":SimpleNamespace(router=SimpleNamespace(routes=[bad_route])),"_pla_previous_home":old}
try:
    exec(compile(patch,"services_after_login_activity_v4.py","exec"),fail)
except RuntimeError as exc:
    assert "wrapper" in str(exc) or "route" in str(exc)
else:
    raise AssertionError("Unknown home override must be rejected")
print("PASS: audit wrapper preserved; services delegated; unknown override rejected")
