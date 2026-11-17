# LLNDN.G Drip Store

International e-commerce platform built with Flask + SQLite.

## Features

- Product catalogue with categories, search, sizes/colours, stock tracking, reviews & ratings
- Shopping cart (session-based), guest checkout, customer accounts
- Multi-currency price display (USD, EUR, GBP, ZAR — live rates)
- International shipping cost calculation by country
- Discount codes
- Real payments: **Stripe** (cards) and **PayPal**, webhook-verified
- Order confirmation emails (SMTP), order tracking page, order statuses
- Admin dashboard: products, inventory, orders, customers, discounts, revenue
- LLNDN.G branding preserved

## Setup

1. Install Python 3.10+ from python.org (tick "Add to PATH")
2. Open a terminal in this folder:

```
pip install -r requirements.txt
copy .env.example .env
```

3. Edit `.env` and add your real keys:
   - `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` — from https://dashboard.stripe.com/apikeys
   - `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` — from https://developer.paypal.com (`PAYPAL_MODE=live` for real payments, `sandbox` for testing)
   - `PAYNOW_INTEGRATION_ID`, `PAYNOW_INTEGRATION_KEY` — from your Paynow account (paynow.co.zw → Integrations). Supports EcoCash, OneMoney, InnBucks and cards.
   - Email settings (optional) for order confirmations
4. Run:

```
python app.py
```

5. Open http://localhost:5000

## Make yourself admin

After registering, run in the `store.db` database:

```
UPDATE users SET is_admin=1 WHERE email='you@example.com';
```

Then log in and visit `/admin`.

## Stripe webhook (production)

Point a Stripe webhook at `https://your-domain.com/webhook/stripe` listening for `checkout.session.completed`, and set `STRIPE_WEBHOOK_SECRET` to the signing secret it gives you.

## Notes

- All prices are stored in USD; Stripe/PayPal charge in USD. The currency selector converts display prices only.
- Without payment keys configured, checkout will show a "payments not configured" message — no fake payments are simulated.
