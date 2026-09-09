"""Choose the safe Hub bind host without creating or changing its database."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def bind_host(database):
    database = Path(database)
    if not database.exists():
        return '127.0.0.1'
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        admin = connection.execute("SELECT 1 FROM hub_users WHERE role='admin' AND disabled=0 LIMIT 1").fetchone()
    return '0.0.0.0' if admin else '127.0.0.1'


if __name__ == '__main__':
    workspace = Path(os.environ['QWENPAW_WORKING_DIR'])
    print(bind_host(workspace / 'hub' / 'control.db'))
