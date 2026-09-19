import os
import shlex
import subprocess
import time
from pathlib import Path

from django.conf import settings


class DshRunError(RuntimeError):
    pass


def _configured_command():
    configured = getattr(settings, "DSH_HEADLESS_CMD", "") or ""
    if isinstance(configured, (list, tuple)):
        return [str(part) for part in configured if str(part).strip()]
    text = str(configured).strip()
    return shlex.split(text) if text else []


def _uses_docker(parts):
    if not parts:
        return False
    name = Path(parts[0]).name.lower()
    return name in {"docker", "docker.exe", "podman", "podman.exe"}


def _host_workspace_root():
    return Path(getattr(settings, "DSH_SORT_WORKSPACE", "") or "").expanduser()


def _container_workspace_root():
    return (getattr(settings, "DSH_HEADLESS_CONTAINER_CWD", "") or "").strip()


def mapped_cwd(host_cwd):
    host_path = Path(host_cwd).expanduser()
    try:
        host_path = host_path.resolve()
    except OSError as exc:
        raise DshRunError(f"Не удалось прочитать рабочий каталог DSH: {exc}") from exc

    container_root = _container_workspace_root()
    if not container_root:
        return str(host_path)

    host_root = _host_workspace_root()
    if not str(host_root):
        raise DshRunError(
            "Задан DSH_HEADLESS_CONTAINER_CWD, но пуст DSH_SORT_WORKSPACE. "
            "На проде рабочий каталог прогона должен совпадать с volume "
            "/opt/dsh/workspace (внутри контейнера /workspace)."
        )
    try:
        host_root = host_root.resolve()
    except OSError as exc:
        raise DshRunError(f"Не удалось прочитать DSH_SORT_WORKSPACE: {exc}") from exc
    try:
        relative = host_path.relative_to(host_root)
    except ValueError as exc:
        raise DshRunError(
            f"Каталог прогона {host_path} вне DSH_SORT_WORKSPACE ({host_root}). "
            "Django и контейнер DSH должны видеть один и тот же bind-mount."
        ) from exc
    return str(Path(container_root) / relative)


def command_parts(host_cwd):
    parts = _configured_command()
    if not parts:
        raise DshRunError(
            "Не задана команда DSH_HEADLESS_CMD. "
            "Локально: установите DSH через ./scripts/dev_dsh.sh "
            "(settings.local подставит бинарник из deploy/dsh/data/npm). "
            "На проде: docker compose exec в стек /opt/dsh "
            "(см. deploy/dsh/prod.env.dsh.example)."
        )
    container_root = _container_workspace_root()
    joined = " ".join(parts)
    if container_root and "{cwd}" not in joined:
        raise DshRunError(
            "Для DSH в контейнере в DSH_HEADLESS_CMD нужен плейсхолдер {cwd} "
            "(например: docker compose ... exec -T -w {cwd} dsh dsh --profile headless)."
        )
    mapped = mapped_cwd(host_cwd)
    return [part.replace("{cwd}", mapped) for part in parts]


def headless_env(parts):
    env = os.environ.copy()
    docker = _uses_docker(parts)
    if not docker:
        dsh_home = (getattr(settings, "DSH_HOME", "") or "").strip()
        if dsh_home:
            env["DSH_HOME"] = dsh_home
        npm_cache = (getattr(settings, "DSH_NPM_CACHE", "") or "").strip()
        if npm_cache:
            cache_dir = Path(npm_cache)
            cache_dir.mkdir(parents=True, exist_ok=True)
            env["npm_config_cache"] = str(cache_dir)
        extra_path = (getattr(settings, "DSH_NODE_BIN", "") or "").strip()
        if extra_path:
            env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
    return env


def _summarize_failure(stdout, stderr, code):
    text = (stderr or stdout or "").strip()
    lines = [
        line
        for line in text.splitlines()
        if line.strip()
        and "EBADENGINE" not in line
        and "npm warn" not in line.casefold()
    ]
    if not lines:
        lines = [line for line in text.splitlines() if line.strip()][-8:]
    snippet = "\n".join(lines[-12:]).strip() or f"DSH завершился с кодом {code}."
    if "v18." in text or "Unsupported engine" in text:
        snippet = (
            "DSH запущен слишком старым Node. Нужен Node >= 20 "
            "(локально nvm 22 / ./scripts/dev_dsh.sh, на проде образ imc-dsh).\n"
            f"{snippet}"
        )
    return snippet


def _stop_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_headless(
    prompt,
    *,
    cwd,
    timeout=None,
    heartbeat=None,
    heartbeat_interval=30,
):
    parts = command_parts(cwd)
    timeout_seconds = timeout
    if timeout_seconds is None:
        timeout_seconds = int(getattr(settings, "DSH_HEADLESS_TIMEOUT", 900) or 900)

    try:
        process = subprocess.Popen(
            [*parts, str(prompt)],
            cwd=str(cwd),
            env=headless_env(parts),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        missing = parts[0] if parts else "dsh"
        if _uses_docker(parts):
            raise DshRunError(
                f"Не удалось вызвать Docker для DSH ({missing}). "
                "На проде должен быть запущен стек /opt/dsh."
            ) from exc
        raise DshRunError(f"Не удалось запустить DSH: {exc}") from exc
    started = time.monotonic()
    interval = max(float(heartbeat_interval or 30), 1.0)
    while True:
        elapsed = time.monotonic() - started
        remaining = float(timeout_seconds) - elapsed
        if remaining <= 0:
            _stop_process(process)
            raise DshRunError(f"DSH не ответил за {timeout_seconds} с.")
        try:
            stdout, stderr = process.communicate(timeout=min(interval, remaining))
            break
        except subprocess.TimeoutExpired:
            if heartbeat is not None and heartbeat() is False:
                _stop_process(process)
                raise DshRunError("Lease прогона потерян во время выполнения DSH.")

    stdout = (stdout or "").strip()
    stderr = (stderr or "").strip()
    combined = f"{stdout}\n{stderr}".casefold()
    if "stream ended without finish_reason" in combined:
        raise DshRunError(
            "Сессия DSH оборвалась (стрим закрылся без ответа). "
            "Запустите сортировку ещё раз."
        )
    if process.returncode != 0:
        raise DshRunError(_summarize_failure(stdout, stderr, process.returncode))
    if not stdout:
        raise DshRunError("DSH вернул пустой ответ. Запустите сортировку ещё раз.")
    return stdout
