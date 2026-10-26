# HESAB_CUSTOMER_SERVICES_AFTER_LOGIN_ACTIVITY_V4
# Appended to the existing mounted customer_portal/login_activity.py.
# That runtime overlay replaces GET / after the image-baked services V2.
# Keep the login-report wrapper and its audit behavior, but route its content
# through the new services page (which itself preserves checkout fallback).
if not callable(globals().get("_sv2_landing")):
    raise RuntimeError("Services V2 landing missing; refuse route handoff")
if not callable(globals().get("_pla_home_with_activity")):
    raise RuntimeError("Login activity home handler missing; refuse route handoff")
if globals().get("_pla_previous_home") is not v2_home:
    raise RuntimeError("Unexpected login activity upstream home; refuse route handoff")
_svcv4_home_routes = [
    route for route in app.router.routes
    if getattr(route, "path", None) == "/"
    and "GET" in (getattr(route, "methods", set()) or set())
]
if len(_svcv4_home_routes) != 1:
    raise RuntimeError("Expected exactly one GET / route for safe handoff")
_svcv4_route = _svcv4_home_routes[0]
if (
    _svcv4_route.endpoint is not _pla_home_with_activity
    or _svcv4_route.dependant.call is not _pla_home_with_activity
):
    raise RuntimeError("Login activity wrapper is not the current route; refuse handoff")
_pla_previous_home = _sv2_landing
# The endpoint stays _pla_home_with_activity: current daily login report remains.
