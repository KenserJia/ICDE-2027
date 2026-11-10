"""Command-line entry point for artifact reproduction."""
from pathlib import Path
import argparse, json, urllib.request
from .integrity import verify, install_raw
from .runner import catalog, write, workspace, execute, run, legacy_figures

def main(argv=None):
    p = argparse.ArgumentParser(description='MT-Memory current-manuscript reproducibility artifact')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    v = sub.add_parser('verify')
    v.add_argument('--full', action='store_true')
    r = sub.add_parser('run')
    r.add_argument('experiment', choices=[x['id'] for x in catalog()])
    r.add_argument('--output', type=Path, required=True)
    for name in ['smoke', 'tables', 'figures', 'prepare-data', 'audit-raw']:
        x = sub.add_parser(name)
        x.add_argument('--output', type=Path, required=True)
    x = sub.add_parser('install-raw')
    x.add_argument('--archive', type=Path, required=True)
    x = sub.add_parser('fetch-raw')
    x.add_argument('--url', required=True)
    x.add_argument('--download-to', type=Path, required=True)
    args = p.parse_args(argv)
    if args.command == 'list':
        for x in catalog():
            print(f"{x['id']:24s} {','.join(x['rqs']):14s} {x['title']}")
        return
    if args.command == 'verify':
        result = verify(args.full)
    elif args.command == 'run':
        result = run(args.experiment, args.output)
    elif args.command == 'prepare-data':
        from .prepare import prepare
        result = prepare(args.output)
    elif args.command == 'tables':
        from .current import tables
        result = tables(args.output)
    elif args.command == 'smoke':
        from .current import smoke
        result = smoke(args.output)
    elif args.command == 'figures':
        from .current import figures
        result = figures(args.output)
    elif args.command == 'audit-raw':
        from .current import audit_raw
        result = audit_raw(args.output)
    elif args.command == 'install-raw':
        result = install_raw(args.archive)
    else:
        if not args.url.startswith('https://'):
            raise ValueError('use an HTTPS Release asset URL')
        if args.download_to.exists():
            raise FileExistsError(args.download_to)
        args.download_to.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(args.url, timeout=120) as source, args.download_to.open('wb') as target:
            shutil.copyfileobj(source, target)
        result = install_raw(args.download_to)
    print(json.dumps(result, indent=2))
