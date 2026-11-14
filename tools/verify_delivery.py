"""Verify a submission's declared files without running models or changing data."""
from pathlib import Path
import argparse,hashlib,json

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def verify(folder):
    root=Path(folder).resolve()
    record=json.loads((root/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
    expected=set();errors=[]
    for item in record['files']:
        rel=Path(item['path'])
        path=(root/rel).resolve()
        if rel.is_absolute() or not path.is_relative_to(root):
            errors.append('Unsafe manifest path');continue
        if item['path'] in expected:errors.append('Duplicate manifest path')
        expected.add(item['path'])
        if not path.is_file():errors.append('Missing: '+item['path'])
        elif path.stat().st_size!=item['bytes'] or sha256(path)!=item['sha256']:
            errors.append('Changed: '+item['path'])
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}-{'DELIVERY_MANIFEST.json','SHA256SUMS.txt'}
    errors.extend('Extra: '+p for p in sorted(actual-expected))
    checksum_lines=['{}  {}'.format(f['sha256'],f['path']) for f in record['files']]
    if (root/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()!=checksum_lines:
        errors.append('SHA256SUMS.txt differs from manifest')
    return {'passed':not errors,'profile':record['profile'],'files':len(expected),'errors':errors,'integrity_only':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path,nargs='?',default=Path(__file__).resolve().parent)
    args=parser.parse_args();result=verify(args.folder)
    print(json.dumps(result,ensure_ascii=True,indent=2));raise SystemExit(0 if result['passed'] else 1)
