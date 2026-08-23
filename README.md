# VPN Control Center

Personal, agentless VPN customer/accounting and 3x-ui monitoring dashboard.

- Customer accounts, Persian/Jalali due dates, payment state and payment history
- Debtors/receivables view
- Multi-server 3x-ui read-only sync
- Online clients, Xray state, CPU/RAM/disk/network stats
- Local traffic history on the management server
- Excel import from the dashboard (`Settings`)
- No agent or extra service is installed on production VPN servers
- Ayria payment automation intentionally deferred to a later phase

## One-line install (Ubuntu/Debian management VPS)

```bash
curl -fsSL https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/main/install.sh | sudo bash
```

Then open the URL printed by the installer and sign in with the generated admin password.

## Import the real customer workbook

Do **not** commit real phone numbers/customer data to this public repository. After login open **Settings → Excel Import** and upload `vpn-sait.xlsx` from your computer. The workbook is processed in memory and is not committed to GitHub.

## X-UI

Open **Servers**, add the full panel base URL, username and password. This project calls only read endpoints for sync/monitoring.
