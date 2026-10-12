# Cloudflare migration

Target resources:

- Worker: `federation-bot`
- D1: `federation-bot-db`

Do not move the Telegram webhook until the applications/payments schema, receipt
storage and admin review callbacks are working on Cloudflare.
