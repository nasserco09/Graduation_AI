"""Build a runtime-only distribution without personal databases or unused models."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

if __package__:
    from .verify_runtime import digest, safe_file, verify
else:
    from verify_runtime import digest, safe_file, verify


MODEL_FILES = {
    'siglip2_base': ('config.json', 'model.safetensors', 'preprocessor_config.json',
                     'special_tokens_map.json', 'tokenizer_config.json', 'tokenizer.json',
                     'tokenizer.model', 'README.md'),
    'sam2_base_plus': ('config.json', 'model.safetensors', 'preprocessor_config.json',
                       'processor_config.json', 'video_preprocessor_config.json', 'README.md'),
}
DATA_FILES = ('catalog_metadata_train.json', 'catalog_siglip2.faiss',
              'catalog_siglip2_paths.json', 'reviewed_product_groups.json')


def application_modules(root: Path) -> set[str]:
    pending = ['app', 'tools.launch_demo']
    selected = set()
    while pending:
        module = pending.pop()
        parts = module.split('.')
        candidates = [root.joinpath(*parts).with_suffix('.py'), root.joinpath(*parts, '__init__.py')]
        path = next((p for p in candidates if p.is_file()), None)
        if path is None:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in selected:
            continue
        selected.add(relative)
        for position in range(1, len(parts)):
            init = root.joinpath(*parts[:position], '__init__.py')
            if init.is_file():
                selected.add(init.relative_to(root).as_posix())
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                pending.append(node.module)
    return selected


def collect_files(root: Path) -> dict[str, str]:
    selected = {name: 'application' for name in application_modules(root)}
    for name in ('Start_Demo.cmd', 'Setup_Runtime.cmd', 'requirements_runtime.txt',
                 'tools/setup_runtime.py', 'tools/verify_runtime.py', 'RUNTIME_README_AR.md'):
        selected[name] = 'setup'
    for path in (root / 'frontend').rglob('*'):
        if path.is_file() and path.suffix.lower() in {'.html', '.css', '.js', '.json', '.svg', '.png', '.ico', '.jpg', '.woff', '.woff2', '.ttf', '.txt'}:
            if any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(root / 'frontend').parts):
                continue
            selected[path.relative_to(root).as_posix()] = 'frontend'
    for model, names in MODEL_FILES.items():
        for name in names:
            selected[f'models/{model}/{name}'] = 'model'
    for name in DATA_FILES:
        selected['data/' + name] = 'catalog_index'
    for name in ('LICENSE', 'README.md'):
        selected['datasets/clothing_small/' + name] = 'dataset_notice'
    for path in (root / 'datasets/clothing_small/train').rglob('*'):
        if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}:
            selected[path.relative_to(root).as_posix()] = 'catalog_image'
    for path in (root / 'runtime/licenses').rglob('*'):
        if path.is_file():
            selected[path.relative_to(root).as_posix()] = 'license'
    selected['runtime/THIRD_PARTY_NOTICES.md'] = 'license'
    if sum(role == 'catalog_image' for role in selected.values()) != 3068:
        raise ValueError('The package requires the original 3068-image catalog.')
    for name in selected:
        if not safe_file(root, name).is_file():
            raise ValueError('Missing runtime resource: ' + name)
    if 'backend/catalog_isolation.py' in selected:
        raise ValueError('Unexpected experiment module in the application graph')
    return selected


def stage(root: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError('Use a new, empty staging directory; existing data is never replaced.')
    files = collect_files(root)
    destination.mkdir(parents=True)
    entries = []
    for position, (relative, role) in enumerate(sorted(files.items()), 1):
        source = safe_file(root, relative)
        target = safe_file(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        entries.append({'path': relative, 'role': role, 'bytes': target.stat().st_size,
                        'sha256': digest(target)})
        if position % 500 == 0 or source.stat().st_size > 100_000_000:
            print(f'Staged {position}/{len(files)}: {relative}', flush=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    manifest = {'schema_version': 1, 'application_release': 'v1.2.0-rc.9',
                'package_release': 'runtime-rc9-v1', 'source_commit': revision,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'platform': 'Windows x86_64, Python 3.12', 'catalog_images': 3068,
                'files': entries}
    (destination / 'runtime_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(verify(destination)), flush=True)
    return manifest


def archive(stage_root: Path, output: Path) -> dict:
    verify(stage_root)
    manifest = json.loads((stage_root / 'runtime_manifest.json').read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix('.zip.part').exists():
        raise ValueError('Archive output already exists; use a new filename.')
    temporary = output.with_suffix('.zip.part')
    with ZipFile(temporary, 'w', ZIP_DEFLATED, compresslevel=1, allowZip64=True) as bundle:
        for position, entry in enumerate(manifest['files'], 1):
            bundle.write(safe_file(stage_root, entry['path']), 'Graduation_AI_Runtime/' + entry['path'])
            if position % 500 == 0 or entry['bytes'] > 100_000_000:
                print(f'Packed {position}/{len(manifest["files"])}: {entry["path"]}', flush=True)
        bundle.write(stage_root / 'runtime_manifest.json', 'Graduation_AI_Runtime/runtime_manifest.json')
    if temporary.stat().st_size >= 2 * 1024**3:
        raise ValueError('The archive exceeds the GitHub Release asset limit.')
    with ZipFile(temporary) as bundle:
        bad = bundle.testzip()
        if bad is not None:
            raise ValueError('Archive integrity check failed: ' + bad)
        if len(bundle.infolist()) != len(manifest['files']) + 1:
            raise ValueError('Unexpected archive entries')
    temporary.rename(output)
    result = {'archive': str(output), 'bytes': output.stat().st_size, 'sha256': digest(output)}
    print(json.dumps(result), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    modes = parser.add_subparsers(dest='mode', required=True)
    stage_mode = modes.add_parser('stage')
    stage_mode.add_argument('destination', type=Path)
    zip_mode = modes.add_parser('archive')
    zip_mode.add_argument('stage_root', type=Path)
    zip_mode.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.mode == 'stage':
        stage(args.root.resolve(), args.destination.resolve())
    else:
        archive(args.stage_root.resolve(), args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
