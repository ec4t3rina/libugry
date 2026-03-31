from __future__ import annotations

import json
import os

import anthropic
from dotenv import load_dotenv

import osv_client
import pypi_client
from graph_engine import GraphEngine

load_dotenv()

SYSTEM_PROMPT = """You are the Graph Navigator for libugry — a dependency intelligence system.

You have tools to query a Neo4j Context Graph storing multiple context layers:
- Security   : CVE vulnerabilities per version (HAS_VULNERABILITY)
- Environment: crash records per OS/arch (CRASHES_ON) and verified installs (COMPATIBLE_WITH)
- Legal      : license type per version (LICENSED_UNDER)
- Structural : declared dep constraints (DEPENDS_ON)
- Historical : past decisions and their outcomes
- Bundle     : verified working combinations of multiple libraries

You will often be asked about MULTIPLE libraries at once. Reason about the full set:
- Are there dep conflicts between them?
- Have they been verified as a bundle before?
- Do any share a transitive dependency with conflicting constraints?

Reasoning order (follow this every time):
1. check_vulnerabilities — CVEs override everything. HIGH/CRITICAL = warn or reject.
2. query_crashes — what broke on this environment and why?
3. check_license — flag copyleft (GPL/AGPL/LGPL) in context of proprietary use.
4. fetch_pypi_versions — if graph has no versions, populate from PyPI first.
5. trace_dependencies / fetch_pypi_deps — build the dep tree, find constraint conflicts.
6. check_dep_conflicts — across the full library set, find shared deps with clashing constraints.
7. get_bundle_history — has this combination been verified before?
8. get_decision_history — what was chosen before and what happened?

Always ground your reasoning in graph data. State what you found, what was absent, and why.

Respond with a JSON object:
{
  "libraries": [
    {
      "library": "name",
      "recommended_version": "x.y.z",
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "reasoning": "...",
      "warnings": ["..."],
      "cve_flags": ["CVE-ID (severity)"],
      "license": "license name"
    }
  ],
  "bundle_verified": true | false,
  "conflicts": ["description of any dep conflicts found"],
  "summary": "one sentence covering the full set"
}
"""

TOOLS = [
    {
        "name": "check_vulnerabilities",
        "description": "Check CVEs for a specific library version via OSV.dev. Run this FIRST for every version you're considering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string"},
                "version": {"type": "string"},
            },
            "required": ["library", "version"],
        },
    },
    {
        "name": "query_crashes",
        "description": "Find versions of a library with recorded crash events on the current environment, including crash cause and fix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string"},
                "os": {"type": "string"},
                "arch": {"type": "string"},
            },
            "required": ["library", "os", "arch"],
        },
    },
    {
        "name": "query_compatibility",
        "description": "Find versions of a library with verified successful installs on the current environment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string"},
                "os": {"type": "string"},
                "arch": {"type": "string"},
            },
            "required": ["library", "os", "arch"],
        },
    },
    {
        "name": "check_license",
        "description": "Check the license type of a library version. Flag copyleft licenses (GPL, LGPL, AGPL).",
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string"},
                "version": {"type": "string"},
            },
            "required": ["library", "version"],
        },
    },
    {
        "name": "fetch_pypi_versions",
        "description": "Fetch real available versions from PyPI and store them in the graph. Use when get_available_versions returns empty.",
        "input_schema": {
            "type": "object",
            "properties": {"library": {"type": "string"}},
            "required": ["library"],
        },
    },
    {
        "name": "fetch_pypi_deps",
        "description": "Fetch declared dependency constraints from PyPI for a specific version and store in graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string"},
                "version": {"type": "string"},
            },
            "required": ["library", "version"],
        },
    },
    {
        "name": "trace_dependencies",
        "description": "Trace the dependency tree of a specific version up to 3 levels deep (graph data).",
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string"},
                "version": {"type": "string"},
                "depth": {"type": "integer", "default": 3},
            },
            "required": ["library", "version"],
        },
    },
    {
        "name": "check_dep_conflicts",
        "description": "Find shared transitive dependencies with potentially conflicting version constraints across a set of libraries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "libraries": {"type": "array", "items": {"type": "string"}},
                "os": {"type": "string"},
                "arch": {"type": "string"},
            },
            "required": ["libraries", "os", "arch"],
        },
    },
    {
        "name": "get_bundle_history",
        "description": "Check if a combination of libraries has been verified as a working bundle on this environment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "libraries": {"type": "array", "items": {"type": "string"}},
                "os": {"type": "string"},
                "arch": {"type": "string"},
            },
            "required": ["libraries", "os", "arch"],
        },
    },
    {
        "name": "get_decision_history",
        "description": "Retrieve past decisions and outcomes for a library, including project context.",
        "input_schema": {
            "type": "object",
            "properties": {"library": {"type": "string"}},
            "required": ["library"],
        },
    },
    {
        "name": "get_available_versions",
        "description": "List all known versions of a library currently in the graph.",
        "input_schema": {
            "type": "object",
            "properties": {"library": {"type": "string"}},
            "required": ["library"],
        },
    },
]


def _run_tool(name: str, args: dict, engine: GraphEngine, env: dict) -> str:
    if name == "check_vulnerabilities":
        # Query graph first; fall back to live OSV if not stored
        stored = engine.query_vulnerabilities(args["library"], args["version"])
        if stored:
            result = stored
        else:
            vulns = osv_client.check_vulnerabilities(args["library"], args["version"])
            for v in vulns:
                engine.merge_cve(v["id"], v["severity"], v["description"], v["published"])
                engine.merge_version(args["library"], args["version"])
                engine.link_has_vulnerability(args["library"], args["version"], v["id"])
            result = vulns

    elif name == "query_crashes":
        result = engine.query_crashes(
            args["library"],
            {"os": args["os"], "arch": args["arch"], "python": env["python"]},
        )

    elif name == "query_compatibility":
        result = engine.query_compatibility(
            args["library"],
            {"os": args["os"], "arch": args["arch"], "python": env["python"]},
        )

    elif name == "check_license":
        stored = engine.query_license(args["library"], args["version"])
        if stored:
            result = stored
        else:
            lic = pypi_client.fetch_license(args["library"])
            engine.merge_license(lic["name"], lic["type"])
            engine.merge_version(args["library"], args["version"])
            engine.link_licensed_under(args["library"], args["version"], lic["name"])
            result = lic

    elif name == "fetch_pypi_versions":
        versions = pypi_client.fetch_versions(args["library"])
        for v in versions:
            engine.merge_version(args["library"], v)
        result = versions

    elif name == "fetch_pypi_deps":
        deps = pypi_client.fetch_deps(args["library"], args["version"])
        for d in deps:
            engine.link_depends_on(args["library"], args["version"], d["name"], d["constraint"])
        result = deps

    elif name == "trace_dependencies":
        result = engine.trace_dependencies(
            args["library"], args["version"], args.get("depth", 3)
        )

    elif name == "check_dep_conflicts":
        result = engine.check_dep_conflicts(
            args["libraries"],
            {"os": args["os"], "arch": args["arch"], "python": env["python"]},
        )

    elif name == "get_bundle_history":
        result = engine.get_bundle_history(
            args["libraries"],
            {"os": args["os"], "arch": args["arch"], "python": env["python"]},
        )

    elif name == "get_decision_history":
        result = engine.get_decision_history(args["library"])

    elif name == "get_available_versions":
        result = engine.get_available_versions(args["library"])

    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, default=str)


def navigate(
    libraries: list[str],
    env: dict,
    engine: GraphEngine,
    print_fn=print,
    project_context: str = "",
) -> dict:
    """
    Walk the context graph for one or more libraries and return recommendations.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    lib_str = ", ".join(f"'{l}'" for l in libraries)
    project_line = f"\nProject context: {project_context}" if project_context else ""
    user_msg = (
        f"I need to use {lib_str} on {env['os']} {env['arch']} "
        f"(Python {env['python']}).{project_line} "
        f"What versions should I use?"
    )

    messages = [{"role": "user", "content": user_msg}]
    tool_call_trace = []
    final_text = ""

    while True:
        response_text = ""
        tool_uses = []

        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            full_response = stream.get_final_message()
            stop_reason = full_response.stop_reason

            for block in full_response.content:
                if block.type == "text":
                    response_text = block.text
                elif block.type == "tool_use":
                    tool_uses.append(block)

        messages.append({"role": "assistant", "content": full_response.content})

        if stop_reason == "end_turn" or not tool_uses:
            final_text = response_text
            break

        tool_results = []
        for tool_use in tool_uses:
            print_fn(f"  [graph] {tool_use.name}({json.dumps(tool_use.input)})")
            result = _run_tool(tool_use.name, tool_use.input, engine, env)
            tool_call_trace.append({
                "tool": tool_use.name,
                "args": tool_use.input,
                "result": json.loads(result),
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # Parse JSON response
    try:
        start = final_text.find("{")
        end = final_text.rfind("}") + 1
        parsed = json.loads(final_text[start:end])
    except Exception:
        # Normalise single-library old format for backward compat
        parsed = {
            "libraries": [
                {
                    "library": libraries[0] if libraries else "unknown",
                    "recommended_version": "unknown",
                    "confidence": "LOW",
                    "reasoning": final_text,
                    "warnings": ["Could not parse structured response"],
                    "cve_flags": [],
                    "license": "",
                }
            ],
            "bundle_verified": False,
            "conflicts": [],
            "summary": final_text[:200],
        }

    parsed["tool_call_trace"] = tool_call_trace
    return parsed
