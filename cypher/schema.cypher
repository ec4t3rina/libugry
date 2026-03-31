// libugry — Context Graph Schema
// Run via: python main.py init

// --- Core ---
CREATE CONSTRAINT library_name IF NOT EXISTS
  FOR (l:Library) REQUIRE l.name IS UNIQUE;

CREATE CONSTRAINT version_unique IF NOT EXISTS
  FOR (v:Version) REQUIRE (v.library, v.number) IS UNIQUE;

CREATE CONSTRAINT env_unique IF NOT EXISTS
  FOR (e:Environment) REQUIRE (e.os, e.arch, e.python) IS UNIQUE;

CREATE CONSTRAINT decision_id IF NOT EXISTS
  FOR (d:Decision) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT outcome_id IF NOT EXISTS
  FOR (o:Outcome) REQUIRE o.id IS UNIQUE;

// --- Context layers ---
CREATE CONSTRAINT cve_id IF NOT EXISTS
  FOR (c:CVE) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT license_name IF NOT EXISTS
  FOR (l:License) REQUIRE l.name IS UNIQUE;

CREATE CONSTRAINT bundle_id IF NOT EXISTS
  FOR (b:Bundle) REQUIRE b.id IS UNIQUE;

CREATE CONSTRAINT project_id IF NOT EXISTS
  FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT crashcause_sig IF NOT EXISTS
  FOR (c:CrashCause) REQUIRE (c.category, c.signature) IS UNIQUE;

// --- Indexes ---
CREATE INDEX version_library IF NOT EXISTS
  FOR (v:Version) ON (v.library);

CREATE INDEX cve_severity IF NOT EXISTS
  FOR (c:CVE) ON (c.severity);
