from __future__ import annotations

import os
import re

import anthropic
from dotenv import load_dotenv

from graph_engine import GraphEngine

load_dotenv()

# ------------------------------------------------------------------
# Fix command extraction
# ------------------------------------------------------------------

_FIX_PATTERNS = [
    r"(brew install \S+(?:\s+\S+)*)",
    r"(apt-get install \S+(?:\s+\S+)*)",
    r"(apt install \S+(?:\s+\S+)*)",
    r"(conda install \S+(?:\s+\S+)*)",
    r"(pip install \S+(?:\s+\S+)*)",
]


def _extract_fix(log: str) -> str | None:
    for pattern in _FIX_PATTERNS:
        match = re.search(pattern, log)
        if match:
            return match.group(1)
    return None


# ------------------------------------------------------------------
# Tier 1 — regex crash classification
# ------------------------------------------------------------------

_CRASH_PATTERNS = [
    (
        r"(lib[\w\-]+\.(?:dylib|so|dll))\s+not found|ImportError.*?(lib[\w\-]+\.(?:dylib|so))",
        "MISSING_SYSTEM_DEP",
    ),
    (
        r"requires Python\s*[>=<]+\s*[\d.]+|Python\s+[\d.]+\s+is not supported|"
        r"This package requires Python",
        "PYTHON_VERSION_TOO_OLD",
    ),
    (
        r"ResolutionImpossible|version conflict|incompatible versions|"
        r"cannot be installed because.*requires",
        "DEP_VERSION_CONFLICT",
    ),
    (
        r"No matching distribution found",
        "VERSION_NOT_EXIST",
    ),
    (
        r"illegal instruction|unsupported.*arch|no wheel.*for.*(arm64|aarch64|x86_64)|"
        r"universal2.*not.*available",
        "ARCH_INCOMPATIBLE",
    ),
]


def _extract_signature(log: str) -> str:
    """Extract the key error line to use as dedup signature."""
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith(("ERROR:", "ImportError:", "ValueError:", "OSError:")):
            return stripped[:150]
    # Fall back to last non-empty line
    lines = [l.strip() for l in log.splitlines() if l.strip()]
    return lines[-1][:150] if lines else log[:150]


def _tier1_classify(log: str) -> dict | None:
    for pattern, category in _CRASH_PATTERNS:
        match = re.search(pattern, log, re.IGNORECASE)
        if match:
            detail = match.group(0)[:100]
            return {"category": category, "detail": detail}
    return None


# ------------------------------------------------------------------
# Tier 2 — Claude classification (only when Tier 1 has no match)
# ------------------------------------------------------------------

def _tier2_classify(log: str) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    # Send only the last 20 lines to keep it tight
    tail = "\n".join(log.splitlines()[-20:])
    prompt = (
        "Classify this Python package installation crash. "
        "Return ONLY valid JSON with keys: category, detail, fix.\n"
        "category must be one of: MISSING_SYSTEM_DEP, PYTHON_VERSION_TOO_OLD, "
        "ARCH_INCOMPATIBLE, ABI_CONFLICT, DEP_VERSION_CONFLICT, VERSION_NOT_EXIST, OTHER\n"
        "detail: brief phrase describing root cause\n"
        "fix: shell command to fix it, or empty string\n\n"
        f"Log:\n{tail}"
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        import json
        parsed = json.loads(text[start:end])
        return {
            "category": parsed.get("category", "OTHER"),
            "detail": parsed.get("detail", "")[:100],
            "fix": parsed.get("fix", ""),
        }
    except Exception:
        return {"category": "OTHER", "detail": "unclassified", "fix": ""}


# ------------------------------------------------------------------
# Public interface
# ------------------------------------------------------------------

def record_outcome(
    decision_id: str,
    library: str,
    version: str,
    env: dict,
    sandbox_result: dict,
    engine: GraphEngine,
) -> str:
    status = sandbox_result["status"]
    log = sandbox_result["log"]

    outcome_id = engine.create_outcome(decision_id, status, log)

    if status == "SUCCESS":
        engine.link_compatible_with(library, version, env)
    else:
        # Classify crash cause — Tier 1 first, Tier 2 fallback
        result = _tier1_classify(log)
        if result is None:
            result = _tier2_classify(log)

        category = result["category"]
        detail = result.get("detail", "")
        fix = result.get("fix", "") or _extract_fix(log) or ""
        signature = _extract_signature(log)

        # Write CrashCause (MERGE — shared across libraries with same root cause)
        engine.merge_crash_cause(category, signature, detail, fix)
        engine.link_outcome_caused_by(outcome_id, category, signature)
        engine.link_crashes_on(library, version, env, category=category, detail=detail)

        if fix:
            engine.create_command(outcome_id, fix)

    return outcome_id
