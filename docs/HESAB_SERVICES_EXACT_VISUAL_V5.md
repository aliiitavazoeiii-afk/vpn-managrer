# Hesab Customer Services — exact visual V5 release

Date: 2026-10-26. Owner chose a specific 1312×1190 Persian dashboard reference image and requested faithful deployment, including the original artwork of 3D server with green LEDs, speedometer, globe, and a large headset customer-support agent extending above the card.

## Release archive

- File: `releases/hesab_exact_visual_v5.zip.b64` (ASCII base64; decode to a ZIP).
- Decoded ZIP SHA-256: `4f88a25a32777f19d6adecbcff5d678671c7993735e87579f7714852b3c04841`.
- Archive contains source HTML/CSS/Python, 4 JPEG crops directly derived from the owner-provided reference design, a preview page, and the guarded installer `scripts/install_hesab_exact_visual_v5.sh`.
- This archive is source material, not an installed production release. Real browser verification remains required.

## Design fidelity and functional boundaries

- Desktop layout matches reference: server status on top right, subscription at top left; Radar right and Speedtest left; full-width support card below with operator illustration extending above the top edge. Supports narrow mobile screens.
- Header, shadows, white cards, black buttons, green WhatsApp button, blue telephone button, Persian Estedad first and Vazirmatn fallback.
- Dates and debt are NOT hardcoded: existing `_sv2_landing` renders live subscription amounts and expiry via existing account data. Payments link goes to `/?view=payments`; `/payments/history` is the existing read-only history route.
- Browser Cloudflare speed test uses previously committed `services_ui_v2.js`, and official Cloudflare Radar public Iran outages page is external.
- The pictured 3D server green LEDs/check icon are **decorative, not telemetry**. Live server health is unconfigured; label must remain pending and statistics unmeasured. The 99.9% / online values in design sketch must NOT be fabricated.
- The owner has not provided production support phone/WhatsApp; current `_sv2_phone()` and `_sv2_whatsapp()` return null without verified configured env. In that case render attractive nonclickable placeholders, never invent phone links.
- Existing phone-only session authorization is a pre-existing privacy limitation; financial history should be treated accordingly and proper OTP security considered separately.

## Production installation

- Installer copies only a new visual module, its HTML/CSS and 4 images; appends an isolated Dockerfile layer after the existing V3 layer; builds/recreates only `customer-portal`. It leaves Finance PostgreSQL, broker/X-UI, SMS gateway, admin app, Caddy and Compose config untouched.
- The production Compose command currently appends a bind-mounted `customer_portal/login_activity.py` after starting from the image. This route wrapper shadowed previous V3. The V5 installer appends an idempotent-safe handoff shim to that existing mounted file, preserving `_pla_home_with_activity` and its daily audit; it supports both V4 installed and V4 not installed.
- Preflight requires the existing V3 `_sv2_landing` in runtime and active login activity overlay. Source/route mismatch -> stop without modifying files. Backs up modified sources under `/root/hesab-exact-visual-v5-backup-TIMESTAMP`. On installation/build/health/test failure attempts portal-only rollback. It does not delete volumes or mutate customer finance.
- CI-ish local tests passed in the authoring container: archive integrity `unzip -t`, Bash `bash -n`, `python -m py_compile`, and Jinja render for 1- and 3-account templates. No SSH access or real server deployment performed, and full browser visual comparison not claimed.
- Sample screenshot preview in the ZIP contains mock amounts and contacts only. Do not ship them as real account info.
