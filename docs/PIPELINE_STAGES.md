# Pipeline stages (16-stage order)

Canonical order defined in `stage_framework/registry.py` (single source of truth).

```
00_resolve_run → 01_ingest_source → 02_extract_primitives → 02a_collect_evidence → 02b_resolve_page_ir →
03_normalize_layout → 04_resolve_assets_symbols → 05_plan_translation → 06_translate_units →
07_merge_localization → 08_enrich_content → 09_evaluate_qa → 11_export_site_bundle →
12_build_reader → 13_index_search → 14_package_release
```

Stages 02a and 02b are Architecture 3 only (`architecture: "v3"`) — they skip automatically on v2 (default).

Stage implementations go in `packages/pipeline/src/aeon_reader_pipeline/stages/`.
