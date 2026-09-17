# DeepSeek Harness And Ollama On The Same Host

This is the portable AI sidecar for the Django app: an admin DeepSeek Harness
console and a local OpenAI-compatible model server. It follows the same
isolation pattern as Nextcloud, Moodle, and Mailu — separate Compose stacks,
loopback ports, host `nginx`, data under `/opt/...` so a move to another
server is a copy.

Django CI/CD is not used. The app deploy restarts gunicorn; these stacks have
their own images, volumes, and session state.

## Why Two Stacks

- `deploy/ollama`: model weights and the `/v1` API. Swap later for
  `llama-server` by pointing DSH at another OpenAI-compatible URL.
- `deploy/dsh`: Web UI, sessions, skills, provider settings.

On the current production VM, deploy **DSH only**. Point it at the official
model API from the Web UI (DeepSeek card in Settings → Models). Do not install
Ollama there.

`deploy/ollama` stays for a later GPU host. Then DSH can keep using the
official API, or you attach it to Ollama with `docker-compose.ollama.yml`.

Nothing is published on `0.0.0.0`. Host `nginx` terminates HTTPS for the admin UI.

## Suggested Server Layout

```text
/opt/ollama/
  docker-compose.yml
  docker-compose.gpu.yml
  ollama.env
  ollama-healthcheck.sh
  pull-model.sh
  models/                 # Ollama blobs — the large directory to copy

/opt/dsh/
  docker-compose.yml
  Dockerfile
  docker-entrypoint.sh
  container-healthcheck.sh
  dsh.env
  dsh-healthcheck.sh
  settings.yaml.example
  home/                   # sessions, credentials, live settings.yaml
  workspace/              # agent working directory for local tests
  skills/                 # SKILL.md trees; git is the source of truth
```

Moving servers:

1. Stop both compose stacks.
2. Copy `/opt/ollama` and `/opt/dsh` (rsync/`-a`).
3. Recreate `docker network create imc-ai`.
4. Restore host `nginx` site and TLS files.
5. Enable the two systemd units.
6. Confirm `127.0.0.1:11434/api/tags` and `127.0.0.1:3080/`.

The Django repo checkout is not required on the new host except as a place to
copy these `deploy/` files the first time.

## Hardware

The current production VM does not run a local model. DSH only needs RAM for
Node and outbound HTTPS to the official API.

Qwen3.5-9B Q4 wants roughly 16 GB VRAM. That belongs on a later GPU host, or
on a laptop with native Ollama.

## Current Production: DSH Plus Official API

Skip `deploy/ollama` and `docker network create imc-ai`. The DSH container uses
the default Docker network so it can reach `api.deepseek.com` (or another
provider).

```bash
REPO=~/ai_appdir/ai_app
sudo mkdir -p /opt/dsh/home /opt/dsh/workspace /opt/dsh/skills /opt/dsh/branding
sudo chown -R 1000:1000 /opt/dsh/home /opt/dsh/workspace /opt/dsh/skills
sudo bash "$REPO"/deploy/dsh/sync-sidecar.sh "$REPO" /opt/dsh
sudo cp "$REPO"/deploy/dsh/dsh.env.example /opt/dsh/dsh.env
sudo chmod +x /opt/dsh/*.sh /opt/dsh/docker-entrypoint.sh
```

In `/opt/dsh/dsh.env` set `OPENROUTER_API_KEY` from https://openrouter.ai/keys.
Leave `DSH_LLM_BASE_URL` empty. Set `DSH_TRUSTED_HOSTS` to the public hostname
if nginx will sit in front; leave it empty for an SSH tunnel to
`127.0.0.1:3080`.

```bash
cd /opt/dsh
sudo docker compose --env-file dsh.env build
sudo docker compose --env-file dsh.env up -d
sudo ./dsh-healthcheck.sh
```

Open the UI (tunnel or `https://dsh.example.com`). On first start the
container seeds OpenRouter as `qwen/qwen3.5-27b` when `OPENROUTER_API_KEY` is
set. You can still paste or rotate the key in Settings → Models. DashScope
and the official DeepSeek card can stay as extra routes. No local weights
are required.

The container must be allowed outbound HTTPS. If a host firewall or proxy
blocks it, the UI will start and model calls will fail.

## Later: Ollama On Another Host

Create `imc-ai` only when Ollama runs on the same Docker host:

```sh
docker network create imc-ai
```

Then start `deploy/ollama` and DSH with
`-f docker-compose.yml -f docker-compose.ollama.yml`, and set
`DSH_LLM_BASE_URL=http://ollama:11434/v1`.

## Ollama On A Later GPU Server

```sh
sudo mkdir -p /opt/ollama/models
sudo cp deploy/ollama/docker-compose.yml \
       deploy/ollama/docker-compose.gpu.yml \
       deploy/ollama/ollama-healthcheck.sh \
       deploy/ollama/pull-model.sh \
       /opt/ollama/
sudo cp deploy/ollama/ollama.env.example /opt/ollama/ollama.env
sudo chmod +x /opt/ollama/ollama-healthcheck.sh /opt/ollama/pull-model.sh
```

CPU-only (smoke):

```sh
cd /opt/ollama
docker compose --env-file ollama.env up -d
./ollama-healthcheck.sh
```

GPU (NVIDIA Container Toolkit already installed):

```sh
cd /opt/ollama
docker compose --env-file ollama.env -f docker-compose.yml -f docker-compose.gpu.yml up -d
./pull-model.sh
```

Keep the API on loopback: `127.0.0.1:11434`. Host tools can call it; the
internet cannot.

Optional systemd: copy `ollama-compose.service.example` to
`/etc/systemd/system/ollama-compose.service`. For GPU, change `ExecStart` to
the two-file compose command above.

## DeepSeek Harness Bind Address

`dsh web` refuses `--host 0.0.0.0`. The image binds DSH to `127.0.0.1:3080`
inside the container and forwards container port `13080` with `socat`. Compose
publishes `127.0.0.1:3080`. Install and first-start steps are under Current
Production above. Optional systemd: `dsh-compose.service.example`.

A local OpenAI-compatible URL is seeded into `home/settings.yaml` only when
`DSH_LLM_BASE_URL` is set and `OPENROUTER_API_KEY` is empty. With OpenRouter,
configure `OPENROUTER_API_KEY` in `dsh.env`.

## Host Nginx

Install `nginx-dsh.example.conf` as a dedicated HTTPS site. Web UI needs a
secure context (`crypto.randomUUID`). Keep `auth_basic` until SSO exists.
Set `DSH_TRUSTED_HOSTS` to the same hostname or `/api` returns 403.

Do not publish Compose ports on a public interface.

## Local Laptop

Native honcho (`./scripts/dev_up.sh`) is the usual laptop path, not Docker.
`scripts/dev_dsh.sh` applies `deploy/dsh/branding` on every start: sidebar and
browser title become **IMC Montan AI**, with the same globe mark as the Django
favicon / collapsed header icon. To change it later, edit
`deploy/dsh/branding/brand.yaml` and/or `core/static/core/icons/favicon.svg`.

1. Get a key at https://openrouter.ai/keys
2. Put it in `deploy/dsh/dsh.env` as `OPENROUTER_API_KEY=...` (gitignored)
3. In the DSH UI, Settings → Models: provider `openrouter`, model `qwen/qwen3.5-27b`
4. Existing DashScope / Token Plan routes stay in `settings.yaml`; they are not deleted

If DSH is already running, paste the same key into the OpenRouter card in
Settings → Models — that writes `$DSH_HOME/.credentials.yaml` without a restart.
A later honcho restart picks the key up from `dsh.env`.

Docker on the laptop is optional: copy `dsh.env.example` to `dsh.env`, set
`OPENROUTER_API_KEY`, then `cd deploy/dsh && docker compose --env-file dsh.env up -d --build`.

## llama-server Instead Of Ollama

Keep the DSH stack. Replace `deploy/ollama` with any OpenAI-compatible
`llama-server` (`/v1/chat/completions`), join `imc-ai` as hostname `ollama` or
change `DSH_LLM_BASE_URL`, and set `compat.maxTokensField: max_tokens` as in
`settings.yaml.example`.

## Django

DSH is not started by gunicorn. The staff menu only needs `DSH_BASE_URL`.
Checklist sort additionally runs **headless DSH once per section**. That
subprocess must use the **same runtime as the Web UI**, not `npx` and not
whatever Node happens to be on the Django PATH.

### Production

Gunicorn and the DSH container share `/opt/dsh/workspace`:

| Django (host) | DSH (container) |
|---|---|
| `/opt/dsh/workspace/sort-runs/<id>` | `/workspace/sort-runs/<id>` |

Copy the Django variables from `deploy/dsh/prod.env.dsh.example` into the
gunicorn env. `settings/prod.py` fills the same defaults when
`/opt/dsh/docker-compose.yml` exists.

```bash
sudo mkdir -p /opt/dsh/workspace/sort-runs
# gunicorn must write here; the container user is uid/gid 1000 (`node`).
sudo chown -R 1000:www-data /opt/dsh/workspace/sort-runs
sudo chmod 2775 /opt/dsh/workspace/sort-runs
```

Do **not** set `DSH_HEADLESS_CMD=npx ...`, `DSH_NODE_BIN`, or a host
`DSH_HOME` for gunicorn. The container already has Node 24, global `dsh`,
and `DSH_HOME=/home/node/.dsh`. Local inbox paths stay off
(`DSH_SORT_ALLOW_LOCAL_INBOX=0`).

Django deploy does **not** start DSH on every gunicorn restart. It only
rsyncs `deploy/dsh` sidecar files (including `branding/`) into `/opt/dsh`
and rebuilds the container when that checksum changes. Sessions, `dsh.env`,
and `$DSH_HOME` stay untouched on ordinary app deploys.

To change the Web UI name or mark: edit `deploy/dsh/branding/brand.yaml`
and/or `core/static/core/icons/favicon.svg` (the header/favicon globe),
merge to `main`, and let CI/CD copy it. Do not patch DSH `node_modules`
and do not `dsh plugin` by hand on the server.

### Local laptop

`settings/local.py` plus `./scripts/dev_dsh.sh` (honcho): nvm Node 22,
isolated npm prefix `deploy/dsh/data/npm`, `DSH_HOME` under
`deploy/dsh/data/home`. Headless uses that binary, not `npx`. The local
inbox field is on for testing only.
