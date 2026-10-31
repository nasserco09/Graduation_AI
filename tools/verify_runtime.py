"""Verify a clean runtime bundle using only the Python standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Invalid runtime path')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or '..' in parts.parts or parts.as_posix() != relative:
        raise ValueError('Unsafe runtime path: ' + relative)
    target = root.joinpath(*parts.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Runtime file leaves the project directory: ' + relative)
    return target


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def verify(root: Path, *, quick: bool = False) -> dict:
    manifest = json.loads((root / 'runtime_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('catalog_images') != 3068:
        raise ValueError('Unsupported runtime manifest')
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Empty runtime manifest')
    seen = set()
    image_count = 0
    for entry in entries:
        relative = entry['path']
        if relative in seen:
            raise ValueError('Duplicate runtime file: ' + relative)
        seen.add(relative)
        lower = relative.lower()
        if lower.endswith(('.db', '.db-wal', '.db-shm')) or any(
            part in {'.venv', '.idea', '.cache', '__pycache__', 'demo_store'}
            for part in PurePosixPath(lower).parts
        ):
            raise ValueError('Private or machine-specific file in runtime manifest')
        if lower.startswith('models/') and not lower.startswith((
            'models/siglip2_base/', 'models/sam2_base_plus/'
        )):
            raise ValueError('Unused model in runtime manifest')
        path = safe_file(root, relative)
        if not path.is_file() or path.stat().st_size != entry['bytes']:
            raise ValueError('Missing or changed runtime file: ' + relative)
        if not quick and digest(path) != entry['sha256']:
            raise ValueError('Runtime checksum mismatch: ' + relative)
        if relative.startswith('datasets/clothing_small/train/'):
            image_count += 1
    if image_count != 3068:
        raise ValueError('Runtime catalog must contain exactly 3068 images')
    required = {'app.py', 'Start_Demo.cmd', 'requirements_runtime.txt',
                'models/siglip2_base/model.safetensors',
                'models/sam2_base_plus/model.safetensors',
                'data/catalog_siglip2.faiss', 'data/catalog_siglip2_paths.json',
                'data/catalog_metadata_train.json', 'data/reviewed_product_groups.json'}
    if not required.issubset(seen):
        raise ValueError('Required runtime components are missing from the manifest')
    return {'verified': True, 'files': len(seen), 'catalog_images': image_count,
            'hashes_checked': not quick, 'application_release': manifest['application_release']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--quick', action='store_true', help='Check file sizes without reading all model bytes')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root.resolve(), quick=args.quick), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Runtime verification failed: ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
