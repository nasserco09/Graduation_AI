"""Join verified runtime parts without installing any third-party packages."""
import hashlib
import json
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def assemble(folder):
    manifest = json.loads((folder/'parts_manifest.json').read_text(encoding='utf-8'))
    name = manifest['archive']
    if Path(name).name != name or '/' in name or '\\' in name or ':' in name:
        raise ValueError('Invalid archive name')
    target = folder/name
    if target.exists():
        if target.stat().st_size == manifest['bytes'] and digest(target) == manifest['sha256']:
            print('The verified ZIP already exists. Extract it and run Setup_Runtime.cmd.')
            return target
        raise ValueError('An existing ZIP differs; use a new folder.')
    for number, entry in enumerate(manifest['parts'], 1):
        if entry['name'] != name+f'.part{number:03d}':
            raise ValueError('Invalid part name or order')
        part = folder/entry['name']
        if not part.is_file() or part.stat().st_size != entry['bytes'] or digest(part) != entry['sha256']:
            raise ValueError('Missing or changed part: '+entry['name'])
    temporary = target.with_suffix('.zip.assembling')
    whole = hashlib.sha256()
    with temporary.open('xb') as output:
        for entry in manifest['parts']:
            with (folder/entry['name']).open('rb') as source:
                for block in iter(lambda: source.read(4*1024*1024), b''):
                    output.write(block)
                    whole.update(block)
    if temporary.stat().st_size != manifest['bytes'] or whole.hexdigest() != manifest['sha256']:
        raise ValueError('Final ZIP checksum mismatch; the partial result was preserved.')
    temporary.rename(target)
    print('Verified ZIP ready. Extract it, then run Setup_Runtime.cmd and Start_Demo.cmd.')
    return target


if __name__ == '__main__':
    try:
        assemble(Path(__file__).resolve().parent)
    except (OSError, ValueError, KeyError) as error:
        print('Assembly failed: '+str(error))
        raise SystemExit(1)
