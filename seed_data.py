"""
Foundational Context Graph seed data.
Includes: libraries, versions, environments, dep constraints,
crash events with CrashCause stubs, compat records, and known bundles.
"""
from graph_engine import GraphEngine


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------
ENVS = [
    {"os": "macos",  "arch": "arm64",  "python": "3.9"},
    {"os": "macos",  "arch": "arm64",  "python": "3.11"},
    {"os": "linux",  "arch": "x86_64", "python": "3.11"},
    {"os": "linux",  "arch": "x86_64", "python": "3.9"},
    {"os": "linux",  "arch": "x86_64", "python": "3.8"},
]

# ---------------------------------------------------------------------------
# Libraries + versions  {library: [versions]}
# ---------------------------------------------------------------------------
VERSIONS = {
    "scipy":              ["1.7.3", "1.9.3", "1.11.4"],
    "numpy":              ["1.19.0", "1.21.0", "1.24.4", "1.26.2"],
    "pandas":             ["1.3.5", "2.0.3", "2.1.4"],
    "requests":           ["2.27.0", "2.31.0", "2.32.3"],
    "pillow":             ["9.0.0", "9.5.0", "10.3.0"],
    "torch":              ["2.0.0", "2.1.2"],
    "scikit_learn":       ["1.0.2", "1.3.2"],
    "matplotlib":         ["3.5.3", "3.8.4"],
    "python_dateutil":    ["2.8.2"],
    "certifi":            ["2023.7.22", "2024.2.2"],
    "urllib3":            ["1.26.18", "2.2.1"],
    "charset_normalizer": ["3.3.2"],
    "idna":               ["3.6"],
}

# ---------------------------------------------------------------------------
# Declared dependency constraints  (lib, version) -> [(dep_lib, constraint)]
# ---------------------------------------------------------------------------
DEPS = [
    ("scipy",    "1.7.3",  "numpy",           ">=1.16.5,<2.0"),
    ("scipy",    "1.11.4", "numpy",           ">=1.21.6,<2.0"),
    ("scipy",    "1.9.3",  "numpy",           ">=1.18.5,<2.0"),
    ("pandas",   "2.1.4",  "numpy",           ">=1.23.2"),
    ("pandas",   "2.1.4",  "python_dateutil", ">=2.8.2"),
    ("pandas",   "1.3.5",  "numpy",           ">=1.17.3"),
    ("pandas",   "1.3.5",  "python_dateutil", ">=2.7.3"),
    ("requests", "2.31.0", "certifi",         ">=2017.4.17"),
    ("requests", "2.31.0", "urllib3",         ">=1.21.1,<3"),
    ("requests", "2.31.0", "idna",            ">=2.5,<4"),
    ("requests", "2.31.0", "charset_normalizer", ">=2,<4"),
    ("requests", "2.32.3", "certifi",         ">=2017.4.17"),
    ("requests", "2.32.3", "urllib3",         ">=1.21.1,<3"),
    ("scikit_learn", "1.3.2", "numpy",        ">=1.17.3,<2.0"),
    ("matplotlib",   "3.8.4", "numpy",        ">=1.21"),
]

# ---------------------------------------------------------------------------
# Crash events  {library, version, env_key, category, detail, fix, log}
# ---------------------------------------------------------------------------
CRASHES = [
    {
        "library": "scipy", "version": "1.7.3",
        "env": {"os": "macos", "arch": "arm64", "python": "3.9"},
        "category": "MISSING_SYSTEM_DEP",
        "detail": "libopenblas.dylib",
        "fix": "brew install openblas && pip install scipy==1.7.3",
        "log": "ImportError: libopenblas.dylib not found — scipy requires OpenBLAS on macOS ARM64",
        "reasoning": "scipy 1.7.3 pre-dates native ARM64 OpenBLAS wheels. Requires manual brew install.",
    },
    {
        "library": "pillow", "version": "9.0.0",
        "env": {"os": "macos", "arch": "arm64", "python": "3.9"},
        "category": "MISSING_SYSTEM_DEP",
        "detail": "libjpeg",
        "fix": "brew install libjpeg && pip install pillow==9.0.0",
        "log": "ValueError: jpeg is required unless explicitly disabled using --disable-jpeg",
        "reasoning": "pillow 9.0.0 does not bundle libjpeg for ARM64. Requires Homebrew jpeg.",
    },
    {
        "library": "numpy", "version": "1.19.0",
        "env": {"os": "macos", "arch": "arm64", "python": "3.9"},
        "category": "ARCH_INCOMPATIBLE",
        "detail": "pre-ARM64 build, no universal2 wheel",
        "fix": "pip install numpy>=1.21",
        "log": "ERROR: numpy-1.19.0 does not provide a universal2 wheel. "
               "Installation failed: no compatible wheel found for arm64.",
        "reasoning": "numpy ARM64 support starts at 1.21.0. Versions prior to that have no arm64 wheel.",
    },
    {
        "library": "torch", "version": "2.0.0",
        "env": {"os": "linux", "arch": "x86_64", "python": "3.8"},
        "category": "PYTHON_VERSION_TOO_OLD",
        "detail": "torch>=2.0.0 requires Python>=3.9",
        "fix": "upgrade to Python 3.9+ or use torch<2.0.0",
        "log": "ERROR: torch-2.0.0 requires Python >=3.9 but the running Python is 3.8.x",
        "reasoning": "PyTorch 2.0 dropped Python 3.8 support.",
    },
]

# ---------------------------------------------------------------------------
# Compatibility records  (library, version, env)
# ---------------------------------------------------------------------------
COMPAT = [
    ("scipy",       "1.11.4", {"os": "macos",  "arch": "arm64",  "python": "3.11"}),
    ("scipy",       "1.11.4", {"os": "linux",  "arch": "x86_64", "python": "3.11"}),
    ("numpy",       "1.26.2", {"os": "macos",  "arch": "arm64",  "python": "3.11"}),
    ("numpy",       "1.26.2", {"os": "linux",  "arch": "x86_64", "python": "3.11"}),
    ("pandas",      "2.1.4",  {"os": "linux",  "arch": "x86_64", "python": "3.11"}),
    ("pandas",      "2.1.4",  {"os": "macos",  "arch": "arm64",  "python": "3.11"}),
    ("requests",    "2.31.0", {"os": "linux",  "arch": "x86_64", "python": "3.11"}),
    ("requests",    "2.31.0", {"os": "macos",  "arch": "arm64",  "python": "3.11"}),
    ("requests",    "2.32.3", {"os": "macos",  "arch": "arm64",  "python": "3.9"}),
    ("pillow",      "10.3.0", {"os": "macos",  "arch": "arm64",  "python": "3.11"}),
    ("scikit_learn","1.3.2",  {"os": "linux",  "arch": "x86_64", "python": "3.11"}),
    ("matplotlib",  "3.8.4",  {"os": "linux",  "arch": "x86_64", "python": "3.11"}),
    ("matplotlib",  "3.8.4",  {"os": "macos",  "arch": "arm64",  "python": "3.11"}),
]

# ---------------------------------------------------------------------------
# Known working bundles  {description, versions, env, status}
# ---------------------------------------------------------------------------
BUNDLES = [
    {
        "description": "ML stack: pandas + numpy + scikit-learn",
        "versions": [
            {"library": "pandas",      "version": "2.1.4"},
            {"library": "numpy",       "version": "1.26.2"},
            {"library": "scikit_learn","version": "1.3.2"},
        ],
        "env": {"os": "linux", "arch": "x86_64", "python": "3.11"},
        "status": "SUCCESS",
    },
    {
        "description": "Scientific stack: scipy + numpy + matplotlib",
        "versions": [
            {"library": "scipy",      "version": "1.11.4"},
            {"library": "numpy",      "version": "1.26.2"},
            {"library": "matplotlib", "version": "3.8.4"},
        ],
        "env": {"os": "macos", "arch": "arm64", "python": "3.11"},
        "status": "SUCCESS",
    },
    {
        "description": "HTTP stack: requests + certifi + urllib3",
        "versions": [
            {"library": "requests", "version": "2.31.0"},
            {"library": "certifi",  "version": "2023.7.22"},
            {"library": "urllib3",  "version": "2.2.1"},
        ],
        "env": {"os": "linux", "arch": "x86_64", "python": "3.11"},
        "status": "SUCCESS",
    },
]

# ---------------------------------------------------------------------------
# Licenses (library -> {name, type})
# ---------------------------------------------------------------------------
LICENSES = {
    "scipy":           {"name": "BSD License",  "type": "permissive"},
    "numpy":           {"name": "BSD License",  "type": "permissive"},
    "pandas":          {"name": "BSD License",  "type": "permissive"},
    "requests":        {"name": "Apache-2.0",   "type": "permissive"},
    "pillow":          {"name": "HPND",          "type": "permissive"},
    "torch":           {"name": "BSD License",  "type": "permissive"},
    "scikit_learn":    {"name": "BSD License",  "type": "permissive"},
    "matplotlib":      {"name": "PSF License",  "type": "permissive"},
    "certifi":         {"name": "MPL-2.0",       "type": "copyleft"},
    "urllib3":         {"name": "MIT License",  "type": "permissive"},
    "charset_normalizer": {"name": "MIT License", "type": "permissive"},
    "idna":            {"name": "BSD License",  "type": "permissive"},
    "python_dateutil": {"name": "Apache/BSD",   "type": "permissive"},
}


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------
def seed(engine: GraphEngine):
    # Environments
    for env in ENVS:
        engine.merge_environment(env["os"], env["arch"], env["python"])

    # Libraries + versions + licenses
    for library, versions in VERSIONS.items():
        engine.merge_library(library)
        for version in versions:
            engine.merge_version(library, version)
        if library in LICENSES:
            lic = LICENSES[library]
            engine.merge_license(lic["name"], lic["type"])
            for version in versions:
                engine.link_licensed_under(library, version, lic["name"])

    # Dep constraints
    for lib, ver, dep, constraint in DEPS:
        engine.link_depends_on(lib, ver, dep, constraint)

    # Crash events + CrashCause stubs + historical Decision/Outcome
    for crash in CRASHES:
        env = crash["env"]
        engine.link_crashes_on(
            crash["library"], crash["version"], env,
            category=crash["category"], detail=crash["detail"],
        )
        engine.merge_crash_cause(
            category=crash["category"],
            signature=crash["detail"],
            detail=crash["detail"],
            fix=crash["fix"],
        )
        # Historical decision record
        decision_id = engine.create_decision(
            task_id=f"seed-{crash['library']}-{crash['version']}",
            reasoning=crash["reasoning"],
            confidence="LOW",
            env=env,
            considered=[crash["version"]],
            chosen_library=crash["library"],
            chosen_version=crash["version"],
            tool_call_trace=[],
        )
        outcome_id = engine.create_outcome(decision_id, status="CRASH", log=crash["log"])
        engine.create_command(outcome_id, crash["fix"])
        engine.link_outcome_caused_by(outcome_id, crash["category"], crash["detail"])

    # Compat records
    for library, version, env in COMPAT:
        engine.link_compatible_with(library, version, env)

    # Bundles
    for bundle in BUNDLES:
        bundle_id = engine.create_bundle(
            bundle["description"],
            bundle["versions"],
            bundle["env"],
        )
        outcome_id = engine.create_outcome(
            # Bundles get a standalone outcome (no decision)
            # We create a minimal decision to satisfy the FK
            engine.create_decision(
                task_id=f"seed-bundle-{bundle_id[:8]}",
                reasoning=f"Known working combination: {bundle['description']}",
                confidence="HIGH",
                env=bundle["env"],
                considered=[v["version"] for v in bundle["versions"]],
                chosen_library=bundle["versions"][0]["library"],
                chosen_version=bundle["versions"][0]["version"],
                tool_call_trace=[],
            ),
            status=bundle["status"],
            log=f"Seeded verified bundle: {bundle['description']}",
        )
        engine.link_bundle_outcome(bundle_id, outcome_id)


if __name__ == "__main__":
    engine = GraphEngine()
    try:
        seed(engine)
        print("Seed data loaded.")
    finally:
        engine.close()
