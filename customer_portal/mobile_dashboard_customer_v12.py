# HESAB_MOBILE_CUSTOMER_V12
# Additive MOBILE PRESENTATION only, appended to the mounted customer_portal/
# login_activity.py. No login, billing, payments, XUI, surveys or downloads
# are modified. All existing Jinja variables and form routes stay intact.
from fastapi.responses import Response as _hcm12_Response
from jinja2 import Environment as _hcm12_Jinja
import re as _hcm12_re

_HCM12_STYLE=r'''
/* HESAB MOBILE V12 — self-contained responsive customer portal rules.
   Desktop (>=861px) is unchanged; no sections or actions are removed. */
@media (max-width:860px){
  html{font-size:16px;-webkit-text-size-adjust:100%;overflow-x:clip}
  body{min-width:0;max-width:100%;overflow-x:clip}
  :is(.sv2,.shell,.login-shell){box-sizing:border-box;min-width:0;max-width:100%}
  .sv2 .sv-shell{width:100%;max-width:100%;padding:16px 14px calc(32px + env(safe-area-inset-bottom,0px))!important;
    box-sizing:border-box}
  .sv2 .sv-top{display:flex;align-items:center;gap:10px;justify-content:space-between;
    padding-bottom:12px!important;flex-wrap:wrap}
  .sv2 .sv-brand{min-width:0;gap:9px}
  .sv2 .sv-brand b{font-size:14px;line-height:1.5}
  .sv2 .sv-logo{width:43px;height:43px;flex:none;border-radius:13px}
  .sv2 .sv-logo img{width:37px;height:37px}
  .sv2 .sv-top-actions{margin-inline-start:auto}
  .sv2 .sv-logout{min-height:43px;padding:8px 13px;white-space:nowrap}
  .sv2 .sv-phone{display:none}
  .sv2 .sv-greeting{margin:10px 2px 16px;align-items:center}
  .sv2 .sv-greeting h1{font-size:27px!important;line-height:1.45}
  .sv2 .sv-greeting-tag{font-size:9px;letter-spacing:.4px}
  .sv2 .sv-top-grid,.sv2 .sv-feature-grid{
    display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:12px!important;
    margin-bottom:12px}
  .sv2 .sv-box{min-width:0;max-width:100%;padding:18px 17px!important;
    border-radius:20px!important;box-sizing:border-box}
  .sv2 .sv-heading{gap:10px;align-items:flex-start;flex-wrap:wrap}
  .sv2 .sv-heading>div:not(.sv-heading-icon){min-width:0}
  .sv2 .sv-heading-icon{width:43px;height:43px;border-radius:13px;flex:none}
  .sv2 .sv-heading h2{font-size:19px;line-height:1.5}
  .sv2 .sv-heading p{font-size:11px;line-height:1.8}
  .sv2 .sv-count{margin-inline-start:auto;white-space:nowrap}
  .sv2 .sv-duo{display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:9px!important;margin:16px 0 14px!important}
  .sv2 .sv-metric{min-width:0;min-height:107px;padding:13px 10px;border-radius:14px}
  .sv2 .sv-metric-label{font-size:11px;gap:5px}
  .sv2 .sv-mini{width:22px;height:22px}
  .sv2 .sv-metric strong{font-size:clamp(17px,4vw,23px)!important;
    white-space:normal!important;overflow-wrap:anywhere;line-height:1.55}
  .sv2 :is(.sv-main-button,.sv-line-button,.sv-feature-button){
    min-height:46px;min-width:0;max-width:100%;
    white-space:normal!important;line-height:1.7;padding:11px 12px;
    font-size:13px;text-align:center;box-sizing:border-box}
  .sv2 .sv-server{min-height:0!important;gap:10px}
  .sv2 .sv-server::before{width:180px;height:180px;top:35px}
  .sv2 .sv-server-art{margin:0 auto;min-height:110px;width:100%;max-width:260px;flex:initial}
  .sv2 .sv-server-art svg{width:100%;max-height:142px}
  .sv2 .sv-server-footer{min-height:43px;margin-top:0;padding:10px 12px;
    flex-wrap:wrap;gap:9px}
  .sv2 .sv-server-caption{font-size:11px;display:inline}
  .sv2 .sv-feature{min-height:0!important;display:flex!important;
    flex-direction:row!important;align-items:center!important;
    gap:10px!important;padding:18px!important}
  .sv2 .sv-feature-copy{min-width:0;flex:1}
  .sv2 .sv-feature h2{font-size:17px;line-height:1.6}
  .sv2 .sv-feature p{font-size:11px;line-height:1.85;
    margin:4px 0 12px;max-width:none}
  .sv2 .sv-feature-button{width:100%;max-width:260px;min-width:0;
    display:flex!important;justify-content:space-between}
  .sv2 .sv-icon3d{width:100px!important;min-width:75px!important;
    max-width:100px!important;height:110px!important;flex:none;
    align-self:center!important;margin:0!important}
  .sv2 .sv-icon3d svg{max-height:110px}
  .sv2 .sv-support{display:flex!important;flex-direction:column!important;
    align-items:stretch!important;padding:20px 17px!important;gap:6px;
    min-height:0!important}
  .sv2 .sv-support h2{font-size:23px}
  .sv2 .sv-support p{font-size:12px;line-height:1.95;margin:5px 0 14px}
  .sv2 .sv-support-actions{display:grid!important;grid-template-columns:minmax(0,1fr)!important;
    gap:9px;align-items:stretch}
  .sv2 .sv-support-actions :is(a,.sv-disabled){min-height:46px;min-width:0;width:100%;
    box-sizing:border-box;padding:12px 11px;font-size:13px}
  .sv2 .sv-support-graphic{width:min(220px,60%);height:128px;align-self:center;
    flex:none;margin-top:0}
  .sv2 .sv-support-graphic svg{max-height:128px}
  .sv2 .sv-speed-panel{max-width:100%;min-width:0;margin-top:12px}
  .sv2 .sv-speed-controls{display:flex;flex-direction:column;
    gap:10px;align-items:stretch}
  .sv2 .sv-speed-controls .sv-main-button{width:100%;min-width:0;margin:0}
  .sv2 .sv-result-grid{display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:9px}
  .sv2 .sv-result-grid>div{padding:13px 9px;min-width:0}
  .sv2 .sv-result-grid strong{font-size:15px;overflow-wrap:anywhere}
  /* Private .npvs card is optional, but whenever enabled it is kept visible. */
  .sv2 .sv-private-file{display:flex!important;align-items:stretch!important;
    flex-direction:column!important;gap:14px!important}
  .sv2 .sv-private-file .sv-file-heading{gap:10px;align-items:center}
  .sv2 .sv-file-icon{width:48px;height:48px;border-radius:13px}
  .sv2 .sv-private-file h2{font-size:18px}
  .sv2 .sv-file-action{width:100%;min-height:46px;box-sizing:border-box}
  .sv2 .sv-footer{line-height:1.8}
  /* Legacy payment/debt dashboard: full-width, touch-friendly forms. */
  .shell{width:calc(100% - 24px)!important;max-width:100%!important;
    margin-inline:auto;padding:14px 0 calc(28px + env(safe-area-inset-bottom,0px))!important}
  .shell :is(.topbar,.brand,.top-actions,.section-head,.account-top,
   .account-actions,.renew-total){min-width:0;max-width:100%;flex-wrap:wrap}
  .shell .topbar{gap:10px!important;margin-bottom:14px!important}
  .shell .brand{min-width:0;gap:10px}
  .shell .brandcopy{min-width:0;overflow-wrap:anywhere}
  .shell .top-actions{margin-inline-start:auto}
  .shell .logout{min-height:45px;padding:9px 13px}
  .shell .stats{display:grid!important;grid-template-columns:minmax(0,1fr)!important;
    gap:12px!important}
  .shell .stat{min-width:0;min-height:0!important;padding:16px!important}
  .shell .stat strong{overflow-wrap:anywhere;white-space:normal}
  .shell .renew-all{display:grid!important;grid-template-columns:minmax(0,1fr)!important;
    gap:12px!important;padding:18px!important}
  .shell .renew-total{flex-direction:column;align-items:stretch;gap:12px}
  .shell .renew-price{max-width:100%;overflow-wrap:anywhere}
  .shell .renew-all form,.shell .renew-all button{width:100%!important}
  .shell .section-head{align-items:flex-start;gap:8px}
  .shell .account-card{max-width:100%;min-width:0;padding:15px!important;
    border-radius:17px}
  .shell .account-top{flex-direction:column;align-items:stretch}
  .shell .account-meta{display:grid!important;grid-template-columns:minmax(0,1fr)!important;
    gap:9px!important}
  .shell .expiry-shift{min-width:0;max-width:100%;gap:5px}
  .shell .account-actions{display:flex!important;flex-direction:column!important;
    gap:8px;align-items:stretch}
  .shell .account-actions :is(a,button){width:100%!important;min-height:45px;max-width:100%}
  .shell .account-card :is(h2,h3,p,strong,small){overflow-wrap:anywhere}
  .shell :is(input,select,textarea){font-size:16px!important;max-width:100%!important;
    box-sizing:border-box}
  /* Modal content must remain scrollable, not clipped on short phones. */
  .entry-modal{padding:12px!important;max-height:100dvh!important;overflow-y:auto!important;
    place-items:center}
  .entry-modal-card{box-sizing:border-box;width:100%!important;
    max-width:520px!important;max-height:calc(100dvh - 24px)!important;
    overflow-y:auto!important;padding:20px 17px!important;border-radius:19px!important}
  .entry-modal-card h2{font-size:19px!important}
  .entry-modal-card p{font-size:13px!important;line-height:2!important}
  .entry-modal-btn{min-height:47px}
  .login-shell,.login-panel{max-width:100%;min-width:0;box-sizing:border-box}
  .login-shell{width:calc(100% - 24px)!important;margin-inline:auto}
  .login-panel{padding:21px 17px!important}
  .login-panel h1{font-size:26px!important}
  .field input{max-width:100%;font-size:16px!important}
  /* Scroll wide transaction histories without changing table semantics. */
  .sv2 :is(.sv-history-list,.nf-rows,.sv-table-wrap){
    max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .sv2 .sv-history-row{gap:10px;flex-wrap:wrap}
  :is(.sv2,.shell) button,:is(.sv2,.shell) a{touch-action:manipulation}
}
@media (max-width:390px){
  .sv2 .sv-shell{padding-right:10px!important;padding-left:10px!important}
  .sv2 .sv-box{padding:15px 12px!important}
  .sv2 .sv-heading h2{font-size:17px}
  .sv2 .sv-duo{grid-template-columns:minmax(0,1fr)!important}
  .sv2 .sv-metric{min-height:78px}
  .sv2 .sv-feature{flex-direction:column-reverse!important;align-items:stretch!important}
  .sv2 .sv-icon3d{align-self:center!important}
  .sv2 .sv-feature-button{max-width:none}
  .sv2 .sv-greeting-tag{display:none}
  .shell{width:calc(100% - 18px)!important}
  .shell .expiry-shift{grid-template-columns:minmax(0,1fr) 36px minmax(0,1fr)}
}
@media (prefers-reduced-motion: reduce){
  .sv2 *,.shell *{scroll-behavior:auto!important}
}
'''
_HCM12_LINK='<link rel="stylesheet" href="/assets/mobile-dashboard-v12.css?v=1">'

_hcm12_targets=("_SV2_HTML","_V2_DASH","_V2_LOGIN",
                "_V2_PAYMENT_RETURN","_V2_SAFARI")
if ("_SV2_HTML" not in globals() or "_V2_DASH" not in globals()
    or not isinstance(_SV2_HTML,str) or not isinstance(_V2_DASH,str)):
    raise RuntimeError("MOBILE_V12_CUSTOMER_LAYOUT_NOT_LOADED")
_hcm12_edited=[]
for _hcm12_key in _hcm12_targets:
    _hcm12_html=globals().get(_hcm12_key)
    if not isinstance(_hcm12_html,str):
        continue
    if _hcm12_html.count(_HCM12_LINK):
        raise RuntimeError("MOBILE_V12_CUSTOMER_DUPLICATE_ASSET")
    matches=list(_hcm12_re.finditer("</head>",_hcm12_html,_hcm12_re.I))
    if len(matches)!=1:
        if _hcm12_key in ("_SV2_HTML","_V2_DASH","_V2_LOGIN"):
            raise RuntimeError("MOBILE_V12_CUSTOMER_HEAD_NOT_FOUND")
        continue
    _hcm12_html=_hcm12_re.sub(r"(?i)</head>",
                    lambda m:_HCM12_LINK+"\n"+m.group(),_hcm12_html,count=1)
    # Jinja templates use variables and existing URLs; keep exact content
    # except for one CSS asset link in <head>.
    _hcm12_Jinja().parse(_hcm12_html)
    globals()[_hcm12_key]=_hcm12_html
    _hcm12_edited.append(_hcm12_key)
if not all(k in _hcm12_edited for k in ("_SV2_HTML","_V2_DASH","_V2_LOGIN")):
    raise RuntimeError("MOBILE_V12_CUSTOMER_REQUIRED_PAGES_MISSING")
if any(getattr(route,"path",None)=="/assets/mobile-dashboard-v12.css"
       for route in app.router.routes):
    raise RuntimeError("MOBILE_V12_CUSTOMER_ASSET_ROUTE_COLLISION")

@app.get("/assets/mobile-dashboard-v12.css",include_in_schema=False)
def _hcm12_asset():
    return _hcm12_Response(_HCM12_STYLE,
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control":"public,max-age=86400",
                 "X-Content-Type-Options":"nosniff"})
