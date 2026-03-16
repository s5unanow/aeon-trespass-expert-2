"""Tests for config loading and validation."""

from pathlib import Path

import pytest

from aeon_reader_pipeline.config.loader import (
    load_all_document_configs,
    load_catalog,
    load_document_config,
    load_glossary_pack,
    load_model_profile,
    load_patch_set,
    load_rule_profile,
    load_symbol_pack,
)
from aeon_reader_pipeline.models.config_models import (
    CatalogConfig,
    DocumentConfig,
    GlossaryPack,
    ModelProfile,
    PatchSet,
    RuleProfile,
    SymbolPack,
)

CONFIGS_ROOT = Path(__file__).parent.parent.parent / "configs"


def test_load_catalog():
    catalog = load_catalog(CONFIGS_ROOT)
    assert isinstance(catalog, CatalogConfig)
    assert "aeon-trespass-core" in catalog.documents


def test_load_document_config():
    config = load_document_config(CONFIGS_ROOT, "aeon-trespass-core")
    assert isinstance(config, DocumentConfig)
    assert config.doc_id == "aeon-trespass-core"
    assert config.titles.en == "Aeon Trespass: Core Rulebook"
    assert config.source_locale == "en"
    assert config.target_locale == "ru"


def test_load_document_config_id_mismatch(tmp_path):
    bad_yaml = tmp_path / "documents" / "wrong-name.yaml"
    bad_yaml.parent.mkdir(parents=True)
    bad_yaml.write_text(
        "doc_id: actual-id\nslug: x\nsource_pdf: x\ntitles:\n  en: X\n  ru: X\n"
        "profiles:\n  rules: x\n  models: x\n  symbols: x\n  glossary: x\n"
        "build:\n  route_base: /x\n"
    )
    with pytest.raises(ValueError, match="doc_id mismatch"):
        load_document_config(tmp_path, "wrong-name")


def test_load_document_config_missing():
    with pytest.raises(FileNotFoundError):
        load_document_config(CONFIGS_ROOT, "nonexistent-doc")


def test_load_model_profile():
    profile = load_model_profile(CONFIGS_ROOT, "translate-default")
    assert isinstance(profile, ModelProfile)
    assert profile.profile_id == "translate-default"
    assert profile.provider == "gemini"


def test_load_rule_profile():
    profile = load_rule_profile(CONFIGS_ROOT, "rulebook-default")
    assert isinstance(profile, RuleProfile)
    assert profile.profile_id == "rulebook-default"
    assert profile.heading_detection.min_font_size_ratio > 0


def test_load_symbol_pack():
    pack = load_symbol_pack(CONFIGS_ROOT, "aeon-core")
    assert isinstance(pack, SymbolPack)
    assert pack.pack_id == "aeon-core"


def test_load_glossary_pack():
    pack = load_glossary_pack(CONFIGS_ROOT, "aeon-core")
    assert isinstance(pack, GlossaryPack)
    assert pack.pack_id == "aeon-core"


def test_load_patch_set():
    patch_set = load_patch_set(CONFIGS_ROOT, "aeon-trespass-core")
    assert isinstance(patch_set, PatchSet)
    assert patch_set.doc_id == "aeon-trespass-core"


def test_load_all_document_configs():
    configs = load_all_document_configs(CONFIGS_ROOT)
    assert len(configs) >= 1
    assert all(isinstance(c, DocumentConfig) for c in configs)
