# حذف دائمی اکانت از پروفایل — V1 محافظت‌شده

Source: feat/profile-hard-delete-safeguarded-v1

This adds a separate **بررسی حذف دائمی از سامانه** button in the existing
\`/users/{sid}\` profile. The existing **انتقال به حذفی‌ها** archive action
is NOT replaced.

## Behavior

1. Open a user profile. The "مدیریت دائمی اکانت" section appears.
2. Select "بررسی حذف دائمی از سامانه". A read-only dependency check reports
   whether this specific subscription can be physically removed without
   corrupting finance, shared identities or SMS evidence.
3. For an eligible isolated subscription only: type "حذف <ID>", check the
   explicit backup/irreversibility acknowledgement and submit within 10 min.
4. The POST rechecks all constraints under a row lock and transaction, then
   deletes the subscription and its unambiguous per-account follow-up and
   user-creation audit events. The optional billing_anchor FK must be
   confirmed ON DELETE CASCADE; all other current FKs and non-FK references
   are examined. Unknown or shared dependencies cause refusal.
5. The user disappears from active, waiting, removed/archive and all-users
   views, because the subscription row no longer exists.

## Strong limits

- **Payment history or payment gateway allocations block deletion.** It
  would be misleading and dangerous to erase financial history automatically.
- SMS gateway/native drafts, browser SMS, any phone-bearing tables, uncertain
  audit entries, shared-phone subscriptions or unknown foreign keys also
  block deletion.
- Only standalone, unencumbered local records are eligible in this version.
- This is NOT a complete legal/privacy "right to be forgotten" implementation.
  Already-created database backups, archived dumps, export files, raw logs,
  external payment provider records, WhatsApp messages and Shahan/X-UI VPN
  users may remain. No automatic deletion or disconnection on VPN servers.
- Operator must ensure there is a separate verified backup BEFORE using the
  button; the installer creates one full verified pre-enablement backup.
- No deletion occurs during the installation. Actual deletion always requires
  a profile-specific two-stage confirmation and cross-origin guard.
- No changes to finance tables, SMS queue, customer portal or other
  subscriptions are performed by an ineligible user deletion attempt.

## Install on account-management host only

Use a fresh checkout (do not switch a dirty live tree):

    SRC="$(mktemp -d /root/hesab-hard-delete.XXXXXX)"
    git clone --depth 1 -b feat/profile-hard-delete-safeguarded-v1 \
      https://github.com/aliiitavazoeiii-afk/vpn-managrer.git "$SRC"
    python3 "$SRC/scripts/test_profile_hard_delete_v1.py"
    bash -n "$SRC/scripts/install_profile_hard_delete_v1.sh"
    bash "$SRC/scripts/install_profile_hard_delete_v1.sh"

The installer verifies existing /users/{sid}, /user-status and archive routes,
confirms the Compose app mount/startup layout, makes and verifies a full
PostgreSQL pg_dump and config backup, adds a new read-only bind-mounted patch,
recreates ONLY the admin app and probes the unauthenticated route to ensure
it is denied. On failure it restores the compose file and stops the feature.

Expected output:
\`SUCCESS=PROFILE_GUARDED_PERMANENT_DELETE_UI_INSTALLED\`

Deployment is NOT complete when GitHub is updated. Confirm success on the
management server and open an existing eligible user's profile to test the
two-stage preview WITHOUT submitting the irreversible deletion form.
