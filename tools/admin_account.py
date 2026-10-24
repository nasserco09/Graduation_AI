"""Recover the single local administrator through filesystem access, without HTTP."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.admin_auth import AdminAuth, AuthError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path(os.getenv('GRADUATION_AI_AUTH_DB', str(ROOT/'data/admin_auth.db'))))
    parser.add_argument('--reset', action='store_true', help='Replace the account and revoke all sessions; preserves products.')
    args = parser.parse_args()
    store = AdminAuth(args.database)
    if store.configured() and not args.reset:
        parser.error('Account already configured. Use --reset only to recover access.')
    username = input('Administrator username (3-40 ASCII characters): ').strip()
    password = getpass('New password (15-128 characters): ')
    if password != getpass('Confirm new password: '):
        print('Passwords do not match. Nothing changed.'); return 1
    try:
        if args.reset: store.reset_local(username, password)
        else: store.setup(username, password)
    except AuthError as error:
        print('Account not changed: '+error.code); return 1
    print('Administrator saved. Sign in through /admin-login.html. Products were preserved.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
