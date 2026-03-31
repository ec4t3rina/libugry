import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


class Sandbox:
    def install(self, library: str, version: str) -> dict:
        tmpdir = tempfile.mkdtemp(prefix="libugry_")
        try:
            venv_dir = Path(tmpdir) / "venv"
            venv.create(str(venv_dir), with_pip=True)

            pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
            result = subprocess.run(
                [str(pip), "install", f"{library}=={version}", "--quiet"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            log = (result.stdout + result.stderr).strip()
            status = "SUCCESS" if result.returncode == 0 else "CRASH"
            return {"status": status, "log": log or f"pip exited {result.returncode}"}
        except subprocess.TimeoutExpired:
            return {"status": "CRASH", "log": "Installation timed out after 120s"}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
