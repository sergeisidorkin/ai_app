#!/usr/bin/env python3
"""Insert or replace the local SGLang provider in a DSH settings file.

The rest of the file is left intact, including YAML 1.1 keys such as ``off``.
``agent-default-model`` is not modified.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

MODEL_ID = "qwen3.8-27b-local"
PROVIDER_KEY = re.compile(r"^([A-Za-z0-9_-]+):\s*$")


def provider_block(indent: str, base_url: str) -> str:
    p2 = indent + "  "
    p4 = p2 + "  "
    p6 = p4 + "  "
    lines = [
        f"{indent}sglang:",
        f"{p2}displayName: SGLang",
        f"{p2}apiKeyEnv: SGLANG_API_KEY",
        f"{p2}api: openai-completions",
        f"{p2}baseURL: {base_url}",
        f"{p2}compat:",
        f"{p4}supportsDeveloperRole: false",
        f"{p4}maxTokensField: max_tokens",
        f"{p4}thinkingFormat: qwen",
        f"{p2}models:",
        f"{p2}- id: {MODEL_ID}",
        f"{p4}name: Qwen3.8-27B (локально)",
        f"{p4}input:",
        f"{p4}- text",
        f"{p4}contextWindow: 32768",
        f"{p4}maxTokens: 8192",
        f"{p4}reasoningEfforts:",
        f"{p6}'off': null",
        f"{p6}low: low",
        f"{p6}medium: medium",
        f"{p6}high: high",
        f"{p6}xhigh: xhigh",
    ]
    return "\n".join(lines) + "\n"


def _spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def upsert_sglang_provider(text: str, base_url: str) -> str:
    lines = text.splitlines()
    default_at = next(
        (index for index, line in enumerate(lines) if line.startswith("agent-default-model:")),
        None,
    )
    search_until = default_at if default_at is not None else len(lines)
    providers_at = next(
        (
            index
            for index, line in enumerate(lines[:search_until])
            if re.match(r"^\s*providers:\s*$", line)
        ),
        None,
    )
    provider_indent = 4
    if providers_at is not None:
        base_indent = _spaces(lines[providers_at])
        for line in lines[providers_at + 1 : search_until]:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            spaces = _spaces(line)
            if spaces > base_indent and PROVIDER_KEY.match(line.strip()):
                provider_indent = spaces
                break
    indent = " " * provider_indent
    key_re = re.compile("^" + re.escape(indent) + r"sglang:\s*$")
    start = next((index for index, line in enumerate(lines) if key_re.match(line)), None)
    block_lines = provider_block(indent, base_url).splitlines()

    if start is not None:
        end = default_at if default_at is not None and default_at > start else len(lines)
        for index in range(start + 1, end):
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            spaces = _spaces(line)
            stripped = line.strip()
            if spaces < provider_indent or (
                spaces == provider_indent and PROVIDER_KEY.match(stripped)
            ):
                end = index
                break
        updated = lines[:start] + block_lines + lines[end:]
    else:
        insert_at = default_at if default_at is not None else len(lines)
        prefix = lines[:insert_at]
        if prefix and prefix[-1].strip():
            prefix = prefix + [""]
        updated = prefix + block_lines + lines[insert_at:]

    rendered = "\n".join(updated)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: dsh-merge-sglang SETTINGS", file=sys.stderr)
        return 2
    base_url = os.environ.get("SGLANG_BASE_URL", "").strip()
    if not base_url:
        return 0
    if re.fullmatch(r"https?://\S+", base_url) is None:
        print("sglang: invalid SGLANG_BASE_URL", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    if not path.is_file():
        return 0
    original = path.read_text(encoding="utf-8")
    updated = upsert_sglang_provider(original, base_url)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        print(f"[dsh] sglang provider -> {base_url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
