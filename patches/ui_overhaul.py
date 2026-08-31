# UI-only cache busting. No routes, models, billing or workflow logic are changed.
_base_tpl = TEMPLATES.get("base.html", "")
if _base_tpl:
    for _v in range(2, 20):
        _base_tpl = _base_tpl.replace(f'/static/app.css?v={_v}', '/static/app.css?v=20')
        _base_tpl = _base_tpl.replace(f'/static/app.js?v={_v}', '/static/app.js?v=20')
    TEMPLATES["base.html"] = _base_tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)
