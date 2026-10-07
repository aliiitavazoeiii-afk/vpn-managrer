# Ayria APG integration

The `sms-app` branch integrates the documented Ayria APG `POST /apg/v1/create` flow into the Hesab debt desk.

## Debt desk flow

1. Operator can send the initial reminder SMS from the debt group.
2. Operator clicks **ارسال لینک پرداخت**.
3. Hesab recalculates the group's live debt on the server.
4. Hesab converts Toman to Rial (`amount_toman * 10`) because Ayria APG expects Rial.
5. Hesab creates the payment in Ayria using:
   - `APG-API-KEY` header
   - `APG-WALLET-ID` header
   - `referralCode`
   - payer mobile/name
6. The returned `paymentUrl` and `referenceCode` are stored locally.
7. The returned payment URL is queued through the existing Android personal-SIM SMS gateway.
8. The group is moved to **در انتظار** only after Ayria creation succeeds and the SMS job is queued.

The public Ayria APG documentation exposes payment creation and returns `paymentUrl`; it does not document a separate "send payment URL by Ayria SMS" endpoint. Therefore Hesab sends the returned URL through the already-working personal-SIM gateway.

## Environment

Set these only on the production server `.env`:

```env
AYRIA_API_BASE=https://api.ayriaclub.ir
AYRIA_APG_API_KEY=...
AYRIA_APG_WALLET_ID=...
AYRIA_REFERRAL_CODE=...
```

Never commit the APG API key.

## Current boundary

This version creates/registers payment requests and sends payment links. It does **not** automatically mark invoices paid from Ayria callbacks yet.

For automatic reconciliation, register a default callback URL with Ayria support first, then add a verified callback workflow that matches `referenceCode` and amount before changing Hesab accounting state.
