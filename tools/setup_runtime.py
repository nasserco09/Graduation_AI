"""Create an independent Windows Python 3.12 environment for a verified bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys
import venv

if __package__:
    from .verify_runtime import verify
else:
    from verify_runtime import verify


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheels', type=Path, help='Optional local wheel directory for an offline installation')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        print(json.dumps(verify(root), indent=2), flush=True)
        if args.check_only:
            return 0
        if platform.system() != 'Windows' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
            raise ValueError('This package targets 64-bit Windows with Python 3.12.')
        wheels = args.wheels.resolve() if args.wheels else None
        if wheels and not wheels.is_dir():
            raise ValueError('The wheel directory does not exist.')
        environment = root / '.venv'
        python = environment / 'Scripts' / 'python.exe'
        if not python.is_file():
            if environment.exists() and any(environment.iterdir()):
                raise ValueError('The existing .venv is incomplete; use a fresh project directory.')
            print('Creating the project virtual environment...', flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        version = subprocess.check_output(
            [str(python), '-c', 'import sys; print(str(sys.version_info.major)+"."+str(sys.version_info.minor))'],
            text=True).strip()
        if version != '3.12':
            raise ValueError('The existing environment must use Python 3.12.')
        command = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
        if wheels:
            command.extend(['--no-index', '--find-links', str(wheels)])
        command.extend(['-r', str(root / 'requirements_runtime.txt')])
        subprocess.run(command, check=True, cwd=root)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True, cwd=root)
        print('READY. Double-click Start_Demo.cmd. Create your own administrator account on first use.', flush=True)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Runtime setup failed: ' + str(error), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
