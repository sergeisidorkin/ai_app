# docops_app/services.py
import json, re, hashlib, logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from typing import Optional
from .normalize import load_ruleset, nl_to_ir
from .compile_addin import compile_to_addin_blocks
from .ir import validate_ir

from logs_app import utils as plog

logger = logging.getLogger(__name__)
_RULESET_PATH = "docops_app/rulesets/base.ru.yml"

def _group_name_for_email(email: str, prefix: str = "user") -> str:
    # совпасть с клиентом: user_<email с @→.>, только допустимые символы
    safe = email.replace("@", ".")
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", safe).strip("._-") or "anon"
    base = f"{prefix}_{safe}"
    if len(base) >= 90:  # запас под хэш
        digest = hashlib.sha1(email.encode("utf-8")).hexdigest()[:8]
        base = f"{base[:80]}.{digest}"
    return base

def run(nl_text: str, *, email: Optional[str] = None, execute: bool = False) -> dict:
    rules = load_ruleset(_RULESET_PATH)
    program = nl_to_ir(nl_text, rules)
    validate_ir(program)
    blocks = compile_to_addin_blocks(program)

    # простой лог (без trace_id/request_id — их тут обычно нет)
    try:
        plog.info(None, phase="docops.manual", event="compile",
                  message=f"blocks={len(blocks)} execute={bool(execute)}",
                  data={"ops_preview": [b.get("kind") or b.get("op") for b in blocks[:10]]})
    except Exception:
        pass

    if execute and email:
        channel_layer = get_channel_layer()
        group_name = _group_name_for_email(email)
        logger.warning("DocOps send: group=%s blocks=%d", group_name, len(blocks))
        for block in blocks:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {"type": "addin.block", "block": block},
            )

    return {"program": program.to_dict(), "blocks": blocks}