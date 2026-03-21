# Pipeline stages (16-stage order)

```
00_resolve → 01_ingest → 02_extract → 02a_evidence → 02b_resolve_ir →
03_normalize → 04_resolve_assets → 05_plan_translation → 06_translate →
07_merge → 08_enrich → 09_evaluate_qa → 11_export → 12_build →
13_index → 14_release
```

Stages 02a and 02b are Architecture 3 only (`architecture: "v3"`) — they skip automatically on v2 (default).

Stage implementations go in `packages/pipeline/src/aeon_reader_pipeline/stages/`.
