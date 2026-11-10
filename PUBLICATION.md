# Public release v0.3.0 —2026-11-10

The default branch has been replaced with the current artifact tree. All previous tracked files absent from this snapshot are removed; earlier commits and releases remain available for provenance. Scientific core modules, frozen experiment drivers, data arrays and experimental records are unchanged from the validated local package. README, citation date and release metadata were updated for publication.

Download both attachments from https://github.com/KenserJia/ICDE-2027/releases/tag/v0.3.0 :

- `mt-memory-icde-artifact-20261110.zip`: code, three source/processed datasets, compact evidence and reproduction entry points.
- `mt-memory-raw-evidence-20261110.tar.gz`: complete7,131binary evidence records. It must match `evidence/RAW_MANIFEST.json`.
- `RELEASE_FILES_20261110.sha256`: integrity hashes of the downloadable files.
- `ARTIFACT_AUDIT_20261110.md`: preparation changes and validation scope.

The raw archive is a Release asset, not part of Git history. Install it with `python reproduce.py install-raw --archive PATH`, then run `python reproduce.py verify --full` and `python reproduce.py audit-raw --output runs/raw-audit`.

The original v0.2.0 Release URL cited by the manuscript now links readers to this current release. Its historical assets/tag are preserved; its auto-generated source archive still corresponds to the old tag. The current explicitly dated artifact ZIP corresponds to v0.3.0. The earlier preparation/upload guides and validation reports describe their original stage; this file records subsequent publication. No new scientific performance run is implied by publication.
