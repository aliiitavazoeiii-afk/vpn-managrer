# Hesab VPN

Private VPN subscription/accounting panel for `hesab.filmjadiid.ir`.

## Data invariants
- 307 Excel subscriptions are seeded from encrypted `seed/users.enc`.
- Display names remain exactly as the source Excel labels.
- Shared phone numbers group subscriptions; subscriptions are never merged.
- Monthly fee and current debt are separate fields.
- `done/not done` is imported as the opening manual payment status.
- Expiry date is stored independently and displayed in Persian as day + Jalali month, e.g. `۸ مرداد`.
- Numeric Jalali format is used only inside the edit field so dates can be saved safely.
- Free accounts do not accrue debt.
- Decrypted seed SHA-256: `19abb64964dbef65622c46b4ff6b6a2bc7d09ab2de8882f12f1d5cf8a687691e`

## Deployment
Run `install.sh` on an Ubuntu/Debian management VPS. It intentionally removes the previous `/opt/vpn-control-center` database volume before installing this dataset.
