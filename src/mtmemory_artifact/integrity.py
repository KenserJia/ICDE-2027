"""Repository and raw-archive integrity checks."""
from pathlib import Path
import json, shutil, tarfile
from .io import ROOT, sha256, safe_path

def verify(full=False, root=ROOT):
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    bad = []
    for name, info in manifest['files'].items():
        p = safe_path(root, name)
        if not p.exists() or sha256(p) != info['sha256']:
            bad.append(name)
    raw = json.loads((root / 'evidence/RAW_MANIFEST.json').read_text())
    installed = 0
    for x in raw['files']:
        p = root / x['path']
        if p.exists():
            installed += 1
            if sha256(p) != x['sha256']:
                bad.append(x['path'])
        elif full:
            bad.append(x['path'])
    source_checks = 0
    for name in ['QUALITY_PROTOCOL.json', 'PILOT_PROTOCOL.json', 'LOAD_PROTOCOL.json']:
        from .io import load_json
        protocol = load_json('results/cert_age_slo_20261110/' + name, root)
        for path, digest in protocol['source'].items():
            source_checks += 1
            if sha256(root / path) != digest:
                bad.append('frozen-source:' + path)
    result = dict(passed=not bad, frozen_source_checks=source_checks, repository_files=len(manifest['files']), raw_files_installed=installed, raw_files_available=len(raw['files']), mismatches=bad)
    if bad:
        raise RuntimeError(json.dumps(result))
    return result

def install_raw(archive):
    meta = json.loads((ROOT / 'evidence/RAW_MANIFEST.json').read_text())
    p = Path(archive)
    if sha256(p) != meta['sha256']:
        raise ValueError('raw archive checksum mismatch')
    expected = {x['path']: x for x in meta['files']}
    with tarfile.open(p, 'r:gz') as t:
        members = t.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != set(expected):
            raise ValueError('raw archive inventory differs')
        for m in members:
            dst = safe_path(ROOT, m.name)
            if not m.isfile():
                raise ValueError('raw archive contains a nonregular member')
            if dst.exists() and sha256(dst) != expected[m.name]['sha256']:
                raise FileExistsError(dst)
        for m in members:
            dst = safe_path(ROOT, m.name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                with t.extractfile(m) as source, dst.open('wb') as target:
                    shutil.copyfileobj(source, target)
            if sha256(dst) != expected[m.name]['sha256']:
                raise ValueError('raw record checksum mismatch')
    return dict(passed=True, raw_files=len(expected))
