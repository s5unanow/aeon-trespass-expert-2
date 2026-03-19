"""Base models — intentionally minimal.

ArtifactEnvelope, Provenance, SourceSpanRef, and LlmCallRef were removed
in S5U-219 as dead abstractions. The pipeline uses raw Pydantic model
dumps with deterministic hashing (orjson + sorted keys) for artifact
identity, and StageManifest input_hashes / output_hashes for cache
invalidation. If full provenance tracking is needed later, reintroduce
it as a concrete feature, not a pre-built abstraction.
"""
