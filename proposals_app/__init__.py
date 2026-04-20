import sys
import types


# CI can import this app through either `proposals_app` or `ai_app.proposals_app`.
# Keep both names bound to the same package object to avoid duplicate model loading.
# We also register a placeholder `ai_app` package so that `importlib.import_module`
# based tooling (e.g. `mock.patch("ai_app.proposals_app.views.xxx")`) can walk the
# dotted path even when the project is not installed under a real `ai_app`
# top-level package on the filesystem.
if "ai_app" not in sys.modules:
    _ai_app_alias = types.ModuleType("ai_app")
    _ai_app_alias.__path__ = []  # mark as a namespace-like package
    sys.modules["ai_app"] = _ai_app_alias

sys.modules.setdefault("proposals_app", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app", sys.modules[__name__])

# Bind the subpackage as attribute of the synthetic parent so attribute-based
# access (`ai_app.proposals_app`) used by `mock._importer` works as well.
setattr(sys.modules["ai_app"], "proposals_app", sys.modules[__name__])

