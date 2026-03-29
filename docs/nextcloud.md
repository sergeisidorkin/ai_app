# Nextcloud On The Same Host

This project can use `Nextcloud` as a temporary self-hosted file service during
development, while keeping the deployment simple enough to move to a dedicated
server later.

## Why This Setup

- `Nextcloud` runs on the current VM, but isolated from the Django app, `Moodle`,
  and `Mailu`.
- The stack is packaged in `Docker Compose`, which keeps migration to another
  server straightforward.
- The public URL is a dedicated subdomain such as `cloud.example.com`,
  reverse-proxied by the existing host `nginx`.
- The deployment avoids `OnlyOffice` and `Collabora`, so CPU and memory stay
  predictable on the current `4 vCPU / 8 GB RAM` VM.

## Storage Decision For The Current VM

The current VM has a `20G` root disk and about `7.2G` free space. That is
enough only for a smoke-test deployment with small test files.

For the simplest future migration path, keep the whole stack under
`/opt/nextcloud` and prefer one of these options:

1. Best option for this temporary setup: enlarge the root disk to at least
   `40G`, so `/opt/nextcloud` stays self-contained.
2. If root resize is not possible immediately: keep the test stack on the
   current root disk, but do not store real data there and do not import large
   fixtures.

This repo assumes the portable layout below, so moving to another server later
is mostly a copy operation.

## Files In This Repo

- `deploy/nextcloud/docker-compose.yml`: portable `Nextcloud + PostgreSQL + Redis` stack.
- `deploy/nextcloud/nextcloud.env.example`: environment file template.
- `deploy/nextcloud/nginx-cloud.example.com.conf.example`: reverse proxy example for the host `nginx`.
- `deploy/nextcloud/nextcloud-compose.service.example`: optional `systemd` unit to keep the compose stack up after reboot.
- `deploy/nextcloud/update_cloud_cert.sh.example`: example certificate refresh script for a dedicated `cloud` certificate from Yandex Certificate Manager.
- `deploy/nextcloud/prod.env.nextcloud.example`: Django-side `NEXTCLOUD_*` variables for `$HOME/ai_appdir/env/prod.env`.

## Why Docker Compose Helps Future Migration

- Runtime configuration lives in one env file.
- Persistent state is limited to a small set of directories:
  - `html/`
  - `data/`
  - `postgres/`
  - `redis/`
- The public endpoint stays on the host `nginx`, so moving to another server
  only requires copying the stack and restoring the same proxy pattern.

## Suggested Server Layout

```text
/opt/nextcloud/
  docker-compose.yml
  nextcloud.env
  html/
  data/
  postgres/
  redis/
```

## Install Steps On The Current Server

1. Ensure Docker Engine and the Compose plugin are already installed on the VM.
2. Create `/opt/nextcloud`.
3. Copy:
   - `deploy/nextcloud/docker-compose.yml` -> `/opt/nextcloud/docker-compose.yml`
   - `deploy/nextcloud/nextcloud.env.example` -> `/opt/nextcloud/nextcloud.env`
4. Replace placeholder passwords and set the real subdomain in `/opt/nextcloud/nextcloud.env`.
5. Create data directories:

```bash
mkdir -p /opt/nextcloud/{html,data,postgres,redis}
```

6. Start the stack:

```bash
docker compose -f /opt/nextcloud/docker-compose.yml --env-file /opt/nextcloud/nextcloud.env up -d
```

7. Verify containers:

```bash
docker compose -f /opt/nextcloud/docker-compose.yml --env-file /opt/nextcloud/nextcloud.env ps
```

8. Install the host `nginx` config from `deploy/nextcloud/nginx-cloud.example.com.conf.example`.
9. Reload `nginx`.
10. Open `https://cloud.example.com` and finish the first login if the bootstrap screen still appears.

## Certificate Refresh Pattern

The current production host already rotates certificates through root cron jobs.
`cloud` should follow the same pattern with its own certificate and its own
target directory:

```text
/etc/nginx/ssl-cloud/fullchain.pem
/etc/nginx/ssl-cloud/privkey.pem
```

Recommended server-side installation:

1. Copy `deploy/nextcloud/update_cloud_cert.sh.example` to `/usr/local/sbin/update_cloud_cert.sh`.
2. Replace `CERT_ID` with the managed certificate ID from Yandex Certificate Manager.
3. Create the target directory:

```bash
sudo mkdir -p /etc/nginx/ssl-cloud
sudo chmod 750 /etc/nginx/ssl-cloud
```

4. Make the script executable:

```bash
sudo chmod 755 /usr/local/sbin/update_cloud_cert.sh
```

5. Add the new root crontab entry next to the existing jobs:

```cron
10 4 * * * /usr/local/sbin/update_cert.sh >> /var/log/update_cert.log 2>&1
20 4 * * * /usr/local/sbin/update_mail_cert.sh >> /var/log/update_mail_cert.log 2>&1
30 4 * * * /usr/local/sbin/update_learn_cert.sh >> /var/log/update_learn_cert.log 2>&1
40 4 * * * /usr/local/sbin/update_cloud_cert.sh >> /var/log/update_cloud_cert.log 2>&1
```

6. Run the script once manually before enabling the nginx vhost:

```bash
sudo /usr/local/sbin/update_cloud_cert.sh
```

## Optional systemd Integration

If you want the compose stack managed like a service:

1. Copy `deploy/nextcloud/nextcloud-compose.service.example` to `/etc/systemd/system/nextcloud-compose.service`.
2. Run:

```bash
sudo chmod 644 /etc/systemd/system/nextcloud-compose.service
sudo systemctl daemon-reload
sudo systemctl enable --now nextcloud-compose
```

Useful operational commands:

```bash
sudo systemctl restart nextcloud-compose
sudo systemctl status nextcloud-compose
sudo journalctl -u nextcloud-compose -n 100 --no-pager
docker compose -f /opt/nextcloud/docker-compose.yml --env-file /opt/nextcloud/nextcloud.env logs --tail=100
```

## Reverse Proxy Notes

The host `nginx` remains the only public listener on `80/443`. The compose stack
publishes `Nextcloud` only on `127.0.0.1:8091`, matching the same-host pattern
already used by the other services on this VM.

Important proxy behavior:

- `client_max_body_size 2g` allows practical file upload testing.
- `/.well-known/carddav` and `/.well-known/caldav` redirect to DAV endpoints.
- `proxy_request_buffering off` avoids unnecessary buffering during uploads.

## Validation

After deployment, verify:

- the login page opens on the chosen subdomain;
- admin login succeeds;
- file upload and download both work;
- `remote.php/dav/files/<user>/` is reachable with an app password or basic auth;
- background jobs are handled by the `cron` container instead of AJAX mode.

## Migration To A Dedicated Server

The intended move later should look like this:

1. Prepare the new server with Docker, Compose, and `nginx`.
2. Copy `/opt/nextcloud`.
3. Install the nginx config for the same `cloud.<domain>` hostname.
4. Move DNS to the new server IP.
5. Run `docker compose up -d`.
6. Verify login, upload, and WebDAV again.

Because the stack uses bind mounts under `/opt/nextcloud`, no Docker named
volume export is required during the move.

## SSO And Provisioning Rollout

The Django application already exposes an OIDC provider under `/o/`. `Nextcloud`
SSO should reuse it instead of introducing a second identity source.

Recommended production-side `NEXTCLOUD_*` variables for Django:

```dotenv
NEXTCLOUD_BASE_URL=https://cloud.imcmontanai.ru
NEXTCLOUD_SSO_ENABLED=True
NEXTCLOUD_OIDC_LOGIN_PATH=/apps/user_oidc/login/1
NEXTCLOUD_PROVISIONING_BASE_URL=https://cloud.imcmontanai.ru
NEXTCLOUD_PROVISIONING_USERNAME=admin
NEXTCLOUD_PROVISIONING_TOKEN=replace-with-nextcloud-app-password
NEXTCLOUD_OIDC_PROVIDER_ID=1
NEXTCLOUD_OIDC_CLIENT_ID=replace-with-django-oidc-client-id
NEXTCLOUD_DEFAULT_GROUP=staff
NEXTCLOUD_DEFAULT_QUOTA=
```

`ai_app` should remain the source of truth:

- the left menu opens `Nextcloud` in a new tab;
- when `NEXTCLOUD_SSO_ENABLED=True`, the menu should target the direct `user_oidc`
  login route (`/apps/user_oidc/login/<providerId>`) instead of the plain root URL,
  because that guarantees immediate OIDC hand-off;
- the Django OIDC provider authenticates users;
- the Django integration pre-provisions and updates `active staff` users;
- users who lose staff access are disabled in `Nextcloud`.

Stable user mapping for `Nextcloud` should use the dedicated OIDC claim
`nextcloud_uid`, which is generated from the Django user id as `ncstaff-<pk>`.
This keeps the `Nextcloud` user identifier stable even if username or email
changes later.

Recommended `Nextcloud` `user_oidc` provider shape:

- discovery URL: `https://imcmontanai.ru/o/.well-known/openid-configuration`
- user id mapping: `nextcloud_uid`
- display name mapping: `name`
- email mapping: `email`
- Django OAuth application algorithm: `RS256`
- enable auto redirect when this is the only external login backend
- keep `Nextcloud` users staff-only by registering the `Nextcloud` client id in
  Django `OIDC_STAFF_ONLY_CLIENT_IDS`

For proactive provisioning, the integration should use the `user_oidc`
pre-provisioning API, not generic user creation, so the same OIDC backend owns
both the login and the user lifecycle. Nextcloud documents OIDC login via the
`user_oidc` app and its optional provisioning behavior in the admin manual and
README. The general OCS user provisioning API also supports user enable/disable
operations for lifecycle changes. [Nextcloud OIDC docs](https://docs.nextcloud.com/server/latest/admin_manual/configuration_user/user_auth_oidc.html) [user_oidc README](https://raw.githubusercontent.com/nextcloud/user_oidc/main/README.md) [Nextcloud provisioning API docs](https://docs.nextcloud.com/server/latest/admin_manual/configuration_user/user_provisioning_api.html)
