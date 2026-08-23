# VPN Control Center

Personal agentless VPN customer/accounting and 3x-ui monitoring dashboard.

- Customer accounts, Persian/Jalali due dates, payment state and payment history
- Debtors/receivables view
- Multi-server 3x-ui read-only sync
- Online clients, Xray state, CPU/RAM/disk/network stats
- Local traffic history on the management server
- Excel import from Settings
- No agent or extra service is installed on production VPN servers
- Ayria payment automation is intentionally deferred

## One-line install

Run only on the separate management VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/main/install.sh | sudo bash
```

The installer downloads the actual source tree directly from GitHub, builds it with Docker Compose, validates `/health` and `/login`, and prints a fresh admin password.

## Customer data

This repository is public, so real customer names/phone numbers are **not** committed. After login use **Settings -> Excel Import** and upload `vpn-sait.xlsx` from your computer.

## X-UI

Open **Servers**, add the full panel base URL, username and password. The application uses the existing 3x-ui API in read-only mode and installs nothing on VPN servers.
