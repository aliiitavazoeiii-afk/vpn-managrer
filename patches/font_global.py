# Global font loader only. No business logic changes.
import re

_base = TEMPLATES.get("base.html", "")
if _base:
    font_links = '''
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Estedad:wght@400;500;600;700;800&display=swap" rel="stylesheet">
'''
    if "family=Estedad" not in _base:
        if "</head>" in _base:
            _base = _base.replace("</head>", font_links + "\n</head>", 1)
        else:
            _base = font_links + _base

    # Force a new browser fetch of the final CSS bundle.
    _base = re.sub(
        r'/static/app\.css(?:\?v=[^"\']*)?',
        '/static/app.css?v=font-est-1',
        _base,
    )
    TEMPLATES["base.html"] = _base
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)
