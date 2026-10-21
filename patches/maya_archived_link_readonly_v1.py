# HESAB_MAYA_ARCHIVED_LINK_READONLY_V1
# Allow explicit archived #24 to be shown as linked on control-room while retaining
# its cut/archived finance status. Never permit a toggle of an archived account.
_MAR_OLD_RESOLVE=_ml_resolve

def _ml_resolve(server, clients, db):
    rows=_MAR_OLD_RESOLVE(server,clients,db)
    if server!="maya1":return rows
    approved=_ma_approved().get("maya1",{})
    if approved.get("afrogh hooman")!={"sid":24}:
        return rows
    states=_followup_states(db)
    if states.get(24)!="cut":
        return rows  # original resolver handles non-archived accounts
    # The exact operator-approved identity only. Never link another XUI client.
    matched=[r for r in rows if r["email"].strip().casefold()=="afrogh hooman"]
    if len(matched)!=1: return rows
    row=matched[0]
    if row["sid"] is not None: return rows
    sub=db.get(Subscription,24)
    if sub is None: return rows
    # If another XUI client already mapped #24, never duplicate it.
    if any(r["sid"]==24 for r in rows):return rows
    row["sid"]=24
    row["name"]=str(sub.display_name or "")
    row["finance_state"]="cut"
    row["expiry"]=sub.expiry_date.isoformat() if sub.expiry_date else ""
    row["reason"]="approved_archived_read_only"
    row["control_ambiguous"]=True  # both UI toggle and backend toggle fail closed
    return rows

_MAR_TEMPLATE=TEMPLATES["control_room.html"]
_MAR_ORIGINAL='item.control_ambiguous?"تعارض ورودی"'
_MAR_REPLACEMENT='item.reason==="approved_archived_read_only"?"آرشیوشده · فقط نمایش":item.control_ambiguous?"تعارض ورودی"'
if _MAR_TEMPLATE.count(_MAR_ORIGINAL)!=1:
    raise RuntimeError("Maya archived UI state template has changed")
_MAR_TEMPLATE=_MAR_TEMPLATE.replace(_MAR_ORIGINAL,_MAR_REPLACEMENT)
TEMPLATES["control_room.html"]=_MAR_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
