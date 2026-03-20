"""Validate committed site-bundle fixtures against checked-in JSON Schema.

Ensures that every fixture manifest, page, navigation tree, and catalog
in tests/fixtures/site-bundles/ satisfies the public contract and
round-trips through the authoritative Pydantic models.

This test runs without network access and is part of contract verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from aeon_reader_pipeline.models.enrich_models import NavigationTree
from aeon_reader_pipeline.models.site_bundle_models import (
    BundlePage,
    CatalogManifest,
    SiteBundleManifest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "jsonschema"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "site-bundles"

# Schema name → file mapping
SCHEMAS: dict[str, Path] = {
    "SiteBundleManifest": SCHEMA_DIR / "SiteBundleManifest.json",
    "BundlePage": SCHEMA_DIR / "BundlePage.json",
    "NavigationTree": SCHEMA_DIR / "NavigationTree.json",
    "CatalogManifest": SCHEMA_DIR / "CatalogManifest.json",
}


def _load_schema(name: str) -> dict[str, Any]:
    path = SCHEMAS[name]
    assert path.exists(), f"Schema file missing: {path}"
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _load_json(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _validate(instance: dict[str, Any], schema_name: str) -> None:
    schema = _load_schema(schema_name)
    jsonschema.validate(instance=instance, schema=schema)


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _discover_doc_dirs() -> list[Path]:
    """Return all document directories under the fixture root."""
    return sorted(
        p for p in FIXTURE_ROOT.iterdir() if p.is_dir() and (p / "bundle_manifest.json").exists()
    )


def _discover_page_files(doc_dir: Path) -> list[Path]:
    pages_dir = doc_dir / "pages"
    if not pages_dir.exists():
        return []
    return sorted(pages_dir.glob("p*.json"))


# Collect parametrize IDs
_doc_dirs = _discover_doc_dirs()
_doc_ids = [d.name for d in _doc_dirs]
_page_params: list[tuple[Path, str]] = []
for _d in _doc_dirs:
    for _p in _discover_page_files(_d):
        _page_params.append((_p, f"{_d.name}/{_p.name}"))


# ---------------------------------------------------------------------------
# Schema validation: manifests
# ---------------------------------------------------------------------------


class TestManifestSchemaValidation:
    """Validate every committed bundle_manifest.json against SiteBundleManifest schema."""

    @pytest.mark.parametrize("doc_dir", _doc_dirs, ids=_doc_ids)
    def test_manifest_validates_against_schema(self, doc_dir: Path) -> None:
        data = _load_json(doc_dir / "bundle_manifest.json")
        _validate(data, "SiteBundleManifest")

    @pytest.mark.parametrize("doc_dir", _doc_dirs, ids=_doc_ids)
    def test_manifest_round_trips_through_pydantic(self, doc_dir: Path) -> None:
        data = _load_json(doc_dir / "bundle_manifest.json")
        model = SiteBundleManifest.model_validate(data)
        reserialized = model.model_dump(mode="json")
        _validate(reserialized, "SiteBundleManifest")


# ---------------------------------------------------------------------------
# Schema validation: pages
# ---------------------------------------------------------------------------


class TestPageSchemaValidation:
    """Validate every committed page JSON against BundlePage schema."""

    @pytest.mark.parametrize(
        "page_path", [p for p, _ in _page_params], ids=[i for _, i in _page_params]
    )
    def test_page_validates_against_schema(self, page_path: Path) -> None:
        data = _load_json(page_path)
        _validate(data, "BundlePage")

    @pytest.mark.parametrize(
        "page_path", [p for p, _ in _page_params], ids=[i for _, i in _page_params]
    )
    def test_page_round_trips_through_pydantic(self, page_path: Path) -> None:
        data = _load_json(page_path)
        model = BundlePage.model_validate(data)
        reserialized = model.model_dump(mode="json")
        _validate(reserialized, "BundlePage")


# ---------------------------------------------------------------------------
# Schema validation: navigation
# ---------------------------------------------------------------------------


class TestNavigationSchemaValidation:
    """Validate every committed navigation.json against NavigationTree schema."""

    @pytest.mark.parametrize("doc_dir", _doc_dirs, ids=_doc_ids)
    def test_navigation_validates_against_schema(self, doc_dir: Path) -> None:
        nav_path = doc_dir / "navigation.json"
        if not nav_path.exists():
            pytest.skip("No navigation.json in fixture")
        data = _load_json(nav_path)
        _validate(data, "NavigationTree")

    @pytest.mark.parametrize("doc_dir", _doc_dirs, ids=_doc_ids)
    def test_navigation_round_trips_through_pydantic(self, doc_dir: Path) -> None:
        nav_path = doc_dir / "navigation.json"
        if not nav_path.exists():
            pytest.skip("No navigation.json in fixture")
        data = _load_json(nav_path)
        model = NavigationTree.model_validate(data)
        reserialized = model.model_dump(mode="json")
        _validate(reserialized, "NavigationTree")


# ---------------------------------------------------------------------------
# Schema validation: catalog
# ---------------------------------------------------------------------------


class TestCatalogSchemaValidation:
    """Validate the committed catalog.json against CatalogManifest schema."""

    def test_catalog_validates_against_schema(self) -> None:
        catalog_path = FIXTURE_ROOT / "catalog.json"
        assert catalog_path.exists(), "catalog.json fixture missing"
        data = _load_json(catalog_path)
        _validate(data, "CatalogManifest")

    def test_catalog_round_trips_through_pydantic(self) -> None:
        catalog_path = FIXTURE_ROOT / "catalog.json"
        assert catalog_path.exists(), "catalog.json fixture missing"
        data = _load_json(catalog_path)
        model = CatalogManifest.model_validate(data)
        reserialized = model.model_dump(mode="json")
        _validate(reserialized, "CatalogManifest")


# ---------------------------------------------------------------------------
# Negative tests: prove the gate catches contract drift
# ---------------------------------------------------------------------------


class TestSchemaRejectsMalformedFixtures:
    """Verify that the schema gate catches missing required fields."""

    def test_manifest_missing_run_id_rejected(self) -> None:
        payload = {"doc_id": "test", "page_count": 1, "title_en": "Test"}
        with pytest.raises(jsonschema.ValidationError, match="run_id"):
            _validate(payload, "SiteBundleManifest")

    def test_manifest_missing_doc_id_rejected(self) -> None:
        payload = {"run_id": "r1", "page_count": 1, "title_en": "Test"}
        with pytest.raises(jsonschema.ValidationError, match="doc_id"):
            _validate(payload, "SiteBundleManifest")

    def test_page_missing_doc_id_rejected(self) -> None:
        payload = {"page_number": 1, "width_pt": 595.0, "height_pt": 842.0}
        with pytest.raises(jsonschema.ValidationError, match="doc_id"):
            _validate(payload, "BundlePage")

    def test_page_missing_dimensions_rejected(self) -> None:
        payload = {"page_number": 1, "doc_id": "test"}
        with pytest.raises(jsonschema.ValidationError, match="width_pt"):
            _validate(payload, "BundlePage")

    def test_page_invalid_render_mode_rejected(self) -> None:
        payload = {
            "page_number": 1,
            "doc_id": "test",
            "width_pt": 595.0,
            "height_pt": 842.0,
            "render_mode": "invalid",
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate(payload, "BundlePage")

    def test_navigation_missing_doc_id_rejected(self) -> None:
        payload: dict[str, Any] = {"entries": []}
        with pytest.raises(jsonschema.ValidationError, match="doc_id"):
            _validate(payload, "NavigationTree")

    def test_nav_entry_missing_required_fields_rejected(self) -> None:
        payload = {
            "doc_id": "test",
            "entries": [{"anchor_id": "a1"}],
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate(payload, "NavigationTree")

    def test_catalog_entry_missing_slug_rejected(self) -> None:
        payload = {
            "documents": [{"doc_id": "test", "title_en": "Test"}],
        }
        with pytest.raises(jsonschema.ValidationError, match="slug"):
            _validate(payload, "CatalogManifest")
