# Mailu On The Same Host

This project sends email through Django SMTP settings in `settings/base.py`. The app code does not depend on any vendor API, so switching to `Mailu` is mostly an infrastructure change.

## What This Setup Assumes

- The Django app stays on the current host.
- `Mailu` runs on the same host in Docker Compose.
- Existing public `80/443` remain owned by the current reverse proxy and application stack.
- Mail protocols (`25`, `465`, `587`, `143`, `993`, `4190`) are exposed directly by `Mailu`.
- The `Mailu` web UI is published through the existing reverse proxy on `mail.imcmontanai.ru`.

## Files In This Repo

- `deploy/mailu/docker-compose.yml`: `Mailu` stack template for a same-host install.
- `deploy/mailu/mailu.env.example`: example `Mailu` environment file.
- `deploy/mailu/nginx-mail.imcmontanai.ru.conf.example`: reverse proxy example for the `Mailu` web UI.
- `deploy/mailu/mailu.service.example`: optional `systemd` unit for `Mailu`.
- `deploy/mailu/prod.env.mailu.example`: Django mail variables for `$HOME/ai_appdir/env/prod.env`.

## DNS And Certificates

Before switching traffic, prepare:

1. `A` record for `mail.imcmontanai.ru` pointing to the same server.
2. `MX` record for `imcmontanai.ru` pointing to `mail.imcmontanai.ru`.
3. `SPF` record authorizing the server IP.
4. `DMARC` record for the main domain.
5. `DKIM` record after `Mailu` generates the selector key.
6. A certificate for `mail.imcmontanai.ru` copied into `Mailu` as `cert.pem` and `key.pem`.

Because the host already uses external `80/443`, this setup uses `TLS_FLAVOR=cert` instead of the built-in Let's Encrypt flow in `Mailu`.

## Server Layout

Suggested directories on the server:

```text
/opt/mailu/
  docker-compose.yml
  mailu.env
  certs/
  data/
  dkim/
  mail/
  mailqueue/
  filter/
  redis/
  webmail/
  overrides/
```

## Install Steps

1. Install Docker Engine and Compose plugin on the server.
2. Create `/opt/mailu` and copy `deploy/mailu/docker-compose.yml` there.
3. Copy `deploy/mailu/mailu.env.example` to `/opt/mailu/mailu.env` and replace placeholders.
4. Copy the certificate pair to `/opt/mailu/certs/cert.pem` and `/opt/mailu/certs/key.pem`.
5. Set `REAL_IP_FROM` in `mailu.env` to the CIDR that Mailu sees for your reverse proxy traffic.
6. Apply the reverse proxy config from `deploy/mailu/nginx-mail.imcmontanai.ru.conf.example` in the existing web server.
7. Start `Mailu` with:

```bash
docker compose -f /opt/mailu/docker-compose.yml --env-file /opt/mailu/mailu.env up -d
```

8. Verify containers:

```bash
docker compose -f /opt/mailu/docker-compose.yml --env-file /opt/mailu/mailu.env ps
```

9. Log in to the admin UI on `https://mail.imcmontanai.ru/admin`.
10. Create:
   - the primary domain `imcmontanai.ru`
   - a mailbox such as `notifications@imcmontanai.ru`
   - an alias for `postmaster@imcmontanai.ru`
   - any forwarding rules needed for personal inboxes

## Django Switch

The project now supports both explicit `EMAIL_*` variables and a single `EMAIL_URL`.

Recommended production values for the Django host:

```dotenv
EMAIL_URL=smtp+tls://notifications%40imcmontanai.ru:change-me@127.0.0.1:587
DEFAULT_FROM_EMAIL=notifications@imcmontanai.ru
EMAIL_TIMEOUT=10
```

If you prefer explicit variables instead of `EMAIL_URL`, use:

```dotenv
EMAIL_HOST=127.0.0.1
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=notifications@imcmontanai.ru
EMAIL_HOST_PASSWORD=change-me
DEFAULT_FROM_EMAIL=notifications@imcmontanai.ru
EMAIL_TIMEOUT=10
```

After updating `$HOME/ai_appdir/env/prod.env`, redeploy the app so `systemd` reloads the environment and Django reconnects to `Mailu`.

## Post-Switch Checks

- Confirm `EHLO`, `STARTTLS`, and authenticated SMTP submission on `127.0.0.1:587`.
- Send a test message from Django registration flow.
- Confirm the message is accepted by `Mailu` and reaches an external mailbox.
- Check DKIM signing on the received message headers.
- Verify forwarding rules and aliases.
- Check spam placement in Gmail/Yandex/Outlook test inboxes.

## Notes

- This repo does not auto-deploy `Mailu`; it only provides server-side templates and Django config support.
- If you later move the mail stack to another host, only the `EMAIL_URL` or `EMAIL_*` values need to change.
