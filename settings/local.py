from .base import *

DEBUG = True
READ_DOTENV = True  # читаем .env локально

OPENAI_FILTER_MODELS = False
OPENAI_ALLOWED_PREFIXES = ("gpt-4", "gpt-4o", "o4")

if not (DSH_BASE_URL or "").strip():
    DSH_BASE_URL = "http://127.0.0.1:3080"
if not (DSH_LAUNCH_URL_FILE or "").strip():
    DSH_LAUNCH_URL_FILE = str(BASE_DIR / "deploy" / "dsh" / "data" / "web-launch.url")
if not (DSH_HOME or "").strip():
    DSH_HOME = str(BASE_DIR / "deploy" / "dsh" / "data" / "home")
_LOCAL_DSH_BIN = BASE_DIR / "deploy" / "dsh" / "data" / "npm" / "node_modules" / ".bin" / "dsh"
if not (DSH_HEADLESS_CMD or "").strip() and _LOCAL_DSH_BIN.exists():
    DSH_HEADLESS_CMD = f"{_LOCAL_DSH_BIN} --profile headless"


def _local_nvm_bin_dir():
    nvm_versions = Path.home() / ".nvm" / "versions" / "node"
    if not nvm_versions.is_dir():
        return None
    preferred = sorted(nvm_versions.glob("v22*"), reverse=True)
    fallback = sorted(nvm_versions.glob("v2[0-9]*"), reverse=True)
    for version_dir in preferred + fallback:
        if (version_dir / "bin" / "node").exists():
            return version_dir / "bin"
    return None


_local_path_dirs = []
_local_nvm = _local_nvm_bin_dir()
if _local_nvm:
    _local_path_dirs.append(str(_local_nvm))
if _LOCAL_DSH_BIN.exists():
    _local_path_dirs.append(str(_LOCAL_DSH_BIN.parent))
if not (DSH_NODE_BIN or "").strip() and _local_path_dirs:
    DSH_NODE_BIN = os.pathsep.join(_local_path_dirs)
if not (DSH_NPM_CACHE or "").strip():
    DSH_NPM_CACHE = str(BASE_DIR / "deploy" / "dsh" / "data" / "cache" / "npm")
if not (DSH_SORT_WORKSPACE or "").strip():
    DSH_SORT_WORKSPACE = str(BASE_DIR / "deploy" / "dsh" / "data" / "sort-runs")
DSH_SORT_ALLOW_LOCAL_INBOX = True
if not DSH_SORT_LOCAL_ROOTS:
    DSH_SORT_LOCAL_ROOTS = (
        str(Path.home() / "Desktop" / "Workspace"),
        str(BASE_DIR / "tmp"),
    )

# WhiteNoise в dev, чтобы статика работала под Daphne
WHITENOISE_AUTOREFRESH = True       # авто-перечитывать файлы без collectstatic
WHITENOISE_USE_FINDERS = True       # искать статику через finders в DEBUG