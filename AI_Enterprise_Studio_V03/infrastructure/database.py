"""SQLite connection lifecycles; no schema, business policy or startup effects."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def transaction(path):
    """Preserve the original server transaction and rollback behavior."""
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@contextmanager
def read_snapshot(path):
    """Existing campus read-only, consistent snapshot; never create a DB."""
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=3)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        yield db
    finally:
        db.close()
