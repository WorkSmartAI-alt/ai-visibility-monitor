from __future__ import annotations

import importlib.util
import subprocess
import sys

REQUIRED: list[tuple[str, str, str]] = [
    ("anthropic", "anthropic>=0.40.0", "run queries through Claude"),
    ("rich", "rich>=13.0", "colored terminal output"),
]

OPTIONAL: list[tuple[str, str, str]] = [
    ("googleapiclient", "google-api-python-client>=2.100.0", "pull Google Search Console data"),
    ("google.analytics.data", "google-analytics-data>=0.18.0", "pull GA4 data"),
]


def _is_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _prompt_install(name: str, reason: str) -> bool:
    print(f"\n  Required dependency missing: {name}")
    print(f"  This is needed to {reason}.")
    try:
        resp = input("  Install now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return resp in ("", "y", "yes")


def _install(pkg: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def check_dependencies(skip_optional: bool = True) -> None:
    missing = [(name, pkg, reason) for name, pkg, reason in REQUIRED if not _is_available(name)]
    if not missing:
        return

    any_skipped = False
    for name, pkg, reason in missing:
        if _prompt_install(name, reason):
            print(f"  Installing {name}...", flush=True)
            if _install(pkg):
                print(f"  ✓ {name} installed.")
            else:
                print(f"  ✗ Install failed. Run manually: pip install {pkg}", file=sys.stderr)
                if name == "anthropic":
                    sys.exit(1)
                any_skipped = True
        else:
            print(f"  Skipped. Install manually: pip install {pkg}")
            if name == "anthropic":
                print("  Cannot continue without anthropic. Exiting.", file=sys.stderr)
                sys.exit(1)
            any_skipped = True

    if not any_skipped:
        print()


def check_optional_dependency(import_name: str, pkg: str, feature: str) -> bool:
    if _is_available(import_name):
        return True
    print(f"\n  Optional dependency missing: {pkg}")
    print(f"  This is needed to {feature}.")
    try:
        resp = input("  Install now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if resp in ("", "y", "yes"):
        print(f"  Installing {pkg}...", flush=True)
        if _install(pkg):
            print(f"  ✓ {pkg} installed.")
            return True
        print(f"  ✗ Install failed. Run manually: pip install {pkg}", file=sys.stderr)
    return False
