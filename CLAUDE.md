# libugry — Context Graph CLI for Library Dependencies

## What this is
A CLI tool that advises on library versions using a Neo4j Context Graph — not static metadata, but observed reality: crash history, compatibility records, and AI decision traces with full provenance. Built with Python + Claude tool-use + Neo4j.

## Key design principle
**No overkill.** The user wants an effective, focused tool. Do not add: web UI, streaming frontend, GDS algorithms, vector search, multi-agent crews, or extra abstractions. Keep it lean.

## Architecture

```
main.py (click CLI)
  ├── env_detector.py         → {os, arch, python} fingerprint
  ├── agents/navigator.py     → Claude tool-use agentic loop (streaming)
  ├── sandbox.py              → temp venv + pip install
  └── agents/feedback.py     → Outcome node + edge writer
        ↕
  graph_engine.py             → Neo4j Bolt driver, all Cypher lives here
        ↕
  Neo4j (docker compose up -d)
```

## Graph schema (source of truth)

**Nodes:** `Library {name}`, `Version {library, number}`, `Environment {os, arch, python}`, `Decision {id, timestamp, task_id, reasoning, confidence, tool_call_trace}`, `Outcome {id, status, log, timestamp}`, `Command {cmd}`

**Edges:** `DEPENDS_ON`, `COMPATIBLE_WITH`, `CRASHES_ON`, `CONSIDERED`, `CHOSE`, `MADE_IN`, `RESULTED_IN`, `SOLVED_BY`

Constraints/indexes live in `cypher/schema.cypher` and are applied by `graph_engine.init_schema()`.

## Three-tier memory model
- **Long-term:** Library/Version/Environment facts + COMPATIBLE_WITH/CRASHES_ON edges
- **Short-term:** Decision node per request
- **Reasoning/Provenance:** `tool_call_trace` field on Decision — ordered list of graph queries Claude ran, enabling "why was this version chosen?" queries

## Navigator agent (agents/navigator.py)
- Uses `claude-sonnet-4-6` with tool-use + streaming
- Tools available to Claude: `query_crashes`, `query_compatibility`, `trace_dependencies`, `get_decision_history`, `get_available_versions`
- Agentic loop: call Claude → tool_use blocks → execute against Neo4j → append results → loop until `end_turn`
- Returns JSON: `{recommended_version, confidence, reasoning, warnings, tool_call_trace}`
- Sandbox always requires user confirmation (no auto flag)

## CLI commands
```
python main.py init              # apply schema constraints
python main.py seed              # load scipy ARM64 crash event
python main.py query <lib>       # recommend version, no install
python main.py install <lib>     # full flow: navigate → confirm → sandbox → write outcome
python main.py history <lib>     # rich table of past decisions
python main.py graph <lib>       # rich tree of dependency graph
```

## Seeded data
scipy==1.7.3 CRASHES_ON {os: macos, arch: arm64, python: 3.9}
Fix: `brew install openblas && pip install scipy==1.7.3`
scipy==1.11.4 COMPATIBLE_WITH {os: macos, arch: arm64, python: 3.11}

## Running locally
```bash
docker compose up -d     # Neo4j on :7687, browser on :7474
pip install -r requirements.txt
python main.py init && python main.py seed
python main.py query scipy
```

## Where things live
- All Cypher queries: `graph_engine.py` — do not scatter Cypher across other files
- All Neo4j CRUD: `graph_engine.GraphEngine` class — single point of contact with the DB
- Agent tools are pure functions that call `graph_engine` methods
- `env_detector.detect()` has no side effects — it does NOT write to the graph; callers do

## What to avoid
- Do not add logging frameworks, config managers, or plugin systems
- Do not split graph_engine into multiple files
- Do not add retry logic or connection pooling — Neo4j driver handles this
- Do not make sandbox async — it's intentionally synchronous and isolated
