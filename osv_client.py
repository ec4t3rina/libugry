from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError


def check_vulnerabilities(library: str, version: str) -> list[dict]:
    """
    Query OSV.dev for CVEs affecting library==version.
    Returns list of {id, severity, description, published}.
    """
    payload = json.dumps({
        "package": {"name": library, "ecosystem": "PyPI"},
        "version": version,
    }).encode()

    req = urllib.request.Request(
        "https://api.osv.dev/v1/query",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "libugry/1.0"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, ValueError):
        return []

    results = []
    for vuln in data.get("vulns", []):
        severity = _extract_severity(vuln)
        results.append({
            "id": vuln.get("id", "UNKNOWN"),
            "severity": severity,
            "description": (vuln.get("summary") or vuln.get("details") or "")[:300],
            "published": vuln.get("published", ""),
        })

    # Sort: CRITICAL > HIGH > MEDIUM > LOW > UNKNOWN
    _order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    results.sort(key=lambda x: _order.get(x["severity"], 4))
    return results


def _extract_severity(vuln: dict) -> str:
    # Try CVSS severity from database_specific or severity list
    for entry in vuln.get("severity", []):
        score = entry.get("score", "")
        if "CRITICAL" in score.upper():
            return "CRITICAL"
        if "HIGH" in score.upper():
            return "HIGH"
        if "MEDIUM" in score.upper():
            return "MEDIUM"
        if "LOW" in score.upper():
            return "LOW"

    # Fall back to database_specific CVSS score
    db = vuln.get("database_specific", {})
    cvss = str(db.get("cvss_v3", db.get("cvss", ""))).upper()
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        if level in cvss:
            return level

    return "UNKNOWN"
