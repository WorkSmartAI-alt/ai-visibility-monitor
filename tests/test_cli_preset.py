"""CLI tests for the --preset flag and avm presets subcommand."""
from __future__ import annotations

import json
import sys
from io import StringIO

import pytest

from avm.cli import main


def _run(argv: list[str]) -> tuple[int, str]:
    """Run main(argv) and capture stdout."""
    old_stdout = sys.stdout
    sys.stdout = buf = StringIO()
    try:
        code = main(argv)
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 0
    finally:
        sys.stdout = old_stdout
    return code, buf.getvalue()


# ---------------------------------------------------------------------------
# --dry-run with --preset
# ---------------------------------------------------------------------------

def test_dry_run_preset_loads_21_queries(capsys):
    code = main([
        "--preset", "work-smart-mid-market",
        "--dry-run",
        "--no-wizard",
        "--skip-preflight",
    ])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert code == 0
    assert "21 queries" in output
    assert "work-smart-mid-market" in output


def test_dry_run_preset_shows_tiers(capsys):
    main([
        "--preset", "work-smart-mid-market",
        "--dry-run",
        "--no-wizard",
        "--skip-preflight",
    ])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    # Tier labels should appear in the dry-run output
    assert "alpha" in output or "beta" in output


def test_dry_run_unknown_preset_exits_nonzero(capsys):
    code = main([
        "--preset", "nonexistent-preset",
        "--dry-run",
        "--no-wizard",
        "--skip-preflight",
    ])
    assert code != 0
    captured = capsys.readouterr()
    assert "not found" in (captured.out + captured.err).lower()


# ---------------------------------------------------------------------------
# avm presets list
# ---------------------------------------------------------------------------

def test_presets_list_exits_zero(capsys):
    code = main(["--skip-preflight", "presets", "list"])
    assert code == 0


def test_presets_list_shows_work_smart(capsys):
    main(["--skip-preflight", "presets", "list"])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "work-smart-mid-market" in output


def test_presets_list_shows_query_count(capsys):
    main(["--skip-preflight", "presets", "list"])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "21" in output


# ---------------------------------------------------------------------------
# avm presets show
# ---------------------------------------------------------------------------

def test_presets_show_exits_zero(capsys):
    code = main(["--skip-preflight", "presets", "show", "work-smart-mid-market"])
    assert code == 0


def test_presets_show_contains_queries(capsys):
    main(["--skip-preflight", "presets", "show", "work-smart-mid-market"])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "fractional" in output.lower() or "How much" in output


def test_presets_show_unknown_exits_nonzero(capsys):
    code = main(["--skip-preflight", "presets", "show", "nonexistent"])
    assert code != 0
