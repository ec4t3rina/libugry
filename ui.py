"""
libugry — Streamlit UI  (cybernetic dashboard)
Run: streamlit run ui.py
"""
from __future__ import annotations

import os
import sys

import streamlit as st
from dotenv import load_dotenv
from streamlit_agraph import Config, Edge, Node, agraph

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from agents import navigator
from env_detector import detect
from graph_engine import GraphEngine
from main import _considered_from_trace, _extract_libraries

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="libugry",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@300;400;500;600&display=swap');

/* Global font */
html, body, p, div, span, label, input, select, textarea,
button, h1, h2, h3, h4, h5, h6, [class*="css"] {
    font-family: 'Fira Code', 'Courier New', monospace !important;
}

/* Custom details/summary elements (replacing st.expander) */
details > summary { list-style: none !important; outline: none !important; }
details > summary::-webkit-details-marker { display: none !important; }
details[open] > summary { color: #00FF88 !important; }

/* Dark grid background */
[data-testid="stAppViewContainer"] {
    background-color: #0D0D0D;
    background-image:
        linear-gradient(rgba(0,229,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,229,255,0.03) 1px, transparent 1px);
    background-size: 44px 44px;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stDecoration"] { display: none; }

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #111418 !important;
    border-right: 1px solid #1E2A30 !important;
}

/* Kill ALL red — Streamlit uses red focus rings by default */
*, *:focus, *:active {
    outline: none !important;
}
[data-testid="stTextInput"] > div > div {
    background: #161B22 !important;
    border: 1px solid #1E2A30 !important;
    border-radius: 3px !important;
}
[data-testid="stTextInput"] > div > div:focus-within {
    border-color: #00FF88 !important;
    box-shadow: 0 0 0 1px #00FF8844 !important;
}
[data-testid="stTextInput"] input {
    color: #B0BEC5 !important;
    background: transparent !important;
}

/* Buttons */
.stButton > button {
    background: transparent !important;
    border: 1px solid #00FF8866 !important;
    color: #00FF88 !important;
    border-radius: 2px !important;
    font-size: 0.8rem !important;
    padding: 6px 14px !important;
    transition: all 0.15s;
}
.stButton > button:hover {
    background: #00FF8812 !important;
    border-color: #00FF88 !important;
    box-shadow: 0 0 10px #00FF8833 !important;
}

/* Selectboxes */
[data-testid="stSelectbox"] > div > div {
    background: #161B22 !important;
    border: 1px solid #1E2A30 !important;
    color: #90A4AE !important;
    border-radius: 2px !important;
}
[data-testid="stSelectbox"] > div > div:focus-within {
    border-color: #00FF88 !important;
}

/* Expanders */
[data-testid="stExpander"] {
    background: #0F1318 !important;
    border: 1px solid #1E2A30 !important;
    border-radius: 3px !important;
}
[data-testid="stExpander"] summary {
    color: #90A4AE !important;
    font-size: 0.85rem !important;
}
[data-testid="stExpander"] summary:hover {
    color: #00FF88 !important;
}

/* st.info / st.warning / st.error overrides */
[data-testid="stAlert"] {
    border-radius: 2px !important;
    font-size: 0.82rem !important;
}
/* Info → dark teal */
[data-testid="stAlert"][kind="info"],
div[data-testid="stAlert"] > div[data-baseweb="notification"][kind="info"] {
    background: #0A1A1E !important;
    border-left-color: #00FF88 !important;
    color: #90A4AE !important;
}
/* Warning → dark amber */
[data-testid="stAlert"][kind="warning"] {
    background: #1A1400 !important;
    border-left-color: #FF9800 !important;
    color: #B0A070 !important;
}
/* Error → dark red */
[data-testid="stAlert"][kind="error"] {
    background: #1A0808 !important;
    border-left-color: #FF4444 !important;
    color: #B07070 !important;
}
/* Success → dark green */
[data-testid="stAlert"][kind="success"] {
    background: #081A0A !important;
    border-left-color: #4CAF50 !important;
    color: #70B074 !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #0F1318;
    border: 1px solid #1E2A30;
    border-radius: 3px;
    padding: 8px 10px;
}
[data-testid="stMetricValue"] { color: #00FF88 !important; font-size: 1.4rem !important; }
[data-testid="stMetricLabel"] { color: #37474F !important; font-size: 0.7rem !important; }

/* Dividers */
hr { border-color: #1E2A30 !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #0D0D0D; }
::-webkit-scrollbar-thumb { background: #1E2A30; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #00FF8844; }

/* Section headers */
.section-label {
    color: #00FF88;
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    margin-bottom: 10px;
    opacity: 0.8;
}

/* Log line */
.log-line {
    color: #263238;
    font-size: 0.72rem;
    padding: 2px 0;
    border-bottom: 1px solid #0F1318;
}
.log-line.active { color: #546E7A; }
</style>
""", unsafe_allow_html=True)


# ── Engine singleton ───────────────────────────────────────────────────────
@st.cache_resource
def _init_engine():
    try:
        e = GraphEngine()
        e.driver.verify_connectivity()
        return e
    except Exception:
        return None


# ── agraph builder ─────────────────────────────────────────────────────────
_NODE_COLORS = {
    "library": "#00FF88", "version": "#CFD8DC", "cve": "#EF5350",
    "env_ok": "#66BB6A", "env_crash": "#EF5350",
    "license": "#81C784", "dep": "#455A64", "crashcause": "#FF7043",
}
_NODE_SIZES = {
    "library": 30, "version": 22, "cve": 16,
    "env_ok": 16, "env_crash": 16, "license": 14,
    "dep": 13, "crashcause": 16,
}


def build_agraph(subgraph: dict):
    nodes = [
        Node(
            id=n["id"],
            label=n["label"],
            color=_NODE_COLORS.get(n["kind"], "#455A64"),
            size=_NODE_SIZES.get(n["kind"], 14),
            title=n.get("title", ""),
            font={"color": "#78909C", "size": 10, "face": "Fira Code"},
        )
        for n in subgraph["nodes"]
    ]
    edges = [
        Edge(
            source=e["source"],
            target=e["target"],
            label=e.get("label", ""),
            color="#00FF8833",
            font={"color": "#37474F", "size": 8, "face": "Fira Code"},
        )
        for e in subgraph["edges"]
    ]
    cfg = Config(
        width="100%",
        height=340,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#00FF88",
        collapsible=False,
    )
    return nodes, edges, cfg


# ── Result renderer ─────────────────────────────────────────────────────────
_CONF_COLOR = {"HIGH": "#4CAF50", "MEDIUM": "#FF9800", "LOW": "#EF5350"}


def render_result(result: dict):
    libs            = result.get("libraries", [])
    conflicts       = result.get("conflicts", [])
    bundle_verified = result.get("bundle_verified", False)
    summary         = result.get("summary", "")

    # ── 1. Answer first: one-line recommendation ──────────────────
    recs = [
        f"{lr['library']}=={lr['recommended_version']}"
        for lr in libs
        if lr.get("recommended_version") and lr["recommended_version"] != "unknown"
    ]
    if recs:
        bundle_mark = "✓ BUNDLE VERIFIED" if bundle_verified else "RECOMMENDED"
        st.markdown(
            f'<div style="background:#081A0E;border:1px solid #00FF8866;'
            f'border-left:4px solid #00FF88;border-radius:3px;'
            f'padding:16px 20px;margin-bottom:10px;">'
            f'<div style="color:#37474F;font-size:0.68rem;letter-spacing:0.12em;'
            f'margin-bottom:6px;">{bundle_mark}</div>'
            f'<div style="color:#00FF88;font-size:1.15rem;font-weight:600;'
            f'line-height:1.6;">{chr(10).join(recs)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Summary sentence
    if summary:
        st.markdown(
            f'<div style="color:#546E7A;font-size:0.82rem;'
            f'margin-bottom:12px;line-height:1.6;">{summary[:240]}</div>',
            unsafe_allow_html=True,
        )

    # ── 2. Per-library details (native HTML details, no Material Icons) ──
    for lr in libs:
        lib          = lr.get("library", "?")
        ver          = lr.get("recommended_version", "unknown")
        conf         = (lr.get("confidence") or "LOW").upper()
        reasoning    = lr.get("reasoning", "")
        warnings     = lr.get("warnings", [])
        cve_flags    = lr.get("cve_flags", [])
        license_info = lr.get("license", "")

        conf_col  = _CONF_COLOR.get(conf, "#607D8B")
        cve_mark  = "⚡ " if cve_flags else ""
        lic_short = (license_info or "—")[:22]
        label     = f"{cve_mark}{lib}=={ver}  ·  <span style='color:{conf_col}'>[{conf}]</span>  ·  {lic_short}"

        inner = ""
        for cve in cve_flags:
            inner += f'<div style="color:#EF5350;font-size:0.75rem;margin-bottom:4px;">⚡ {cve}</div>'
        if reasoning:
            short  = reasoning[:300] + ("…" if len(reasoning) > 300 else "")
            inner += (
                f'<div style="color:#546E7A;font-size:0.77rem;line-height:1.6;'
                f'margin-top:6px;">{short}</div>'
            )
        for w in warnings[:3]:
            inner += f'<div style="color:#FF9800;font-size:0.74rem;margin-top:6px;">⚠ {w}</div>'

        st.markdown(
            f'<details style="background:#0F1318;border:1px solid #1E2A30;'
            f'border-radius:3px;margin-bottom:6px;">'
            f'<summary style="color:#90A4AE;font-size:0.84rem;padding:10px 14px;'
            f'cursor:pointer;">▸ {label}</summary>'
            f'<div style="padding:10px 14px 12px;border-top:1px solid #1E2A30;">'
            f'{inner}</div></details>',
            unsafe_allow_html=True,
        )

    # ── 3. Conflicts: compact inline text ─────────────────────────
    if conflicts:
        items = "".join(
            f'<div style="color:#455A64;font-size:0.72rem;padding:2px 0 2px 8px;'
            f'border-left:2px solid #FF980044;margin-bottom:3px;">◈ {c[:130]}</div>'
            for c in conflicts[:5]
        )
        st.markdown(
            f'<div style="margin-top:8px;"><div style="color:#FF9800;font-size:0.68rem;'
            f'letter-spacing:0.1em;margin-bottom:4px;">CONFLICTS</div>{items}</div>',
            unsafe_allow_html=True,
        )


# ── Session state ───────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "result": None,
        "tool_log": [],
        "last_subgraph": {"nodes": [], "edges": []},
        "query": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()
engine = _init_engine()


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<p style="color:#00FF88;font-size:1.25rem;font-weight:600;'
        'letter-spacing:0.08em;margin-bottom:0;">⬡ libugry</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown('<p class="section-label">ENVIRONMENT</p>', unsafe_allow_html=True)
    detected = detect()
    os_opts   = ["macos", "linux", "windows"]
    arch_opts = ["arm64", "x86_64"]
    py_opts   = ["3.9", "3.10", "3.11", "3.12"]

    sel_os   = st.selectbox("OS",           os_opts,   index=os_opts.index(detected["os"])     if detected["os"]     in os_opts   else 0)
    sel_arch = st.selectbox("Architecture", arch_opts, index=arch_opts.index(detected["arch"]) if detected["arch"]   in arch_opts else 0)
    sel_py   = st.selectbox("Python",       py_opts,   index=py_opts.index(detected["python"]) if detected["python"] in py_opts   else 0)
    env = {"os": sel_os, "arch": sel_arch, "python": sel_py}
    st.caption(f"Detected: {detected['os']} {detected['arch']} py{detected['python']}")

    st.divider()
    st.markdown('<p class="section-label">GRAPH HEALTH</p>', unsafe_allow_html=True)

    if engine:
        try:
            stats = engine.get_graph_stats()
            c1, c2, c3 = st.columns(3)
            c1.metric("HIGH",   stats.get("HIGH", 0))
            c2.metric("MED",    stats.get("MEDIUM", 0))
            c3.metric("LOW",    stats.get("LOW", 0))
            st.caption(
                f"{stats.get('libraries',0)} libs · "
                f"{stats.get('versions',0)} versions · "
                f"{stats.get('outcomes',0)} outcomes"
            )
        except Exception:
            st.caption("metrics unavailable")
    else:
        st.error("Neo4j unreachable\n`docker compose up -d`")


# ── Main layout: LEFT = input + results, RIGHT = graph + logs ───────────────
left_col, right_col = st.columns([1, 1.2])

_TOOL_LABELS = {
    "check_vulnerabilities": "Checking OSV.dev for CVEs",
    "query_crashes":         "Querying crash records",
    "query_compatibility":   "Checking verified installs",
    "check_license":         "Checking license",
    "fetch_pypi_versions":   "Fetching versions from PyPI",
    "fetch_pypi_deps":       "Fetching dep constraints",
    "trace_dependencies":    "Tracing dependency tree",
    "check_dep_conflicts":   "Checking cross-library conflicts",
    "get_bundle_history":    "Checking verified bundles",
    "get_decision_history":  "Reviewing decision history",
    "get_available_versions":"Listing known versions",
}

# ═══════════════════════════════════════════════════
# LEFT COLUMN — input + run + results
# ═══════════════════════════════════════════════════
with left_col:
    st.markdown('<p class="section-label">NAVIGATOR</p>', unsafe_allow_html=True)

    # Query input + Run Analysis — form so Enter key submits
    with st.form("qform", clear_on_submit=False, border=False):
        query = st.text_input(
            "query",
            value=st.session_state.query,
            placeholder="e.g.  pandas numpy scikit-learn  /  I need boto3 and s3fs",
            label_visibility="collapsed",
        )
        run_clicked = st.form_submit_button("⬡  Run Analysis", use_container_width=True)

    # New Query / Clear History outside the form
    new_col, clear_col = st.columns(2)
    with new_col:
        if st.button("✕  New Query", use_container_width=True):
            st.session_state.result        = None
            st.session_state.tool_log      = []
            st.session_state.query         = ""
            st.session_state.last_subgraph = {"nodes": [], "edges": []}
            st.rerun()
    with clear_col:
        if st.button("◈  Clear History", use_container_width=True):
            st.session_state.last_subgraph = {"nodes": [], "edges": []}
            st.session_state.tool_log      = []
            st.rerun()

    # ── Run analysis ────────────────────────────────
    if run_clicked and query and engine:
        st.session_state.query = query
        libs = _extract_libraries(query, engine)

        if not libs:
            st.warning("No packages detected. Try: 'pandas numpy' or 'I need requests'.")
        else:
            log_lines: list[str] = []

            with st.status(
                f"Navigating context graph for: {', '.join(libs)} …",
                expanded=False,
            ) as status:
                def _print_fn(msg: str):
                    label = msg.strip()
                    for tool, human in _TOOL_LABELS.items():
                        if tool in label:
                            label = f"  {human}…"
                            break
                    log_lines.append(label)
                    status.write(label)

                result = navigator.navigate(
                    libs, env, engine,
                    print_fn=_print_fn,
                    project_context="",
                )
                status.update(label="Navigation complete ✓", state="complete", expanded=False)

            st.session_state.result   = result
            st.session_state.tool_log = log_lines

            for lr in result.get("libraries", []):
                lib = lr.get("library", libs[0])
                ver = lr.get("recommended_version")
                if not ver or ver == "unknown":
                    continue
                engine.merge_version(lib, ver)
                considered = _considered_from_trace(result["tool_call_trace"], lib)
                engine.create_decision(
                    task_id=f"ui-{lib}",
                    reasoning=lr.get("reasoning", ""),
                    confidence=lr.get("confidence", "LOW"),
                    env=env,
                    considered=considered,
                    chosen_library=lib,
                    chosen_version=ver,
                    tool_call_trace=result["tool_call_trace"],
                )

            first   = result.get("libraries", [{}])[0]
            fl_name = first.get("library")
            fl_ver  = first.get("recommended_version")
            if fl_name and fl_ver and fl_ver != "unknown":
                try:
                    st.session_state.last_subgraph = engine.get_library_subgraph(fl_name, fl_ver)
                except Exception:
                    pass

            st.rerun()

    # ── Results (scrollable container) ──────────────
    if st.session_state.result:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        with st.container(height=650):
            render_result(st.session_state.result)



# ═══════════════════════════════════════════════════
# RIGHT COLUMN — graph visualizer + system log
# ═══════════════════════════════════════════════════
with right_col:
    st.markdown('<p class="section-label">CONTEXT GRAPH</p>', unsafe_allow_html=True)

    sg = st.session_state.last_subgraph
    if sg["nodes"]:
        nodes_ag, edges_ag, cfg = build_agraph(sg)
        agraph(nodes=nodes_ag, edges=edges_ag, config=cfg)
        st.markdown(
            '<div style="font-size:0.68rem;color:#263238;margin-top:2px;">'
            '<span style="color:#00FF88">⬡</span> Library &nbsp;'
            '<span style="color:#CFD8DC">⬡</span> Version &nbsp;'
            '<span style="color:#EF5350">⬡</span> CVE &nbsp;'
            '<span style="color:#66BB6A">⬡</span> Compatible env &nbsp;'
            '<span style="color:#455A64">⬡</span> Dep</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="height:340px;display:flex;align-items:center;'
            'justify-content:center;border:1px dashed #1E2A30;border-radius:3px;">'
            '<span style="color:#1E2A30;font-size:0.8rem;">'
            "graph renders after first query</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # System log — always under the graph
    st.markdown('<p class="section-label">SYSTEM LOG</p>', unsafe_allow_html=True)
    if st.session_state.tool_log:
        log_html = "".join(
            f'<div class="log-line active">{line}</div>'
            for line in st.session_state.tool_log
        )
        st.markdown(
            f'<div style="background:#0A0E12;border:1px solid #1E2A30;'
            f'border-radius:3px;padding:10px 12px;max-height:200px;overflow-y:auto;">'
            f"{log_html}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="color:#1E2A30;font-size:0.75rem;">awaiting query…</div>',
            unsafe_allow_html=True,
        )
