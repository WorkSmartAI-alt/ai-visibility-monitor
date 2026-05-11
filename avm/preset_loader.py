"""Load, validate, and list AVM query presets.

Presets are YAML files stored in avm/presets/. Each preset bundles a named
set of buyer queries with tier and target-page metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


@dataclass
class Query:
    id: str
    text: str
    tier: str
    subtier: str
    target_page: str


@dataclass
class Preset:
    name: str
    slug: str
    description: str
    version: str
    last_updated: str
    maintainer: str
    queries: list[Query]
    tier_summary: dict[str, int]
    source_url: str = ""
    license: str = "MIT"


@dataclass
class PresetMetadata:
    name: str
    slug: str
    description: str
    version: str
    query_count: int
    tier_summary: dict[str, int]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _presets_dir() -> Path:
    """Return the path to the avm/presets/ package directory."""
    try:
        pkg = files("avm.presets")
        return Path(str(pkg))
    except Exception:
        return Path(__file__).parent / "presets"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required for preset support. "
            "Install it with: pip install pyyaml"
        ) from exc
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _validate(data: dict, path: Path) -> None:
    required = ("name", "slug", "description", "version", "queries")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(
            f"Preset {path.name} is missing required fields: {', '.join(missing)}"
        )
    if not isinstance(data["queries"], list) or len(data["queries"]) == 0:
        raise ValueError(f"Preset {path.name} has no queries.")
    for i, q in enumerate(data["queries"]):
        for field in ("id", "text", "tier", "target_page"):
            if field not in q:
                raise ValueError(
                    f"Preset {path.name}: query at index {i} missing field '{field}'"
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_preset(name: str) -> Preset:
    """Load and validate a preset by slug name.

    Args:
        name: Preset slug (e.g. "work-smart-mid-market"). The .yaml extension
              is added automatically.

    Returns:
        A validated Preset dataclass.

    Raises:
        FileNotFoundError: if the preset YAML does not exist.
        ValueError: if the YAML is missing required fields.
    """
    presets_dir = _presets_dir()
    path = presets_dir / f"{name}.yaml"
    if not path.exists():
        available = [p.stem for p in presets_dir.glob("*.yaml")]
        avail_str = ", ".join(sorted(available)) if available else "(none)"
        raise FileNotFoundError(
            f"Preset '{name}' not found in {presets_dir}. "
            f"Available presets: {avail_str}"
        )

    data = _load_yaml(path)
    _validate(data, path)

    queries = [
        Query(
            id=q["id"],
            text=q["text"],
            tier=q["tier"],
            subtier=q.get("subtier", ""),
            target_page=q.get("target_page", ""),
        )
        for q in data["queries"]
    ]

    return Preset(
        name=data["name"],
        slug=data["slug"],
        description=str(data.get("description", "")).strip(),
        version=str(data.get("version", "")),
        last_updated=str(data.get("last_updated", "")),
        maintainer=str(data.get("maintainer", "")),
        source_url=str(data.get("source_url", "")),
        license=str(data.get("license", "MIT")),
        queries=queries,
        tier_summary=data.get("tier_summary", {}),
    )


def list_presets() -> list[PresetMetadata]:
    """Scan the presets directory and return metadata for each preset.

    Returns a list sorted by preset name.
    """
    presets_dir = _presets_dir()
    results: list[PresetMetadata] = []

    for path in sorted(presets_dir.glob("*.yaml")):
        try:
            data = _load_yaml(path)
            _validate(data, path)
            results.append(PresetMetadata(
                name=data["name"],
                slug=data["slug"],
                description=str(data.get("description", "")).strip(),
                version=str(data.get("version", "")),
                query_count=len(data["queries"]),
                tier_summary=data.get("tier_summary", {}),
            ))
        except Exception:
            pass  # silently skip malformed files

    return results


def query_texts(name: str) -> list[str]:
    """Convenience wrapper: load a preset and return just the query strings."""
    preset = load_preset(name)
    return [q.text for q in preset.queries]
