# Telegram service (free hosting)

Real MTProto QR login and channel history extraction. The service code is
mirrored at https://github.com/Technoyemenspace/telescraper-telegram.

## Hosting paths

- **Render Free** requires a payment card on the account even for the free plan
  (security verification). If a card is added, create the service from the
  repository root `render.yaml` (free plan, no paid disk).
- **Hugging Face Spaces (chosen cardless path)**: create a free Hugging Face
  account, generate an access token with write scope, and the Space is deployed
  from `Dockerfile` (see below). No card is ever required.

## Hugging Face deployment

1. Create a Space (Docker SDK, public visibility is fine: every path except
   `/health` requires `X-Service-Key`).
2. The Space repository needs: `Dockerfile`, `main.py`, `rules.py`,
   `requirements.txt`, and a `README.md` with:

```yaml
---
title: TeleScraper Telegram Service
app_port: 7860
---
```

3. Add the Space secrets `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
   `TELEGRAM_SERVICE_KEY` (Space settings → Variables and secrets).
4. Free Spaces sleep after about 48 hours of inactivity; storage is ephemeral,
   so the user scans a new QR after a restart. This is not uninterrupted
   production hosting.

## Previous Render deployment steps

1. Put this project in a connected Git repository (Lovable Settings → GitHub).
2. In Render, create a Blueprint from that repository using root `render.yaml`.
3. Use the Free instance plan. Do not add a paid disk or upgrade the plan.
4. Configure `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from my.telegram.org securely
   in Render. Never commit those values.
5. Set a strong shared `TELEGRAM_SERVICE_KEY` using Lovable's secure shared-secret
   form and copy the same value into Render's environment settings.
6. Store the resulting HTTPS service URL in Lovable for the later server integration.

Render automation uses an API key from Account Settings → API Keys, not a login
password. A Render API key alone does not supply a Git repository.

## Free hosting limitations

Render Free spins down after 15 minutes without inbound traffic, and waking up
can take about a minute. Session files disappear on restart, redeplay, or spin-down;
the user must scan a new QR after that. No paid disk is configured. Render also
limits free instance hours and bandwidth; do not upgrade or incur charges on the
user's behalf. This is not uninterrupted production hosting.
See https://render.com/docs/free for current limits.

## Security boundary

This service is for one Telegram account, one process, and one replica. All paths
except `/health` require `X-Service-Key`. Keep that key server-side; never add it
to frontend code. The future dashboard proxy MUST authenticate its own account
owner before forwarding any Telegram call. Do not expose a public proxy: it would
allow visitors to control the owner's Telegram account. No CORS is enabled.

Telegram QR URLs, session files and verification passwords must never be logged.
The session directory is private and temporary on the Free plan; any backup access
must be restricted as the session grants account access. Logout revokes the
Telegram authorization. Only read channels the account is permitted to access.

## API

- `GET /health`: public readiness check, no account information.
- `POST /session/qr`: real QR URL and expiry from Telegram, or active status.
- `GET /session`: waiting / active / expired / password_required / failed / idle.
- `POST /session/password`: Telegram two-step verification password, only after challenge.
- `DELETE /session`: revoke Telegram session.
- `POST /scan`: `channel`, `depth` (100/500/3000), `keywords`, `seen` URLs.
  Returns extracted leads, duplicates and message count. Embedded text-link URLs
  are included. HTTP 429 returns Telegram's required wait in `detail.seconds`;
  the future caller must honor it before retrying. Scans are serialized and spaced
  by three seconds, with a 60-second history-fetch timeout.

## Local verification

Use an isolated Python environment, install `requirements.txt`, then run
`python -m unittest discover -s services/telegram -p 'test_*.py'` from the project
root. Real Telegram end-to-end verification requires deployment credentials and
the account owner's QR approval; unit tests do not establish live login success.