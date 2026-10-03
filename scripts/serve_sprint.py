#!/usr/bin/env python3
"""Serve the private integration on loopback using explicitly selected local databases."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--django-db', type=Path, required=True, help='Existing disposable/dev Django database with authorized local accounts')
    parser.add_argument('--drafts-db', type=Path, required=True, help='Dedicated sprint SQLite file (new or compatible)')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    django_db, drafts_db = args.django_db.resolve(), args.drafts_db.resolve()
    if not django_db.is_file() or django_db == drafts_db:
        parser.error('Choose an existing local Django database and a separate sprint database.')
    if not drafts_db.parent.is_dir() or not 1024 <= args.port <= 65535:
        parser.error('The drafts directory must exist and port must be 1024–65535.')
    if not (root / 'frontend/dist/index.html').is_file():
        parser.error('Build first: npm --prefix frontend run build')
    with sqlite3.connect(django_db.as_uri() + '?mode=ro', uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_session'").fetchone():
            parser.error('The Django database must already be migrated.')
    os.environ['AULALISTA_DB_PATH'] = str(django_db)
    os.environ['AULALISTA_DRAFTS_DB_PATH'] = str(drafts_db)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aulalista.settings')
    os.environ['AULALISTA_ALLOWED_HOSTS'] = '127.0.0.1,localhost'
    sys.path.insert(0, str(root))
    from api.persistence import SQLiteRepository
    SQLiteRepository(drafts_db)
    import uvicorn
    print(f'Private local review: http://127.0.0.1:{args.port}/sprint/', flush=True)
    uvicorn.run('api.local:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
