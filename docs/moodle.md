# Moodle On The Same Host

This project integrates with `Moodle` as a separate subsystem. The Django application remains the main product UI, while `Moodle` handles course authoring, delivery, quizzes, and completion tracking.

The first integration stage assumes that active `staff` users are provisioned from Django into Moodle automatically, so Django remains the source of truth for learning accounts.
The second stage uses Django as the OpenID Connect Provider, so users can enter Moodle under the same Django session without a separate Moodle password.

## Why This Setup

- `Moodle` runs on the same server, but isolated from the Django runtime.
- The stack is packaged in `Docker Compose`, which makes a future migration to another server much easier.
- The public URL is `learn.imcmontanai.ru`, reverse-proxied by the existing host `nginx`.
- Django only talks to `Moodle` over HTTPS and Web Services.

## Files In This Repo

- `deploy/moodle/docker-compose.yml`: portable `Moodle + PostgreSQL` stack for one-host deployment.
- `deploy/moodle/moodle.env.example`: environment file template for the compose stack.
- `deploy/moodle/nginx-learn.imcmontanai.ru.conf.example`: reverse proxy config for the existing `nginx`.
- `deploy/moodle/moodle-compose.service.example`: optional `systemd` unit to keep the compose stack up.
- `deploy/moodle/prod.env.moodle.example`: Django-side variables to place into `$HOME/ai_appdir/env/prod.env`.

## Why Docker Compose Helps Future Migration

- The application definition lives in one compose file instead of ad-hoc package installs.
- Runtime configuration is isolated in one env file.
- Persistent state is limited to a small set of directories:
  - `postgres/`
  - `moodledata/`
- The stack reuses `PostgreSQL`, which you already operate in the main app, instead of introducing `MariaDB`.
- Reverse proxy and Django integration are explicit and versioned in this repo.
- Migration to a new server becomes:
  1. copy `/opt/moodle`
  2. install Docker and `nginx`
  3. restore DNS/certificates
  4. run `docker compose up -d`

## Suggested Server Layout

```text
/opt/moodle/
  docker-compose.yml
  moodle.env
  postgres/
  moodledata/
```

Keep Django and Moodle separate:

```text
$HOME/ai_appdir/        # existing Django app
/opt/moodle/            # Moodle stack
```

## DNS And TLS

Before publishing the subdomain:

1. Create an `A` record for `learn.imcmontanai.ru` pointing to the current server IP.
2. Issue a certificate for `learn.imcmontanai.ru`.
3. Install the reverse proxy config from `deploy/moodle/nginx-learn.imcmontanai.ru.conf.example`.

## Install Steps On The Current Server

1. Install Docker Engine and Docker Compose plugin.
2. Create `/opt/moodle`.
3. Copy:
   - `deploy/moodle/docker-compose.yml` -> `/opt/moodle/docker-compose.yml`
   - `deploy/moodle/moodle.env.example` -> `/opt/moodle/moodle.env`
4. Replace all placeholder passwords in `/opt/moodle/moodle.env`.
5. Create data directories:

```bash
mkdir -p /opt/moodle/{postgres,moodledata}
```

6. Start the stack:

```bash
docker compose -f /opt/moodle/docker-compose.yml --env-file /opt/moodle/moodle.env up -d
```

7. Verify containers:

```bash
docker compose -f /opt/moodle/docker-compose.yml --env-file /opt/moodle/moodle.env ps
```

8. Apply the host `nginx` config for `learn.imcmontanai.ru`.
9. Reload `nginx`.
10. Open `https://learn.imcmontanai.ru` and confirm Moodle bootstrap completed.

## Optional systemd Integration

If you want the compose stack managed like a service:

1. Copy `deploy/moodle/moodle-compose.service.example` to `/etc/systemd/system/moodle-compose.service`.
2. Adjust the paths if needed.
3. Run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now moodle-compose
```

## Django Integration

After `Moodle` is reachable, add the values from `deploy/moodle/prod.env.moodle.example` into the existing Django production env file:

```dotenv
MOODLE_BASE_URL=https://learn.imcmontanai.ru
MOODLE_LAUNCH_PATH=/
MOODLE_SSO_LAUNCH_MODE=oidc
MOODLE_OIDC_LOGIN_PATH=/auth/oidc/
MOODLE_OIDC_LOGIN_SOURCE=django
MOODLE_OIDC_PROMPT_LOGIN=False
MOODLE_WEB_SERVICE_TOKEN=replace-me
MOODLE_WEB_SERVICE_TIMEOUT=20
OIDC_ISSUER_URL=https://imcmontanai.ru/o
OIDC_RSA_PRIVATE_KEY_FILE=/home/app/keys/oidc.key
MOODLE_OIDC_CLIENT_ID=replace-with-django-oidc-client-id
OIDC_STAFF_ONLY_CLIENT_IDS=replace-with-django-oidc-client-id
```

Then redeploy Django so the new env values are loaded and apply migrations:

```bash
source .venv/bin/activate
python manage.py migrate
```

## Django OIDC Provider

The Django app now exposes a minimal OIDC provider under `/o/` using `django-oauth-toolkit`.

Important behavior:

- discovery: `https://imcmontanai.ru/o/.well-known/openid-configuration`
- token signing: `RS256` using `OIDC_RSA_PRIVATE_KEY` or `OIDC_RSA_PRIVATE_KEY_FILE`
- supported flow: Authorization Code
- claims: `sub`, `name`, `given_name`, `family_name`, `preferred_username`, `email`, `email_verified`, `is_staff`
- `PKCE` is required only for `public` clients, so confidential Moodle auth-code clients work without extra tweaks
- if `MOODLE_OIDC_CLIENT_ID` is configured, that client is automatically restricted to Django `staff` users

## Launch Flow From Django

The `Обучение -> Открыть Moodle` button now starts the SSO flow from Django:

- default mode: Django redirects to `https://learn.imcmontanai.ru/auth/oidc/`
- the Moodle `auth_oidc` plugin then starts the authorization-code flow against Django
- after successful login, Moodle creates its own session and the user enters Moodle without a separate password

Relevant settings:

- `MOODLE_SSO_LAUNCH_MODE=oidc`: best default for passwordless launch from Django
- `MOODLE_OIDC_LOGIN_PATH=/auth/oidc/`: entrypoint of the Moodle `auth_oidc` plugin
- `MOODLE_OIDC_LOGIN_SOURCE=django`: optional source marker sent to Moodle
- `MOODLE_OIDC_PROMPT_LOGIN=False`: keep `False` for silent reuse of the current Django session

Alternative mode:

- `MOODLE_SSO_LAUNCH_MODE=page`

In `page` mode Django redirects straight to `MOODLE_LAUNCH_PATH`. Use this only if you later enable automatic redirect to OIDC on the Moodle side, because otherwise users may still land on the Moodle login page first.

Generate the RSA key once and keep it outside the repo:

```bash
openssl genrsa -out /home/app/keys/oidc.key 4096
chmod 600 /home/app/keys/oidc.key
```

Create the Django OIDC application in admin:

1. Open `/admin/oauth2_provider/application/add/`.
2. Set `client type = Confidential`.
3. Set `authorization grant type = Authorization code`.
4. Enable `skip authorization`.
5. Select signing algorithm `RS256`.
6. Add the redirect URI generated by the Moodle OIDC plugin.
7. Save the application and copy its `client_id` and `client_secret` into Moodle.

Use the same `client_id` in Django env for `MOODLE_OIDC_CLIENT_ID` so the provider can enforce the existing `staff-only` access rule for Moodle SSO.

## Initial Moodle Setup After First Start

In Moodle admin:

1. Confirm site URL is `https://learn.imcmontanai.ru`.
2. Enable Web Services.
3. Create a dedicated service account for API access.
4. Create an external service and add at least:
   - `core_user_get_users_by_field`
   - `core_user_create_users`
   - `core_user_update_users`
   - `core_enrol_get_users_courses`
   - `core_completion_get_course_completion_status`
   - `core_completion_get_activities_completion_status`
5. Generate a token for that service account.
6. Put the token into Django production env.

## First End-To-End Validation

1. Open `https://learn.imcmontanai.ru` and log in as Moodle admin.
2. Create one test course.
3. Enrol one existing `staff` user in that course.
4. Add the web service token to Django env.
5. Run:

```bash
source .venv/bin/activate
python manage.py sync_moodle_learning --email staff-user@example.com
```

6. Open the `Обучение` tab in Django and confirm the course appears.

## Backup And Migration Checklist

To move the Moodle subsystem to a new server, preserve:

- `/opt/moodle/docker-compose.yml`
- `/opt/moodle/moodle.env`
- `/opt/moodle/postgres/`
- `/opt/moodle/moodledata/`
- the `nginx` virtual host for `learn.imcmontanai.ru`
- the TLS certificate material

Recommended migration flow:

1. Lower DNS TTL before the move.
2. Stop writes to Moodle during the final cutover window.
3. Create a final backup of `/opt/moodle`.
4. Restore `/opt/moodle` on the new server.
5. Install Docker and `nginx`.
6. Reapply the reverse proxy config and certificate.
7. Start the compose stack.
8. Switch DNS.
9. Validate Moodle login and Django sync command.

## Notes

- This repo does not auto-deploy `Moodle`; it provides the versioned server-side templates and integration settings.
- `PostgreSQL` is inside the compose stack to avoid introducing a second database engine on the server.
- The selected Moodle image is `esdrascaleb/moodle-docker-php-production:alpine-php8.3`, because the previously used `bitnami/moodle` image is no longer published and Moodle 4.5 should not be started on PHP 8.4.
- If you later want higher operational maturity, you can move the database to managed storage without changing the Django integration contract.
