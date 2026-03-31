import platform
import sys


def detect() -> dict:
    system = platform.system().lower()
    os_map = {"darwin": "macos", "linux": "linux", "windows": "windows"}
    os_name = os_map.get(system, system)

    machine = platform.machine().lower()
    arch_map = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}
    arch = arch_map.get(machine, machine)

    python = f"{sys.version_info.major}.{sys.version_info.minor}"

    return {"os": os_name, "arch": arch, "python": python}
