"""Single Source of Truth (SSOT) for Meikova Loop Versioning.

All project files and runtime components synchronize their version from this file:
- package.json
- installer.iss
- loopbox/__init__.py
- loopbox/config.py
- loopbox/tray.py
- web/index.html

Usage CLI:
    python version.py                  # Prints current version string
    python version.py --check          # Verifies version consistency across codebase
    python version.py --sync           # Propagates current version to all target files
    python version.py --bump patch     # Bumps patch (x.y.z -> x.y.z+1) and auto-syncs
    python version.py --bump minor     # Bumps minor (x.y.z -> x.y+1.0) and auto-syncs
    python version.py --bump major     # Bumps major (x.y.z -> x+1.0.0) and auto-syncs
    python version.py --set 1.0.15     # Sets explicit version and auto-syncs
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__version__ = "1.0.26"
VERSION_INFO = (1, 0, 26)
APP_NAME = "Meikova Loop"
APP_SLUG = "meikova-loop"
APP_ID = "com.meikova.loop"

ROOT = Path(__file__).resolve().parent


def get_version() -> str:
    """Returns the current application version."""
    return __version__


def get_version_info() -> Tuple[int, int, int]:
    """Returns the version tuple (major, minor, patch)."""
    return VERSION_INFO


def parse_semver(v_str: str) -> Tuple[int, int, int]:
    """Parses SemVer string x.y.z into integer tuple."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v_str.strip())
    if not m:
        raise ValueError(f"Invalid SemVer string: {v_str}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _update_file(path: Path, pattern: str, replacement: str) -> bool:
    """Replaces first regex match in file if needed."""
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, count=1)
    if count > 0 and new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return True
    return False


def sync_all(version_str: Optional[str] = None) -> Dict[str, str]:
    """Propagates SSOT version across all registered project files."""
    v = version_str or __version__
    parse_semver(v)  # validate format

    results = {}

    # 1. Update version.py itself if an explicit version was passed
    if version_str and version_str != __version__:
        major, minor, patch = parse_semver(v)
        v_file = ROOT / "version.py"
        content = v_file.read_text(encoding="utf-8")
        content = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{v}"', content, count=1)
        content = re.sub(r'VERSION_INFO = \(\d+, \d+, \d+\)', f'VERSION_INFO = ({major}, {minor}, {patch})', content, count=1)
        v_file.write_text(content, encoding="utf-8")
        results["version.py"] = f"Updated to {v}"

    # 2. package.json
    pkg_file = ROOT / "package.json"
    if pkg_file.exists():
        ch = _update_file(pkg_file, r'"version":\s*"[^"]+"', f'"version": "{v}"')
        results["package.json"] = f"Synced to {v}" if ch else f"Up to date ({v})"

    # 3. installer.iss
    iss_file = ROOT / "installer.iss"
    if iss_file.exists():
        ch = _update_file(iss_file, r'#define MyAppVersion\s+"[^"]+"', f'#define MyAppVersion "{v}"')
        results["installer.iss"] = f"Synced to {v}" if ch else f"Up to date ({v})"

    # 4. loopbox/__init__.py
    init_file = ROOT / "loopbox" / "__init__.py"
    if init_file.exists():
        content = init_file.read_text(encoding="utf-8")
        if "__version__" in content:
            ch = _update_file(init_file, r'__version__\s*=\s*"[^"]+"', f'__version__ = "{v}"')
        else:
            init_file.write_text(f'__version__ = "{v}"\n' + content, encoding="utf-8")
            ch = True
        results["loopbox/__init__.py"] = f"Synced to {v}" if ch else f"Up to date ({v})"

    # 5. loopbox/config.py
    cfg_file = ROOT / "loopbox" / "config.py"
    if cfg_file.exists():
        content = cfg_file.read_text(encoding="utf-8")
        if "APP_VERSION" in content:
            ch = _update_file(cfg_file, r'APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{v}"')
        else:
            pos = content.find("ROOT =")
            if pos != -1:
                content = content[:pos] + f'APP_VERSION = "{v}"\n' + content[pos:]
                cfg_file.write_text(content, encoding="utf-8")
                ch = True
            else:
                ch = False
        results["loopbox/config.py"] = f"Synced to {v}" if ch else f"Up to date ({v})"

    # 6. web/index.html meta tag and version badge
    html_file = ROOT / "web" / "index.html"
    if html_file.exists():
        c = html_file.read_text(encoding="utf-8")
        c2 = re.sub(r'<meta name="version" content="[^"]*"', f'<meta name="version" content="{v}"', c)
        c3 = re.sub(r'id="app-version-badge">v[^<]+<', f'id="app-version-badge">v{v}<', c2)
        if c3 != c:
            html_file.write_text(c3, encoding="utf-8")
            results["web/index.html"] = f"Synced to {v}"
        else:
            results["web/index.html"] = f"Up to date ({v})"

    # 7. loopbox/tray.py (ensure dynamic reference)
    tray_file = ROOT / "loopbox" / "tray.py"
    if tray_file.exists():
        tc = tray_file.read_text(encoding="utf-8")
        if "Meikova Loop // v2.0" in tc:
            tc = tc.replace('"Meikova Loop // v2.0"', 'f"Meikova Loop // v{APP_VERSION}"')
            tray_file.write_text(tc, encoding="utf-8")
            results["loopbox/tray.py"] = f"Synced to dynamic APP_VERSION ({v})"
        else:
            results["loopbox/tray.py"] = f"Up to date (dynamic APP_VERSION)"

    return results


def check_sync() -> Tuple[bool, Dict[str, str]]:
    """Checks whether all files match the current SSOT version.
    Returns (all_ok, report_dict).
    """
    expected = __version__
    status = {}
    all_ok = True

    # package.json
    pkg_file = ROOT / "package.json"
    if pkg_file.exists():
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            act = data.get("version")
            status["package.json"] = act
            if act != expected:
                all_ok = False
        except Exception as e:
            status["package.json"] = f"Error: {e}"
            all_ok = False

    # installer.iss
    iss_file = ROOT / "installer.iss"
    if iss_file.exists():
        m = re.search(r'#define MyAppVersion\s+"([^"]+)"', iss_file.read_text(encoding="utf-8"))
        act = m.group(1) if m else "Not found"
        status["installer.iss"] = act
        if act != expected:
            all_ok = False

    # loopbox/__init__.py
    init_file = ROOT / "loopbox" / "__init__.py"
    if init_file.exists():
        m = re.search(r'__version__\s*=\s*"([^"]+)"', init_file.read_text(encoding="utf-8"))
        act = m.group(1) if m else "Not found"
        status["loopbox/__init__.py"] = act
        if act != expected:
            all_ok = False

    # loopbox/config.py
    cfg_file = ROOT / "loopbox" / "config.py"
    if cfg_file.exists():
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', cfg_file.read_text(encoding="utf-8"))
        act = m.group(1) if m else "Not found"
        status["loopbox/config.py"] = act
        if act != expected:
            all_ok = False

    # loopbox/tray.py
    tray_file = ROOT / "loopbox" / "tray.py"
    if tray_file.exists():
        c = tray_file.read_text(encoding="utf-8")
        if "Meikova Loop // v2.0" in c:
            status["loopbox/tray.py"] = "Hardcoded v2.0 detected"
            all_ok = False
        elif "APP_VERSION" in c and "Meikova Loop // v{APP_VERSION}" in c:
            status["loopbox/tray.py"] = f"{expected} (dynamic)"
        else:
            status["loopbox/tray.py"] = "Missing APP_VERSION reference"
            all_ok = False

    # web/index.html
    html_file = ROOT / "web" / "index.html"
    if html_file.exists():
        m = re.search(r'<meta name="version" content="([^"]*)"', html_file.read_text(encoding="utf-8"))
        act = m.group(1) if m else "Not found"
        status["web/index.html"] = act
        if act != expected:
            all_ok = False

    return all_ok, status


def bump_version(part: str = "patch") -> str:
    """Increments major, minor, or patch component, updates version.py and syncs."""
    major, minor, patch = VERSION_INFO
    part = part.lower().strip()
    if part == "patch":
        patch += 1
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"Unknown bump target: '{part}'. Choose from 'major', 'minor', 'patch'.")

    new_v = f"{major}.{minor}.{patch}"
    sync_all(new_v)
    return new_v


def main():
    parser = argparse.ArgumentParser(description="Meikova Loop Centralized Version Manager")
    parser.add_argument("--bump", choices=["patch", "minor", "major"], help="Bump version part and sync all files")
    parser.add_argument("--set", dest="set_version", help="Explicitly set version (x.y.z) and sync all files")
    parser.add_argument("--sync", action="store_true", help="Synchronize all files to current version.py SSOT")
    parser.add_argument("--check", action="store_true", help="Check version consistency across codebase")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()

    if args.bump:
        new_v = bump_version(args.bump)
        if args.json:
            print(json.dumps({"version": new_v, "bumped": args.bump, "ok": True}))
        else:
            print(f"Bumped [{args.bump}] to v{new_v} and synchronized all files.")
        return

    if args.set_version:
        v = args.set_version.strip().lstrip("v")
        sync_all(v)
        if args.json:
            print(json.dumps({"version": v, "ok": True}))
        else:
            print(f"Set version to v{v} and synchronized all files.")
        return

    if args.sync:
        res = sync_all()
        if args.json:
            print(json.dumps({"version": __version__, "results": res, "ok": True}))
        else:
            print(f"Synchronized all files to SSOT version v{__version__}:")
            for k, v in res.items():
                print(f"  - {k}: {v}")
        return

    if args.check:
        is_ok, report = check_sync()
        if args.json:
            print(json.dumps({"version": __version__, "in_sync": is_ok, "files": report}))
        else:
            print(f"SSOT Version: v{__version__}")
            for fname, fver in report.items():
                status = "OK" if fver == __version__ or str(fver).startswith(__version__) else "MISMATCH"
                print(f"  [{status:8}] {fname:<25}: {fver}")
            if not is_ok:
                print("\n[WARNING] Some files are out of sync. Run 'python version.py --sync' to fix.")
                sys.exit(1)
            else:
                print("\n[PASS] All project files are in 100% version synchronization.")
        return

    # Default: print version string
    if args.json:
        print(json.dumps({"version": __version__, "name": APP_NAME, "id": APP_ID}))
    else:
        print(__version__)


if __name__ == "__main__":
    main()
