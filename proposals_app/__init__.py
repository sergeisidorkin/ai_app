import sys


# CI can import this app through either `proposals_app` or `ai_app.proposals_app`.
# Keep both names bound to the same package object to avoid duplicate model loading.
sys.modules.setdefault("proposals_app", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app", sys.modules[__name__])

