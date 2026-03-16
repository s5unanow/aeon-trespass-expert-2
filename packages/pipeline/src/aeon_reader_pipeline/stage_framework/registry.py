"""Stage registry — ordered collection of all pipeline stages."""

from __future__ import annotations

from aeon_reader_pipeline.stage_framework.base import BaseStage

# Canonical stage order
STAGE_ORDER: list[str] = [
    "resolve_run",
    "ingest_source",
    "extract_primitives",
    "normalize_layout",
    "resolve_assets_symbols",
    "plan_translation",
    "translate_units",
    "merge_localization",
    "enrich_content",
    "evaluate_qa",
    "apply_safe_fixes",
    "export_site_bundle",
    "build_reader",
    "index_search",
    "package_release",
]

_REGISTRY: dict[str, type[BaseStage]] = {}


def register_stage(stage_cls: type[BaseStage]) -> type[BaseStage]:
    """Register a stage class. Can be used as a decorator."""
    name = stage_cls.name
    if name in _REGISTRY:
        raise ValueError(f"Stage '{name}' is already registered")
    if name not in STAGE_ORDER:
        raise ValueError(f"Stage '{name}' is not in STAGE_ORDER")
    _REGISTRY[name] = stage_cls
    return stage_cls


def get_stage(name: str) -> BaseStage:
    """Get an instance of a registered stage by name."""
    if name not in _REGISTRY:
        raise KeyError(
            f"Stage '{name}' is not registered. Registered: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]()


def get_registered_stages() -> list[str]:
    """Get names of all registered stages in canonical order."""
    return [name for name in STAGE_ORDER if name in _REGISTRY]


def get_all_stages_ordered() -> list[str]:
    """Get all stage names in canonical order."""
    return list(STAGE_ORDER)


def filter_stages(
    from_stage: str | None = None,
    to_stage: str | None = None,
    only: list[str] | None = None,
) -> list[str]:
    """Filter and return stage names based on selection criteria."""
    if only is not None:
        for name in only:
            if name not in STAGE_ORDER:
                raise ValueError(f"Unknown stage: {name}")
        return [name for name in STAGE_ORDER if name in only]

    stages = list(STAGE_ORDER)
    if from_stage is not None:
        if from_stage not in STAGE_ORDER:
            raise ValueError(f"Unknown from_stage: {from_stage}")
        idx = stages.index(from_stage)
        stages = stages[idx:]
    if to_stage is not None:
        if to_stage not in STAGE_ORDER:
            raise ValueError(f"Unknown to_stage: {to_stage}")
        idx = stages.index(to_stage)
        stages = stages[: idx + 1]
    return stages
