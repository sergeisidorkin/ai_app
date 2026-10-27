ARG NODE_IMAGE=node:24-bookworm-slim
FROM ${NODE_IMAGE}

# Pin the official npm package. Bump this and rebuild when upgrading DSH.
ARG DSH_VERSION=0.1.5-rc.1
ARG PNPM_VERSION=11.7.0

ENV DSH_VERSION=${DSH_VERSION} \
    DSH_HOME=/home/node/.dsh \
    DSH_WEB_PORT=3080 \
    DSH_BRIDGE_PORT=13080 \
    PNPM_HOME=/home/node/.dsh/pnpm \
    NPM_CONFIG_CACHE=/home/node/.dsh/cache/npm \
    XDG_CACHE_HOME=/home/node/.dsh/cache \
    XDG_CONFIG_HOME=/home/node/.dsh/config \
    PATH=/usr/local/bin:${PATH}

RUN set -eux; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        procps \
        python3 \
        socat \
        tini; \
    npm install --global --no-audit --no-fund \
        --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs \
        "pnpm@${PNPM_VERSION}" \
        "@deepseek-ai/dsh@${DSH_VERSION}"; \
    npm cache clean --force; \
    rm -rf /var/lib/apt/lists/*

ARG DSH_UID=1000
ARG DSH_GID=1000

RUN set -eux; \
    if [ "$(id -g node)" != "${DSH_GID}" ]; then \
      existing_group="$(getent group "${DSH_GID}" | cut -d: -f1 || true)"; \
      if [ -z "${existing_group}" ]; then groupmod --gid "${DSH_GID}" node; fi; \
      usermod --gid "${DSH_GID}" node; \
    fi; \
    if [ "$(id -u node)" != "${DSH_UID}" ]; then \
      usermod --uid "${DSH_UID}" node; \
    fi; \
    mkdir -p /home/node/.dsh /workspace /usr/local/share/dsh; \
    chown -R "${DSH_UID}:${DSH_GID}" /home/node /workspace

COPY docker-entrypoint.sh /usr/local/bin/dsh-entrypoint
COPY container-healthcheck.sh /usr/local/bin/dsh-container-healthcheck
COPY apply-brand.sh /usr/local/bin/dsh-apply-brand
COPY settings.yaml.example /usr/local/share/dsh/settings.yaml.example
COPY settings.ollama.yaml.example /usr/local/share/dsh/settings.ollama.yaml.example
COPY branding /usr/local/share/dsh/branding
COPY plugins/imc-brand /usr/local/share/dsh/plugins/imc-brand
RUN chmod 0755 \
        /usr/local/bin/dsh-entrypoint \
        /usr/local/bin/dsh-container-healthcheck \
        /usr/local/bin/dsh-apply-brand \
    && chmod -R a+rX /usr/local/share/dsh

# npm installs several copies of the Win32 helper. Importing two of them on
# Linux registers the koffi type DSH_STARTUPINFOW twice and the web UI exits.
# Keep the shallowest copy and point the other copies at it.
RUN python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

modules = Path("/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules")
name = "dsh-win32-process"
found = []
for dirpath, dirnames, filenames in os.walk(modules, followlinks=False):
    path = Path(dirpath)
    dirnames[:] = [entry for entry in dirnames if not (path / entry).is_symlink()]
    if path.name == name and path.parent.name == "@deepseek-ai" and "package.json" in filenames:
        found.append(path)

found.sort(key=lambda path: len(path.parts))
if not found:
    raise SystemExit(f"{name} was not installed")
canonical = found[0]
canonical_version = json.loads((canonical / "package.json").read_text()).get("version")
linked = 0
for path in found[1:]:
    if path.is_symlink():
        continue
    version = json.loads((path / "package.json").read_text()).get("version")
    if version != canonical_version:
        continue
    relative = Path(os.path.relpath(canonical, path.parent))
    subprocess.check_call(["rm", "-rf", str(path)])
    path.symlink_to(relative)
    linked += 1
print(f"deduped {linked} copies of {name} {canonical_version}")
PY

USER ${DSH_UID}:${DSH_GID}
WORKDIR /workspace

EXPOSE 13080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD ["dsh-container-healthcheck"]

ENTRYPOINT ["tini", "--", "dsh-entrypoint"]
CMD ["web"]
