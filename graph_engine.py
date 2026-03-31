from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


class GraphEngine:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "changeme")),
        )

    def close(self):
        self.driver.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self):
        schema = Path(__file__).parent / "cypher" / "schema.cypher"
        statements = [
            s.strip()
            for s in schema.read_text().split(";")
            if s.strip() and not s.strip().startswith("//")
        ]
        with self.driver.session() as session:
            for stmt in statements:
                session.run(stmt)

    # ------------------------------------------------------------------
    # Core node upserts
    # ------------------------------------------------------------------

    def merge_library(self, name: str):
        with self.driver.session() as session:
            session.run("MERGE (:Library {name: $name})", name=name)

    def merge_version(self, library: str, number: str):
        self.merge_library(library)
        with self.driver.session() as session:
            session.run(
                "MERGE (:Version {library: $library, number: $number})",
                library=library, number=number,
            )

    def merge_environment(self, os_name: str, arch: str, python: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (:Environment {os: $os, arch: $arch, python: $python})",
                os=os_name, arch=arch, python=python,
            )

    # ------------------------------------------------------------------
    # Context layer upserts
    # ------------------------------------------------------------------

    def merge_cve(self, cve_id: str, severity: str, description: str, published: str):
        with self.driver.session() as session:
            session.run(
                """
                MERGE (c:CVE {id: $id})
                ON CREATE SET c.severity = $severity,
                              c.description = $description,
                              c.published = $published
                """,
                id=cve_id, severity=severity,
                description=description, published=published,
            )

    def merge_license(self, name: str, lic_type: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (l:License {name: $name}) ON CREATE SET l.type = $type",
                name=name, type=lic_type,
            )

    def merge_crash_cause(self, category: str, signature: str, detail: str, fix: str = "") -> str:
        with self.driver.session() as session:
            session.run(
                """
                MERGE (cc:CrashCause {category: $category, signature: $signature})
                ON CREATE SET cc.detail = $detail, cc.fix = $fix
                ON MATCH SET cc.fix = CASE WHEN $fix <> '' THEN $fix ELSE cc.fix END
                """,
                category=category, signature=signature, detail=detail, fix=fix,
            )
        return signature

    def merge_project(self, description: str, task: str) -> str:
        project_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            # Check if a similar project already exists
            result = session.run(
                "MATCH (p:Project {description: $desc}) RETURN p.id AS id LIMIT 1",
                desc=description,
            )
            row = result.single()
            if row:
                return row["id"]
            session.run(
                "CREATE (:Project {id: $id, description: $desc, task: $task, timestamp: $ts})",
                id=project_id, desc=description, task=task, ts=ts,
            )
        return project_id

    def create_bundle(self, description: str, versions: list[dict], env: dict) -> str:
        """
        versions: list of {library, version}
        """
        bundle_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            session.run(
                "CREATE (:Bundle {id: $id, description: $desc, timestamp: $ts})",
                id=bundle_id, desc=description, ts=ts,
            )
            for v in versions:
                session.run(
                    """
                    MATCH (b:Bundle {id: $bid})
                    MATCH (v:Version {library: $library, number: $number})
                    MERGE (b)-[:INCLUDES]->(v)
                    """,
                    bid=bundle_id, library=v["library"], number=v["version"],
                )
            session.run(
                """
                MATCH (b:Bundle {id: $bid})
                MATCH (e:Environment {os: $os, arch: $arch, python: $python})
                MERGE (b)-[:TESTED_ON]->(e)
                """,
                bid=bundle_id, **env,
            )
        return bundle_id

    # ------------------------------------------------------------------
    # Relationship helpers
    # ------------------------------------------------------------------

    def link_depends_on(self, lib1: str, ver1: str, lib2: str, constraint: str = ""):
        """lib1==ver1 depends on lib2 (constraint e.g. '>=1.21,<2.0')"""
        self.merge_library(lib2)
        with self.driver.session() as session:
            session.run(
                """
                MATCH (a:Version {library: $lib1, number: $ver1})
                MATCH (b:Library {name: $lib2})
                MERGE (a)-[r:DEPENDS_ON]->(b)
                ON CREATE SET r.constraint = $constraint
                """,
                lib1=lib1, ver1=ver1, lib2=lib2, constraint=constraint,
            )

    def link_compatible_with(self, library: str, version: str, env: dict):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (v:Version {library: $library, number: $version})
                MATCH (e:Environment {os: $os, arch: $arch, python: $python})
                MERGE (v)-[:COMPATIBLE_WITH]->(e)
                """,
                library=library, version=version, **env,
            )

    def link_crashes_on(self, library: str, version: str, env: dict,
                        category: str = "", detail: str = ""):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (v:Version {library: $library, number: $version})
                MATCH (e:Environment {os: $os, arch: $arch, python: $python})
                MERGE (v)-[r:CRASHES_ON]->(e)
                ON CREATE SET r.category = $category, r.detail = $detail
                """,
                library=library, version=version, category=category, detail=detail, **env,
            )

    def link_has_vulnerability(self, library: str, version: str, cve_id: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (v:Version {library: $library, number: $version})
                MATCH (c:CVE {id: $cve_id})
                MERGE (v)-[:HAS_VULNERABILITY]->(c)
                """,
                library=library, version=version, cve_id=cve_id,
            )

    def link_licensed_under(self, library: str, version: str, license_name: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (v:Version {library: $library, number: $version})
                MATCH (l:License {name: $name})
                MERGE (v)-[:LICENSED_UNDER]->(l)
                """,
                library=library, version=version, name=license_name,
            )

    def link_outcome_caused_by(self, outcome_id: str, category: str, signature: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (o:Outcome {id: $outcome_id})
                MATCH (cc:CrashCause {category: $category, signature: $signature})
                MERGE (o)-[:CAUSED_BY]->(cc)
                """,
                outcome_id=outcome_id, category=category, signature=signature,
            )

    def link_bundle_outcome(self, bundle_id: str, outcome_id: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (b:Bundle {id: $bid})
                MATCH (o:Outcome {id: $oid})
                MERGE (b)-[:RESULTED_IN]->(o)
                """,
                bid=bundle_id, oid=outcome_id,
            )

    def link_decision_project(self, decision_id: str, project_id: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (d:Decision {id: $did})
                MATCH (p:Project {id: $pid})
                MERGE (d)-[:FOR_PROJECT]->(p)
                """,
                did=decision_id, pid=project_id,
            )

    # ------------------------------------------------------------------
    # Decision + Outcome
    # ------------------------------------------------------------------

    def create_decision(
        self,
        task_id: str,
        reasoning: str,
        confidence: str,
        env: dict,
        considered: list[str],
        chosen_library: str,
        chosen_version: str,
        tool_call_trace: list[dict],
        project_id: str = "",
    ) -> str:
        decision_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            session.run(
                """
                CREATE (d:Decision {
                    id: $id,
                    task_id: $task_id,
                    timestamp: $ts,
                    reasoning: $reasoning,
                    confidence: $confidence,
                    tool_call_trace: $trace
                })
                WITH d
                MATCH (e:Environment {os: $os, arch: $arch, python: $python})
                MERGE (d)-[:MADE_IN]->(e)
                """,
                id=decision_id, task_id=task_id, ts=ts,
                reasoning=reasoning, confidence=confidence,
                trace=json.dumps(tool_call_trace), **env,
            )
            session.run(
                """
                MATCH (d:Decision {id: $id})
                MATCH (v:Version {library: $library, number: $version})
                MERGE (d)-[:CHOSE]->(v)
                """,
                id=decision_id, library=chosen_library, version=chosen_version,
            )
            for ver in considered:
                session.run(
                    """
                    MATCH (d:Decision {id: $id})
                    MATCH (v:Version {library: $library, number: $version})
                    MERGE (d)-[:CONSIDERED]->(v)
                    """,
                    id=decision_id, library=chosen_library, version=ver,
                )
            if project_id:
                session.run(
                    """
                    MATCH (d:Decision {id: $did})
                    MATCH (p:Project {id: $pid})
                    MERGE (d)-[:FOR_PROJECT]->(p)
                    """,
                    did=decision_id, pid=project_id,
                )
        return decision_id

    def create_outcome(self, decision_id: str, status: str, log: str) -> str:
        outcome_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self.driver.session() as session:
            session.run(
                """
                MATCH (d:Decision {id: $decision_id})
                CREATE (o:Outcome {id: $id, status: $status, log: $log, timestamp: $ts})
                MERGE (d)-[:RESULTED_IN]->(o)
                """,
                decision_id=decision_id, id=outcome_id,
                status=status, log=log, ts=ts,
            )
        return outcome_id

    def create_command(self, outcome_id: str, cmd: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (o:Outcome {id: $outcome_id})
                MERGE (c:Command {cmd: $cmd})
                MERGE (o)-[:SOLVED_BY]->(c)
                """,
                outcome_id=outcome_id, cmd=cmd,
            )

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def query_crashes(self, library: str, env: dict) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (v:Version {library: $library})-[r:CRASHES_ON]->(e:Environment)
                WHERE e.os = $os AND e.arch = $arch
                OPTIONAL MATCH (o:Outcome)-[:CAUSED_BY]->(cc:CrashCause)
                WHERE EXISTS {
                    MATCH (d:Decision)-[:CHOSE]->(v)
                    MATCH (d)-[:RESULTED_IN]->(o)
                }
                OPTIONAL MATCH (o)-[:SOLVED_BY]->(c:Command)
                RETURN v.number AS version,
                       r.category AS category, r.detail AS detail,
                       o.log AS log, c.cmd AS fix,
                       cc.detail AS cause_detail, cc.fix AS cause_fix
                """,
                library=library, **env,
            )
            return [dict(r) for r in result]

    def query_compatibility(self, library: str, env: dict) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (v:Version {library: $library})-[:COMPATIBLE_WITH]->(e:Environment)
                WHERE e.os = $os AND e.arch = $arch
                RETURN v.number AS version, e.os AS os, e.arch AS arch, e.python AS python
                ORDER BY v.number DESC
                """,
                library=library, **env,
            )
            return [dict(r) for r in result]

    def query_vulnerabilities(self, library: str, version: str) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (v:Version {library: $library, number: $version})-[:HAS_VULNERABILITY]->(c:CVE)
                RETURN c.id AS id, c.severity AS severity,
                       c.description AS description, c.published AS published
                ORDER BY c.severity
                """,
                library=library, version=version,
            )
            return [dict(r) for r in result]

    def query_license(self, library: str, version: str) -> dict | None:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (v:Version {library: $library, number: $version})-[:LICENSED_UNDER]->(l:License)
                RETURN l.name AS name, l.type AS type
                LIMIT 1
                """,
                library=library, version=version,
            )
            row = result.single()
            return dict(row) if row else None

    def trace_dependencies(self, library: str, version: str, depth: int = 3) -> list[dict]:
        query = f"""
            MATCH path = (v:Version {{library: $library, number: $version}})-[:DEPENDS_ON*1..{int(depth)}]->(dep)
            RETURN
                CASE WHEN dep:Version THEN dep.library ELSE dep.name END AS library,
                CASE WHEN dep:Version THEN dep.number ELSE null END AS version,
                length(path) AS depth
            ORDER BY depth
        """
        with self.driver.session() as session:
            result = session.run(query, library=library, version=version)
            return [dict(r) for r in result]

    def get_dep_constraints(self, library: str, version: str) -> list[dict]:
        """Return declared dep constraints for a version."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (v:Version {library: $library, number: $version})-[r:DEPENDS_ON]->(dep:Library)
                RETURN dep.name AS library, r.constraint AS constraint
                """,
                library=library, version=version,
            )
            return [dict(r) for r in result]

    def check_dep_conflicts(self, libraries: list[str], env: dict) -> list[dict]:
        """
        Find shared transitive deps with potentially conflicting constraints
        across the requested library set.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                UNWIND $libraries AS lib
                MATCH (v:Version {library: lib})-[r:DEPENDS_ON]->(dep:Library)
                WITH dep.name AS shared_dep, collect({lib: lib, constraint: r.constraint}) AS constraints
                WHERE size(constraints) > 1
                RETURN shared_dep, constraints
                """,
                libraries=libraries,
            )
            return [dict(r) for r in result]

    def get_bundle_history(self, libraries: list[str], env: dict) -> list[dict]:
        """Return bundles that include ALL of the requested libraries on this env."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (b:Bundle)-[:TESTED_ON]->(e:Environment)
                WHERE e.os = $os AND e.arch = $arch
                WITH b
                WHERE ALL(lib IN $libraries WHERE EXISTS {
                    MATCH (b)-[:INCLUDES]->(v:Version {library: lib})
                })
                MATCH (b)-[:INCLUDES]->(v:Version)
                OPTIONAL MATCH (b)-[:RESULTED_IN]->(o:Outcome)
                RETURN b.id AS bundle_id, b.description AS description,
                       collect(v.library + '==' + v.number) AS versions,
                       o.status AS status
                """,
                libraries=libraries, **env,
            )
            return [dict(r) for r in result]

    def get_decision_history(self, library: str) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (d:Decision)-[:CHOSE]->(v:Version {library: $library})
                OPTIONAL MATCH (d)-[:RESULTED_IN]->(o:Outcome)
                OPTIONAL MATCH (o)-[:SOLVED_BY]->(c:Command)
                OPTIONAL MATCH (o)-[:CAUSED_BY]->(cc:CrashCause)
                OPTIONAL MATCH (d)-[:MADE_IN]->(e:Environment)
                OPTIONAL MATCH (d)-[:FOR_PROJECT]->(p:Project)
                RETURN d.timestamp AS timestamp, v.number AS version,
                       d.reasoning AS reasoning, d.confidence AS confidence,
                       o.status AS outcome, o.log AS log,
                       c.cmd AS fix, cc.category AS cause_category,
                       cc.detail AS cause_detail,
                       e.os AS os, e.arch AS arch, e.python AS python,
                       p.description AS project
                ORDER BY d.timestamp DESC
                """,
                library=library,
            )
            return [dict(r) for r in result]

    def get_available_versions(self, library: str) -> list[str]:
        with self.driver.session() as session:
            result = session.run(
                "MATCH (v:Version {library: $library}) RETURN v.number AS version",
                library=library,
            )
            versions = [r["version"] for r in result]

        def _semver_key(v):
            try:
                return tuple(int(x) for x in v.split("."))
            except ValueError:
                return (0,)

        return sorted(versions, key=_semver_key, reverse=True)

    # ------------------------------------------------------------------
    # UI support queries
    # ------------------------------------------------------------------

    def get_graph_stats(self) -> dict:
        """Decision counts grouped by confidence, plus total node counts."""
        with self.driver.session() as session:
            conf = session.run(
                "MATCH (d:Decision) RETURN d.confidence AS c, count(d) AS n"
            )
            stats = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            for row in conf:
                key = (row["c"] or "LOW").upper()
                if key in stats:
                    stats[key] += row["n"]
            totals = session.run(
                """
                MATCH (l:Library) WITH count(l) AS libs
                MATCH (v:Version)  WITH libs, count(v) AS vers
                MATCH (o:Outcome)  WITH libs, vers, count(o) AS outcomes
                RETURN libs, vers, outcomes
                """
            )
            row = totals.single()
            if row:
                stats["libraries"] = row["libs"]
                stats["versions"] = row["vers"]
                stats["outcomes"] = row["outcomes"]
        return stats

    def search_decisions(
        self,
        library: str = "",
        os_name: str = "",
        version: str = "",
        phrase: str = "",
    ) -> list[dict]:
        """Search decision history by library, environment, version, or phrase."""
        conditions = []
        params: dict = {}
        if library:
            conditions.append("v.library = $library")
            params["library"] = library
        if os_name:
            conditions.append("e.os = $os")
            params["os"] = os_name
        if version:
            conditions.append("v.number = $version")
            params["version"] = version
        if phrase:
            conditions.append(
                "(toLower(d.reasoning) CONTAINS toLower($phrase) "
                "OR toLower(o.log) CONTAINS toLower($phrase))"
            )
            params["phrase"] = phrase

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            MATCH (d:Decision)-[:CHOSE]->(v:Version)
            OPTIONAL MATCH (d)-[:RESULTED_IN]->(o:Outcome)
            OPTIONAL MATCH (d)-[:MADE_IN]->(e:Environment)
            OPTIONAL MATCH (o)-[:CAUSED_BY]->(cc:CrashCause)
            {where}
            RETURN d.timestamp AS timestamp, v.library AS library,
                   v.number AS version, d.confidence AS confidence,
                   d.reasoning AS reasoning, o.status AS outcome,
                   e.os AS os, e.arch AS arch, e.python AS python,
                   cc.category AS cause_category, cc.fix AS fix
            ORDER BY d.timestamp DESC LIMIT 50
        """
        with self.driver.session() as session:
            result = session.run(query, **params)
            return [dict(r) for r in result]

    def get_library_subgraph(self, library: str, version: str) -> dict:
        """
        Return nodes + edges for the context graph around one library version.
        Used by the UI graph visualizer.
        """
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_nodes: set = set()

        def _node(nid, label, kind, extra=""):
            if nid not in seen_nodes:
                seen_nodes.add(nid)
                nodes.append({"id": nid, "label": label, "kind": kind, "title": extra})

        def _edge(src, tgt, label=""):
            edges.append({"source": src, "target": tgt, "label": label})

        lib_id = f"lib_{library}"
        ver_id = f"ver_{library}_{version}"
        _node(lib_id, library, "library", f"Library: {library}")
        _node(ver_id, version, "version", f"{library}=={version}")
        _edge(lib_id, ver_id)

        with self.driver.session() as session:
            # CVEs
            r = session.run(
                """
                MATCH (v:Version {library:$lib, number:$ver})-[:HAS_VULNERABILITY]->(c:CVE)
                RETURN c.id AS id, c.severity AS severity, c.description AS desc
                """,
                lib=library, ver=version,
            )
            for row in r:
                cid = f"cve_{row['id']}"
                _node(cid, row["id"], "cve", f"{row['severity']}: {(row['desc'] or '')[:80]}")
                _edge(ver_id, cid, "CVE")

            # Compatible environments
            r = session.run(
                """
                MATCH (v:Version {library:$lib, number:$ver})-[:COMPATIBLE_WITH]->(e:Environment)
                RETURN e.os AS os, e.arch AS arch, e.python AS py
                """,
                lib=library, ver=version,
            )
            for row in r:
                eid = f"env_{row['os']}_{row['arch']}_{row['py']}"
                label = f"{row['os']}/{row['arch']}\npy{row['py']}"
                _node(eid, label, "env_ok", f"Verified: {row['os']} {row['arch']} py{row['py']}")
                _edge(ver_id, eid, "✓")

            # Crash environments + causes
            r = session.run(
                """
                MATCH (v:Version {library:$lib, number:$ver})-[cr:CRASHES_ON]->(e:Environment)
                RETURN e.os AS os, e.arch AS arch, e.python AS py,
                       cr.category AS cat, cr.detail AS detail
                """,
                lib=library, ver=version,
            )
            for row in r:
                eid = f"crash_{row['os']}_{row['arch']}_{row['py']}"
                label = f"{row['os']}/{row['arch']}\npy{row['py']}"
                _node(eid, label, "env_crash",
                      f"CRASH: {row['cat'] or ''} — {row['detail'] or ''}")
                _edge(ver_id, eid, "CRASH")

            # License
            r = session.run(
                """
                MATCH (v:Version {library:$lib, number:$ver})-[:LICENSED_UNDER]->(l:License)
                RETURN l.name AS name, l.type AS type
                LIMIT 1
                """,
                lib=library, ver=version,
            )
            row = r.single()
            if row:
                lid = f"lic_{row['name']}"
                _node(lid, row["name"], "license", f"License: {row['type']}")
                _edge(ver_id, lid, "license")

            # Direct deps (limit to avoid clutter)
            r = session.run(
                """
                MATCH (v:Version {library:$lib, number:$ver})-[r:DEPENDS_ON]->(dep:Library)
                RETURN dep.name AS dep, r.constraint AS constraint
                LIMIT 8
                """,
                lib=library, ver=version,
            )
            for row in r:
                did = f"dep_{row['dep']}"
                _node(did, row["dep"], "dep",
                      f"dep: {row['dep']} {row['constraint'] or ''}")
                _edge(ver_id, did, row["constraint"] or "dep")

            # CrashCause nodes
            r = session.run(
                """
                MATCH (d:Decision)-[:CHOSE]->(v:Version {library:$lib, number:$ver})
                MATCH (d)-[:RESULTED_IN]->(o:Outcome)-[:CAUSED_BY]->(cc:CrashCause)
                RETURN DISTINCT cc.category AS cat, cc.detail AS detail, cc.fix AS fix
                LIMIT 4
                """,
                lib=library, ver=version,
            )
            for row in r:
                ccid = f"cc_{row['cat']}_{(row['detail'] or '')[:20]}"
                _node(ccid, row["cat"] or "CRASH", "crashcause",
                      f"{row['cat']}: {row['detail'] or ''}\nFix: {row['fix'] or ''}")
                _edge(ver_id, ccid, "caused by")

        return {"nodes": nodes, "edges": edges}
