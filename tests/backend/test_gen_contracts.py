"""Tests for contract generation: Python → JSON Schema → TypeScript."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
JSONSCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "jsonschema"
TS_GENERATED = (
    REPO_ROOT / "packages" / "contracts" / "typescript" / "src" / "generated" / "site-bundle.ts"
)

# Type alias for the contract spec fixture return type
ContractSpec = tuple[
    list[str],
    dict[str, list[str]],
    list[tuple[str, list[str], list[str]]],
]


def _load_gen_module() -> Any:
    """Import gen_contracts module dynamically."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen_contracts", REPO_ROOT / "scripts" / "gen_contracts.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def contract_spec() -> ContractSpec:
    """Load contract spec constants from gen_contracts."""
    mod = _load_gen_module()
    model_names: list[str] = [m.__name__ for m in mod._EXPORT_MODELS]
    return model_names, mod.UNION_TYPES, mod._TS_SECTIONS


class TestJsonSchemaFiles:
    def test_all_schema_files_exist(self, contract_spec: ContractSpec) -> None:
        """Every exported model has a corresponding JSON Schema file."""
        model_names, _, _ = contract_spec
        for name in model_names:
            path = JSONSCHEMA_DIR / f"{name}.json"
            assert path.exists(), f"Missing JSON Schema: {path}"

    def test_schemas_are_valid_json(self) -> None:
        """All JSON Schema files must be parseable."""
        for path in sorted(JSONSCHEMA_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, dict), f"{path.name} not a JSON object"

    def test_no_extra_schema_files(self, contract_spec: ContractSpec) -> None:
        """No orphaned JSON Schema files beyond the export list."""
        model_names, _, _ = contract_spec
        expected = {f"{n}.json" for n in model_names}
        actual = {p.name for p in JSONSCHEMA_DIR.glob("*.json")}
        extra = actual - expected
        assert not extra, f"Unexpected JSON Schema files: {extra}"

    def test_schemas_have_title(self) -> None:
        """Each schema should have a title matching its filename."""
        for path in sorted(JSONSCHEMA_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            expected_name = path.stem
            if "$ref" in data:
                ref_name = data["$ref"].split("/")[-1]
                assert ref_name == expected_name, (
                    f"{path.name}: $ref points to {ref_name}, expected {expected_name}"
                )
            else:
                assert data.get("title") == expected_name, (
                    f"{path.name}: title is {data.get('title')!r}, expected {expected_name!r}"
                )


class TestTypescriptGeneration:
    def test_generated_file_exists(self) -> None:
        assert TS_GENERATED.exists(), f"Missing: {TS_GENERATED}"

    def test_header_references_json_schema(self) -> None:
        """Generated TS declares JSON Schema as the source of truth."""
        content = TS_GENERATED.read_text(encoding="utf-8")
        assert "generated from JSON Schema" in content
        assert "packages/contracts/jsonschema" in content

    def test_all_interfaces_present(self, contract_spec: ContractSpec) -> None:
        """Every exported model appears as a TS interface."""
        _, _, ts_sections = contract_spec
        content = TS_GENERATED.read_text(encoding="utf-8")
        for _header, model_names, _unions in ts_sections:
            for name in model_names:
                assert f"export interface {name}" in content, f"Missing interface: {name}"

    def test_union_types_present(self, contract_spec: ContractSpec) -> None:
        """Union type aliases must appear in the TS file."""
        _, union_types, _ = contract_spec
        content = TS_GENERATED.read_text(encoding="utf-8")
        for alias in union_types:
            assert f"export type {alias}" in content, f"Missing union type: {alias}"

    def test_ts_sections_cover_all_models(self, contract_spec: ContractSpec) -> None:
        """TS sections cover exactly the exported model list."""
        model_names, _, ts_sections = contract_spec
        section_models: list[str] = []
        for _header, names, _unions in ts_sections:
            section_models.extend(names)
        assert set(section_models) == set(model_names), (
            f"Mismatch: {set(section_models)} != {set(model_names)}"
        )


class TestContractIdempotency:
    def test_generation_is_idempotent(self) -> None:
        """Running Phase 2 again produces identical output."""
        mod = _load_gen_module()
        before = TS_GENERATED.read_text(encoding="utf-8")
        mod.generate_typescript()
        after = TS_GENERATED.read_text(encoding="utf-8")
        assert before == after, "TS generation is not idempotent"
