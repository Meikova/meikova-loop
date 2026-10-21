"""Database dual-adapter for Meikova Loop.
Supports:
- Turso Cloud SQLite over HTTP/WebSocket via libsql-client (when TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set)
- Local SQLite with WAL mode at DATA_DIR / 'loopbox.db' (fallback)
"""
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple, Union

from .config import DATA_DIR

logger = logging.getLogger("meikova.loop.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS library_items (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT,
    channel TEXT,
    duration REAL,
    bpm REAL,
    key TEXT,
    file_hash TEXT,
    file_size INTEGER,
    relative_path TEXT,
    remote_url TEXT,
    hydration_status TEXT DEFAULT 'METADATA_ONLY',
    analysis_data TEXT,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT,
    track_ids TEXT,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY,
    settings_json TEXT,
    updated_at REAL
);
"""


class TursoResultWrapper:
    def __init__(self, rs):
        self._rs = rs
        self.rows = rs.rows if hasattr(rs, "rows") else []
        self.columns = rs.columns if hasattr(rs, "columns") else ()
        self.rows_affected = getattr(rs, "rows_affected", 0)
        self.last_insert_rowid = getattr(rs, "last_insert_rowid", None)

    def fetchall(self) -> list:
        return self.rows

    def fetchone(self) -> Any:
        return self.rows[0] if self.rows else None

    def __iter__(self) -> Iterator:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, item):
        return self.rows[item]


class SQLiteResultWrapper:
    def __init__(self, cursor: sqlite3.Cursor):
        self.rows = cursor.fetchall()
        self.columns = tuple(d[0] for d in cursor.description) if cursor.description else ()
        self.rows_affected = cursor.rowcount
        self.last_insert_rowid = cursor.lastrowid

    def fetchall(self) -> list:
        return self.rows

    def fetchone(self) -> Any:
        return self.rows[0] if self.rows else None

    def __iter__(self) -> Iterator:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, item):
        return self.rows[item]


class LoopDbAdapter:
    """Unified adapter for Turso Cloud and local SQLite."""

    def __init__(
        self,
        url: Optional[str] = None,
        auth_token: Optional[str] = None,
        db_path: Optional[Union[Path, str]] = None,
    ):
        raw_url = (url if url is not None else os.environ.get("TURSO_DATABASE_URL", "")).strip()
        raw_token = (auth_token if auth_token is not None else os.environ.get("TURSO_AUTH_TOKEN", "")).strip()

        # Normalize url: libsql:// -> https://
        if raw_url.startswith("libsql://"):
            raw_url = "https://" + raw_url[len("libsql://"):]

        self.url: Optional[str] = raw_url if raw_url else None
        self.auth_token: Optional[str] = raw_token if raw_token else None
        self.db_path: Path = Path(db_path) if db_path else (DATA_DIR / "loopbox.db")
        self._is_turso: bool = bool(self.url and self.auth_token)

        self._turso_client = None
        self._sqlite_conn = None
        self._lock = threading.RLock()
        self._connect()

    def _connect(self) -> None:
        if self._is_turso:
            try:
                import libsql_client
                self._turso_client = libsql_client.create_client_sync(
                    url=self.url,
                    auth_token=self.auth_token
                )
                logger.info("Connected to Turso Cloud database at %s", self.url)
                return
            except Exception as e:
                logger.warning("Failed to connect to Turso (%s), falling back to local SQLite: %s", self.url, e)
                self._is_turso = False

        # Local SQLite WAL fallback
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        self._sqlite_conn.row_factory = sqlite3.Row
        self._sqlite_conn.execute("PRAGMA journal_mode=WAL;")
        self._sqlite_conn.execute("PRAGMA synchronous=NORMAL;")
        self._sqlite_conn.executescript(SCHEMA_SQL)
        self._sqlite_conn.commit()
        logger.info("Connected to local SQLite (WAL) at %s", self.db_path)

    @property
    def is_turso(self) -> bool:
        return self._is_turso

    @property
    def db_type(self) -> str:
        return "turso" if self._is_turso else "sqlite"

    def execute(self, sql: str, params: Any = None):
        with self._lock:
            if self._is_turso and self._turso_client:
                args = params if params is not None else []
                if isinstance(args, tuple):
                    args = list(args)
                rs = self._turso_client.execute(sql, args)
                return TursoResultWrapper(rs)
            elif self._sqlite_conn:
                cur = self._sqlite_conn.cursor()
                if params is not None:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                # Commit automatically on DDL / DML
                upper_sql = sql.strip().upper()
                if upper_sql.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE")):
                    self._sqlite_conn.commit()
                return SQLiteResultWrapper(cur)
            else:
                raise RuntimeError("Database connection is closed")

    def fetchall(self, sql: str, params: Any = None) -> list:
        return self.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: Any = None) -> Any:
        return self.execute(sql, params).fetchone()

    def batch(self, stmts: List[Union[str, Tuple[str, Any]]]) -> list:
        with self._lock:
            results = []
            if self._is_turso and self._turso_client:
                for item in stmts:
                    if isinstance(item, tuple):
                        results.append(self.execute(item[0], item[1]))
                    else:
                        results.append(self.execute(item))
            elif self._sqlite_conn:
                for item in stmts:
                    if isinstance(item, tuple):
                        results.append(self.execute(item[0], item[1]))
                    else:
                        results.append(self.execute(item))
                self._sqlite_conn.commit()
            return results

    def commit(self) -> None:
        with self._lock:
            if self._sqlite_conn:
                try:
                    self._sqlite_conn.commit()
                except Exception:
                    pass

    def close(self) -> None:
        with self._lock:
            if self._turso_client:
                try:
                    self._turso_client.close()
                except Exception:
                    pass
                self._turso_client = None
            if self._sqlite_conn:
                try:
                    self._sqlite_conn.close()
                except Exception:
                    pass
                self._sqlite_conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_db(
    url: Optional[str] = None,
    auth_token: Optional[str] = None,
    db_path: Optional[Union[Path, str]] = None,
) -> LoopDbAdapter:
    """Factory function to get a LoopDbAdapter instance."""
    return LoopDbAdapter(url=url, auth_token=auth_token, db_path=db_path)
