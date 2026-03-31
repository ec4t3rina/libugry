from __future__ import annotations

import json
import re
import urllib.request
from urllib.error import URLError


_PRERELEASE = re.compile(r"(a|b|rc|dev|alpha|beta)\d*", re.IGNORECASE)


def _is_stable(version: str) -> bool:
    return not _PRERELEASE.search(version)


def _semver_key(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "libugry/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_versions(library: str, limit: int = 20) -> list[str]:
    """Return stable versions sorted newest-first, capped at limit."""
    try:
        data = _fetch_json(f"https://pypi.org/pypi/{library}/json")
        versions = [v for v in data["releases"] if _is_stable(v)]
        return sorted(versions, key=_semver_key, reverse=True)[:limit]
    except (URLError, KeyError, ValueError):
        return []


def fetch_deps(library: str, version: str) -> list[dict]:
    """Return declared dependencies as [{name, constraint}] for a specific version."""
    try:
        data = _fetch_json(f"https://pypi.org/pypi/{library}/{version}/json")
        requires = data.get("info", {}).get("requires_dist") or []
        deps = []
        for req in requires:
            # Skip extras/optional deps: "requests ; extra == 'security'"
            if ";" in req and "extra" in req:
                continue
            # Parse "numpy (>=1.21,<2.0)" or "numpy>=1.21"
            match = re.match(r"^([A-Za-z0-9_\-\.]+)\s*(.*)$", req.strip())
            if match:
                name = match.group(1).strip().lower().replace("-", "_")
                constraint = match.group(2).strip().strip("()")
                deps.append({"name": name, "constraint": constraint})
        return deps
    except (URLError, KeyError, ValueError):
        return []


def fetch_license(library: str) -> dict:
    """Return {name, type} where type is permissive|copyleft|proprietary|unknown."""
    _COPYLEFT = {"gpl", "lgpl", "agpl", "mpl", "eupl", "cddl", "osl"}
    _PERMISSIVE = {"mit", "bsd", "apache", "isc", "unlicense", "wtfpl", "zlib", "psf"}

    try:
        data = _fetch_json(f"https://pypi.org/pypi/{library}/json")
        license_name = (data.get("info", {}).get("license") or "").strip()
        if not license_name or license_name.lower() in ("unknown", "other", ""):
            # Fall back to classifiers
            classifiers = data.get("info", {}).get("classifiers") or []
            for c in classifiers:
                if "License ::" in c:
                    license_name = c.split("::")[-1].strip()
                    break

        lower = license_name.lower()
        if any(k in lower for k in _COPYLEFT):
            lic_type = "copyleft"
        elif any(k in lower for k in _PERMISSIVE):
            lic_type = "permissive"
        elif license_name:
            lic_type = "unknown"
        else:
            lic_type = "unknown"
            license_name = "Unknown"

        return {"name": license_name, "type": lic_type}
    except (URLError, KeyError, ValueError):
        return {"name": "Unknown", "type": "unknown"}
