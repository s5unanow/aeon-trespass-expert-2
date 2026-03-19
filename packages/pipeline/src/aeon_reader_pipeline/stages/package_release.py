"""Stage 14 — package final release archive with version metadata.

The package stage does not decide acceptance — it enforces it.
If QA has not accepted the run, packaging records the rejection and skips
the release assembly.

When QA is accepted, this stage creates a tar.gz archive containing the
exported site bundle and release manifest.
"""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

from aeon_reader_pipeline.models.qa_models import QASummary
from aeon_reader_pipeline.models.release_models import (
    ReleaseDocEntry,
    ReleaseManifest,
)
from aeon_reader_pipeline.models.site_bundle_models import SiteBundleManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.ids import content_fingerprint

STAGE_NAME = "package_release"
STAGE_VERSION = "2.0.0"


def _generate_release_id(run_id: str, doc_id: str) -> str:
    """Generate a deterministic release ID from run and doc."""
    return f"rel-{content_fingerprint(f'{run_id}:{doc_id}')[:12]}"


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _create_release_archive(
    ctx: StageContext,
    release_id: str,
    release_manifest: ReleaseManifest,
) -> tuple[Path, int, str]:
    """Create a tar.gz archive of the exported bundle and manifest.

    Returns (archive_path, size_bytes, sha256).
    """
    from aeon_reader_pipeline.io.json_io import write_json

    stage_dir = ctx.artifact_store.ensure_stage_dir(ctx.run_id, ctx.doc_id, STAGE_NAME)
    archive_name = f"release-{release_id}.tar.gz"
    archive_path = stage_dir / archive_name

    # Source bundle from export stage
    export_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "export_site_bundle")
    bundle_dir = export_dir / "site_bundle" / ctx.doc_id

    # Write release manifest to a temp location for inclusion
    manifest_path = stage_dir / "release_manifest.json"
    write_json(manifest_path, release_manifest)

    with tarfile.open(archive_path, "w:gz") as tar:
        # Add bundle contents under <doc_id>/
        if bundle_dir.exists():
            for item in sorted(bundle_dir.rglob("*")):
                if item.is_file():
                    arcname = f"{ctx.doc_id}/{item.relative_to(bundle_dir)}"
                    tar.add(item, arcname=arcname)

        # Add release manifest at root
        tar.add(manifest_path, arcname="release_manifest.json")

    size_bytes = archive_path.stat().st_size
    sha256 = _sha256_file(archive_path)

    return archive_path, size_bytes, sha256


@register_stage
class PackageReleaseStage(BaseStage):
    """Package accepted artifacts into a release archive."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Package release with acceptance gating"

    def execute(self, ctx: StageContext) -> None:
        # Read bundle manifest
        bundle_manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{ctx.doc_id}/bundle_manifest.json",
            SiteBundleManifest,
        )

        # Read QA summary
        qa_accepted = True
        rejection_reasons: list[str] = []
        try:
            qa_summary = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "evaluate_qa",
                "summary.json",
                QASummary,
            )
            qa_accepted = qa_summary.accepted
            rejection_reasons = list(qa_summary.rejection_reasons)
        except FileNotFoundError:
            ctx.logger.warning("qa_summary_not_found_for_release")

        release_id = _generate_release_id(ctx.run_id, ctx.doc_id)

        ctx.logger.info(
            "packaging_release",
            release_id=release_id,
            qa_accepted=qa_accepted,
        )

        doc_entry = ReleaseDocEntry(
            doc_id=ctx.doc_id,
            page_count=bundle_manifest.page_count,
            qa_accepted=qa_accepted,
            translation_coverage=bundle_manifest.translation_coverage,
        )

        release_manifest = ReleaseManifest(
            release_id=release_id,
            run_id=ctx.run_id,
            documents=[doc_entry],
            total_documents=1,
            all_accepted=qa_accepted,
            rejection_reasons=rejection_reasons,
            stage_version=STAGE_VERSION,
        )

        if qa_accepted:
            archive_path, size_bytes, sha256 = _create_release_archive(
                ctx, release_id, release_manifest
            )
            release_manifest.artifact_path = str(archive_path.name)
            release_manifest.artifact_size_bytes = size_bytes
            release_manifest.artifact_sha256 = sha256

            ctx.logger.info(
                "release_packaged",
                release_id=release_id,
                archive=archive_path.name,
                size_bytes=size_bytes,
            )
        else:
            ctx.logger.warning(
                "release_rejected",
                release_id=release_id,
                reasons=rejection_reasons,
            )

        # Write final manifest (may be updated with artifact info)
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "release_manifest.json",
            release_manifest,
        )
