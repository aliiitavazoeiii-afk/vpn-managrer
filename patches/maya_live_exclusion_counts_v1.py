# HESAB_MAYA_EXCLUSION_COUNTS_V1
# Count explicit personal/exempt clients separately from accounts requiring review.
# Runtime-only presentation and reporting, NO financial/XUI modifications.
_MA_EXCLUDED_REASONS={"manual_excluded","legacy_excluded"}
_MA_ORIGINAL_ONE=_ml_one

def _ml_one(server,db):
    report=_MA_ORIGINAL_ONE(server,db)
    excluded=sum(
      not row["sid"] and row.get("reason") in _MA_EXCLUDED_REASONS
      for row in report["rows"]
    )
    needs_review=sum(
      not row["sid"] and row.get("reason") not in _MA_EXCLUDED_REASONS
      for row in report["rows"]
    )
    report["excluded"]=excluded
    report["unmatched"]=needs_review
    return report

# Avoid changing existing dashboard/homepage styles or controls.
# Only the control-room-v2 embedded display labels are adjusted.
_MA_CTRL_TEMPLATE=TEMPLATES["control_room.html"]
_MA_REPLACEMENTS=[
 (
  'count(data.unmatched)+" بدون تطبیق"',
  'count(data.excluded||0)+" مستثنا · "+count(data.unmatched)+" نیازمند بررسی"'
 ),
 (
  'else create("small","تطبیق نشده",account);',
  'else create("small",["manual_excluded","legacy_excluded"].includes(item.reason)?'
  '"مستثنا":item.reason==="approved_account_not_active"?"حساب غیرفعال":"تطبیق نشده",account);'
 ),
 (
  'else create("small",item.control_ambiguous?"تعارض ورودی":"نیازمند تطبیق",controls);',
  'else create("small",item.control_ambiguous?"تعارض ورودی":'
  '["manual_excluded","legacy_excluded"].includes(item.reason)?"بدون نیاز":"نیازمند تطبیق",controls);'
 )
]
for _ma_before,_ma_after in _MA_REPLACEMENTS:
    if _MA_CTRL_TEMPLATE.count(_ma_before)!=1:
        raise RuntimeError("Maya exception labels could not be safely applied")
    _MA_CTRL_TEMPLATE=_MA_CTRL_TEMPLATE.replace(_ma_before,_ma_after)
TEMPLATES["control_room.html"]=_MA_CTRL_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
