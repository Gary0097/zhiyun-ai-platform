import importlib.util
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'apps/zhizaoyunAIOS/scripts/hub-bind-host.py'
spec = importlib.util.spec_from_file_location('bind_host', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as temp:
    db = Path(temp) / "中文 user's hub.db"
    assert module.bind_host(db) == '127.0.0.1'
    assert not db.exists(), 'readiness probe must not create a database'
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute('CREATE TABLE hub_users (role TEXT, disabled INTEGER)')
        conn.execute("INSERT INTO hub_users VALUES ('user',0),('admin',1)")
    assert module.bind_host(db) == '127.0.0.1'
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("INSERT INTO hub_users VALUES ('admin',0)")
    assert module.bind_host(db) == '0.0.0.0'
print('Hub bootstrap: fresh, disabled admin, active admin and non-mutating probe passed')
