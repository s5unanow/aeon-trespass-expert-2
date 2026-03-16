"""YAML config loaders and validators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from aeon_reader_pipeline.models.config_models import (
    CatalogConfig,
    DocumentConfig,
    GlossaryPack,
    ModelProfile,
    PatchSet,
    RuleProfile,
    SymbolPack,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Config file is empty: {path}")
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def _load_model[T: BaseModel](path: Path, model_cls: type[T]) -> T:
    """Load a YAML file into a Pydantic model."""
    data = _load_yaml(path)
    return model_cls.model_validate(data)


def load_catalog(configs_root: Path) -> CatalogConfig:
    """Load the document catalog."""
    return _load_model(configs_root / "catalog.yaml", CatalogConfig)


def load_document_config(configs_root: Path, doc_id: str) -> DocumentConfig:
    """Load a single document configuration."""
    path = configs_root / "documents" / f"{doc_id}.yaml"
    config = _load_model(path, DocumentConfig)
    if config.doc_id != doc_id:
        raise ValueError(
            f"doc_id mismatch: filename says '{doc_id}' but file contains '{config.doc_id}'"
        )
    return config


def load_model_profile(configs_root: Path, profile_id: str) -> ModelProfile:
    """Load a model profile."""
    return _load_model(configs_root / "model-profiles" / f"{profile_id}.yaml", ModelProfile)


def load_rule_profile(configs_root: Path, profile_id: str) -> RuleProfile:
    """Load a rule profile."""
    return _load_model(configs_root / "rule-profiles" / f"{profile_id}.yaml", RuleProfile)


def load_symbol_pack(configs_root: Path, pack_id: str) -> SymbolPack:
    """Load a symbol pack."""
    return _load_model(configs_root / "symbol-packs" / f"{pack_id}.yaml", SymbolPack)


def load_glossary_pack(configs_root: Path, pack_id: str) -> GlossaryPack:
    """Load a glossary pack."""
    return _load_model(configs_root / "glossary-packs" / f"{pack_id}.yaml", GlossaryPack)


def load_patch_set(configs_root: Path, patch_id: str) -> PatchSet:
    """Load a patch/override set."""
    return _load_model(configs_root / "overrides" / f"{patch_id}.yaml", PatchSet)


def load_all_document_configs(configs_root: Path) -> list[DocumentConfig]:
    """Load all document configs listed in the catalog."""
    catalog = load_catalog(configs_root)
    return [load_document_config(configs_root, doc_id) for doc_id in catalog.documents]
