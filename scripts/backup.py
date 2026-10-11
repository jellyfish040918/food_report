"""Create a consistent, non-overwriting SQLite backup and verify integrity."""
import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import Settings

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('destination',help='New backup filename; must not exist')
    args=parser.parse_args()
    source=Path(Settings().database).resolve();target=Path(args.destination).resolve()
    if not source.is_file():parser.error('Source database does not exist.')
    if source==target:parser.error('Backup must differ from the live database.')
    target.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create, private permissions on POSIX; never overwrite an existing backup.
    descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as read,closing(sqlite3.connect(target)) as write:
        read.backup(write)
        if write.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed.')
    print(f'Verified backup: {target}')
