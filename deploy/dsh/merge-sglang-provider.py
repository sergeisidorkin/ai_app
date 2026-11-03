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
        f"{p4}- image",
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


def _mapping_end(lines: list[str], start: int, parent_indent: int) -> int:
    """First line at or above ``parent_indent`` that closes the mapping."""
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _spaces(line) <= parent_indent:
            return index
    return len(lines)


def _providers_span(lines: list[str]) -> tuple[int, int, int] | None:
    """Return providers line, its indent, and the line where that mapping ends."""
    llm_at = next(
        (index for index, line in enumerate(lines) if re.match(r"^\s*llm-pi-ai:\s*$", line)),
        None,
    )
    if llm_at is None:
        return None
    llm_indent = _spaces(lines[llm_at])
    llm_end = _mapping_end(lines, llm_at, llm_indent)
    providers_at = None
    for index in range(llm_at + 1, llm_end):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _spaces(line) <= llm_indent:
            break
        if re.match(r"^\s*providers:\s*$", line):
            providers_at = index
            break
    if providers_at is None:
        return None
    providers_indent = _spaces(lines[providers_at])
    providers_end = _mapping_end(lines, providers_at, providers_indent)
    return providers_at, providers_indent, providers_end


def upsert_sglang_provider(text: str, base_url: str) -> str:
    lines = text.splitlines()
    span = _providers_span(lines)
    if span is None:
        return text
    providers_at, providers_indent, providers_end = span
    provider_indent = providers_indent + 2
    for line in lines[providers_at + 1 : providers_end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        spaces = _spaces(line)
        if spaces > providers_indent and PROVIDER_KEY.match(line.strip()):
            provider_indent = spaces
            break
    indent = " " * provider_indent
    key_re = re.compile("^" + re.escape(indent) + r"sglang:\s*$")
    start = next(
        (index for index in range(providers_at + 1, providers_end) if key_re.match(lines[index])),
        None,
    )
    block_lines = provider_block(indent, base_url).splitlines()

    if start is not None:
        end = providers_end
        for index in range(start + 1, providers_end):
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
        prefix = lines[:providers_end]
        if prefix and prefix[-1].strip():
            prefix = prefix + [""]
        updated = prefix + block_lines + lines[providers_end:]

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
