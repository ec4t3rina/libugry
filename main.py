from __future__ import annotations

import json
import os
import sys

import anthropic
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from agents import feedback, navigator
from env_detector import detect
from graph_engine import GraphEngine
from sandbox import Sandbox
from seed_data import seed

console = Console()


def get_engine() -> GraphEngine:
    try:
        engine = GraphEngine()
        engine.driver.verify_connectivity()
        return engine
    except Exception as e:
        console.print(f"[red]Cannot connect to Neo4j: {e}[/red]")
        console.print("Is Neo4j running? Try: docker compose up -d")
        sys.exit(1)


def _considered_from_trace(tool_call_trace: list[dict], library: str) -> list[str]:
    """Extract versions Claude explicitly evaluated via trace_dependencies."""
    return [
        t["args"]["version"]
        for t in tool_call_trace
        if t["tool"] == "trace_dependencies"
        and t["args"].get("library") == library
        and "version" in t["args"]
    ]


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """libugry — context-aware library dependency advisor"""
    if ctx.invoked_subcommand is None:
        _repl()


@cli.command()
def init():
    """Initialize Neo4j schema constraints and indexes."""
    engine = get_engine()
    try:
        engine.init_schema()
        console.print("[green]Schema initialized.[/green]")
    finally:
        engine.close()


@cli.command()
def seed_cmd():
    """Load foundational seed data."""
    engine = get_engine()
    try:
        seed(engine)
        console.print("[green]Seed data loaded.[/green]")
    finally:
        engine.close()


@cli.command()
@click.argument("libraries", nargs=-1, required=True)
@click.option("--project", default="", help="Brief project description for context")
def query(libraries, project):
    """Ask the Navigator to recommend versions (no install). Accepts multiple libraries."""
    engine = get_engine()
    try:
        env = detect()
        engine.merge_environment(env["os"], env["arch"], env["python"])
        libs = list(libraries)

        console.print(f"\n[bold]Environment:[/bold] {env['os']} {env['arch']} / Python {env['python']}")
        console.print(f"[bold]Navigating graph for:[/bold] {', '.join(libs)}\n")

        result = navigator.navigate(
            libs, env, engine,
            print_fn=lambda s: console.print(f"[dim]{s}[/dim]"),
            project_context=project,
        )
        _print_result(result, env)

        # Write Decision nodes for each library
        for lib_result in result.get("libraries", []):
            lib = lib_result.get("library", libs[0])
            ver = lib_result.get("recommended_version", "unknown")
            if ver == "unknown":
                continue
            engine.merge_version(lib, ver)
            considered = _considered_from_trace(result["tool_call_trace"], lib)
            engine.create_decision(
                task_id=f"query-{lib}",
                reasoning=lib_result.get("reasoning", ""),
                confidence=lib_result.get("confidence", "LOW"),
                env=env,
                considered=considered,
                chosen_library=lib,
                chosen_version=ver,
                tool_call_trace=result["tool_call_trace"],
            )
    finally:
        engine.close()


@cli.command()
@click.argument("library")
@click.option("--project", default="", help="Brief project description for context")
def install(library, project):
    """Navigate, confirm, sandbox-test, and write outcome to graph."""
    engine = get_engine()
    try:
        env = detect()
        engine.merge_environment(env["os"], env["arch"], env["python"])

        console.print(f"\n[bold]Environment:[/bold] {env['os']} {env['arch']} / Python {env['python']}")
        console.print(f"[bold]Navigating graph for:[/bold] {library}\n")

        result = navigator.navigate(
            [library], env, engine,
            print_fn=lambda s: console.print(f"[dim]{s}[/dim]"),
            project_context=project,
        )
        _print_result(result, env)

        lib_result = result["libraries"][0] if result.get("libraries") else {}
        version = lib_result.get("recommended_version", "unknown")

        if version == "unknown":
            console.print("[red]Navigator could not determine a version. Aborting.[/red]")
            return

        if not click.confirm(f"\nTest {library}=={version} in sandbox?", default=False):
            console.print("Skipped.")
            return

        console.print("\n[bold]Running sandbox install...[/bold]")
        sandbox_result = Sandbox().install(library, version)

        status_color = "green" if sandbox_result["status"] == "SUCCESS" else "red"
        console.print(f"[{status_color}]Status: {sandbox_result['status']}[/{status_color}]")
        if sandbox_result["log"]:
            console.print(Panel(sandbox_result["log"][:1000], title="Install log", style="dim"))

        engine.merge_version(library, version)
        considered = _considered_from_trace(result["tool_call_trace"], library)
        decision_id = engine.create_decision(
            task_id=f"install-{library}",
            reasoning=lib_result.get("reasoning", ""),
            confidence=lib_result.get("confidence", "LOW"),
            env=env,
            considered=considered,
            chosen_library=library,
            chosen_version=version,
            tool_call_trace=result["tool_call_trace"],
        )
        outcome_id = feedback.record_outcome(decision_id, library, version, env, sandbox_result, engine)
        console.print(f"\n[green]Graph updated.[/green] Decision: {decision_id[:8]}… Outcome: {outcome_id[:8]}…")
    finally:
        engine.close()


@cli.command()
@click.argument("library")
def history(library):
    """Show past decisions and outcomes for a library."""
    engine = get_engine()
    try:
        records = engine.get_decision_history(library)
        if not records:
            console.print(f"No history found for [bold]{library}[/bold].")
            return

        table = Table(title=f"History: {library}", show_lines=True, expand=True)
        table.add_column("Timestamp", style="dim", width=20, no_wrap=True)
        table.add_column("Version", width=10, no_wrap=True)
        table.add_column("Environment", width=20, no_wrap=True)
        table.add_column("Outcome", width=9, no_wrap=True)
        table.add_column("Cause / Fix", ratio=1, overflow="ellipsis", no_wrap=True)

        for r in records:
            if r["outcome"] == "SUCCESS":
                outcome_str = "[green]SUCCESS[/green]"
            elif r["outcome"] == "CRASH":
                outcome_str = "[red]CRASH[/red]"
            else:
                outcome_str = "-"
            env_str = f"{r['os'] or '?'} {r['arch'] or '?'} py{r['python'] or '?'}"
            # Prefer structured cause info over raw reasoning
            if r.get("cause_category"):
                detail = f"{r['cause_category']}: {r.get('cause_detail', '')}"
            elif r.get("fix"):
                detail = r["fix"]
            else:
                detail = (r.get("reasoning") or "")[:80]
            table.add_row(
                (r["timestamp"] or "")[:19],
                r["version"] or "?",
                env_str,
                outcome_str,
                detail,
            )

        console.print(table)
    finally:
        engine.close()


@cli.command("graph")
@click.argument("library")
@click.option("--version", default=None, help="Specific version (defaults to latest known)")
def graph_cmd(library, version):
    """Show dependency tree for a library version."""
    engine = get_engine()
    try:
        versions = engine.get_available_versions(library)
        if not versions:
            console.print(
                f"No versions found for [bold]{library}[/bold] in graph. "
                "Try seeding or running install first."
            )
            return

        ver = version or versions[0]
        deps = engine.trace_dependencies(library, ver, depth=3)

        tree = Tree(f"[bold]{library}=={ver}[/bold]")
        for dep in deps:
            ver_str = f"=={dep['version']}" if dep.get("version") else ""
            label = f"{dep['library']}{ver_str} [dim](depth {dep['depth']})[/dim]"
            tree.add(label)

        console.print(tree)
    finally:
        engine.close()


# ------------------------------------------------------------------
# REPL
# ------------------------------------------------------------------

def _repl():
    engine = get_engine()
    env = detect()
    engine.merge_environment(env["os"], env["arch"], env["python"])

    console.print(f"\n[bold]libugry[/bold] context graph  "
                  f"({env['os']} {env['arch']} / Python {env['python']})")
    console.print("Type your question, or [dim]'exit'[/dim] to quit.\n")

    project_context = ""
    project_id = ""

    try:
        while True:
            try:
                user_input = console.input("[bold cyan]>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break

            # Capture project context on first substantive input if not set
            if not project_context and len(user_input) > 10:
                project_context = user_input
                project_id = engine.merge_project(user_input, "repl-session")

            # Detect explicit install intent
            install_intent = user_input.lower().startswith("install ")
            if install_intent:
                lib = user_input[8:].strip().split()[0]
                libs = [lib]
            else:
                # Extract library names heuristically (simple: words that look like pypi packages)
                libs = _extract_libraries(user_input, engine)
                if not libs:
                    console.print("[dim]No libraries detected in query. Be specific, e.g. 'what version of pandas should I use?'[/dim]")
                    continue

            console.print(f"[dim]Libraries: {', '.join(libs)}[/dim]\n")

            result = navigator.navigate(
                libs, env, engine,
                print_fn=lambda s: console.print(f"[dim]{s}[/dim]"),
                project_context=project_context,
            )
            _print_result(result, env)

            if install_intent and result.get("libraries"):
                lib_result = result["libraries"][0]
                version = lib_result.get("recommended_version", "unknown")
                if version and version != "unknown" and click.confirm(f"\nTest {lib}=={version} in sandbox?", default=False):
                    sandbox_result = Sandbox().install(lib, version)
                    status_color = "green" if sandbox_result["status"] == "SUCCESS" else "red"
                    console.print(f"[{status_color}]{sandbox_result['status']}[/{status_color}]")
                    engine.merge_version(lib, version)
                    considered = _considered_from_trace(result["tool_call_trace"], lib)
                    decision_id = engine.create_decision(
                        task_id=f"repl-install-{lib}",
                        reasoning=lib_result.get("reasoning", ""),
                        confidence=lib_result.get("confidence", "LOW"),
                        env=env,
                        considered=considered,
                        chosen_library=lib,
                        chosen_version=version,
                        tool_call_trace=result["tool_call_trace"],
                        project_id=project_id,
                    )
                    outcome_id = feedback.record_outcome(
                        decision_id, lib, version, env, sandbox_result, engine
                    )
                    console.print(f"[green]Graph updated.[/green] Decision: {decision_id[:8]}…")
            else:
                # Write query decisions
                for lib_result in result.get("libraries", []):
                    lib = lib_result.get("library", libs[0])
                    ver = lib_result.get("recommended_version", "unknown")
                    if not ver or ver == "unknown":
                        continue
                    engine.merge_version(lib, ver)
                    considered = _considered_from_trace(result["tool_call_trace"], lib)
                    engine.create_decision(
                        task_id=f"repl-query-{lib}",
                        reasoning=lib_result.get("reasoning", ""),
                        confidence=lib_result.get("confidence", "LOW"),
                        env=env,
                        considered=considered,
                        chosen_library=lib,
                        chosen_version=ver,
                        tool_call_trace=result["tool_call_trace"],
                        project_id=project_id,
                    )

            console.print()

    finally:
        engine.close()


def _extract_libraries(text: str, engine: GraphEngine) -> list[str]:
    """
    Extract library names from freeform text.
    Strategy: check each word/token against known libraries in graph first (free);
    fall back to Claude haiku extraction when nothing matches (handles short names,
    hyphenated packages, and name normalization like beautifulsoup → beautifulsoup4).
    """
    import re
    with engine.driver.session() as s:
        result = s.run("MATCH (l:Library) RETURN l.name AS name")
        known = {r["name"].lower() for r in result}

    # Match whole tokens including hyphens/underscores (e.g. apache-airflow, scikit-learn)
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]*", text)
    found = [t.lower() for t in tokens if t.lower() in known]
    if found:
        return list(dict.fromkeys(found))

    # Fallback: Claude haiku extracts and normalises library names from natural language
    return _claude_extract_libraries(text)


def _claude_extract_libraries(text: str) -> list[str]:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{
                "role": "user",
                "content": (
                    "Extract Python package names from this text. "
                    "Use canonical PyPI names (e.g. beautifulsoup4 not beautifulsoup, "
                    "scikit-learn not sklearn, Pillow not PIL). "
                    "Ignore generic words like 'deep learning', 'data pipeline', 'AWS'. "
                    "Return ONLY a JSON array of strings, nothing else.\n\n"
                    f"Text: {text}"
                ),
            }],
        )
        raw = response.content[0].text.strip()
        libs = json.loads(raw[raw.find("["):raw.rfind("]") + 1])
        return [l.lower() for l in libs if isinstance(l, str)][:5]
    except Exception:
        return []


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------

def _print_result(result: dict, env: dict):
    """Print the full navigator result — handles multi-library responses."""
    libs = result.get("libraries", [])
    conflicts = result.get("conflicts", [])
    bundle_verified = result.get("bundle_verified", False)
    summary = result.get("summary", "")

    for lib_result in libs:
        lib = lib_result.get("library", "?")
        ver = lib_result.get("recommended_version", "unknown")
        confidence = lib_result.get("confidence", "LOW")
        reasoning = lib_result.get("reasoning", "")
        warnings = lib_result.get("warnings", [])
        cve_flags = lib_result.get("cve_flags", [])
        license_info = lib_result.get("license", "")

        conf_color = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}.get(confidence, "white")

        lines = [
            f"[bold]Recommended:[/bold] {lib}=={ver}",
            f"[bold]Confidence:[/bold] [{conf_color}]{confidence}[/{conf_color}]",
        ]
        if license_info:
            lines.append(f"[bold]License:[/bold] {license_info}")
        if cve_flags:
            lines.append(f"[bold][red]CVEs:[/red][/bold] {', '.join(cve_flags)}")
        lines += ["", reasoning]
        if warnings:
            lines += ["", "[yellow]Warnings:[/yellow]"] + [f"  • {w}" for w in warnings]

        console.print(Panel("\n".join(lines), title=f"Navigator — {lib}", border_style="blue"))

    if conflicts:
        console.print(Panel(
            "\n".join(f"  • {c}" for c in conflicts),
            title="[yellow]Dependency Conflicts[/yellow]",
            border_style="yellow",
        ))

    if bundle_verified:
        console.print("[green]✓ This combination has a verified working bundle record.[/green]")

    if summary and len(libs) > 1:
        console.print(f"\n[dim]{summary}[/dim]")


cli.add_command(seed_cmd, name="seed")


if __name__ == "__main__":
    cli()
