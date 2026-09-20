"""用户脚本库（``lua_script/`` 目录）。

目录结构::

    <APP_ROOT>/lua_script/
        user_scripts.db      元信息 + 执行审计（SQLite）
        demo.echo.lua        脚本正文 —— **真身**，可以直接用外部编辑器改
        .backup/             覆盖或删除前的历史正文（每脚本最多留 5 份）

放在 ``<APP_ROOT>``（打包后就是 ``agvmon.exe`` 所在目录）而不是别处：更新流程是用
robocopy 把更新包覆盖上去、**不做清理**，包内也不含 ``lua_script/``，所以脚本不会被
版本更新冲掉（与 ``util/config.py`` 里 config.toml 的处理一致）。

**正文以 .lua 文件为准**：读取时永远先看文件，文件内容与库里的副本不一致
（说明有人直接编辑了文件）就以文件为准回写副本并递增版本；文件被误删时用库里
的副本自愈。这样既能用网页编辑器管理，也能直接改文件 / 塞进 git。
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from util.config import APP_ROOT

# 脚本目录名（相对 APP_ROOT）与库文件名
SCRIPT_DIR_NAME = "lua_script"
INDEX_DB_NAME = "user_scripts.db"
BACKUP_DIR_NAME = ".backup"
# 每个脚本保留的历史正文份数（覆盖 / 删除前自动留一份）
MAX_BACKUPS = 5

# 旧版把库放在 <APP_ROOT>/data/user_scripts.db，首次启动时自动搬过来
LEGACY_DB_RELATIVE = Path("data") / "user_scripts.db"

# 脚本 ID：字母数字与 _ . - ，限长 64
SCRIPT_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

# 审计流水最多保留的条数（每次写入后裁剪）
MAX_RUN_ROWS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_scripts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id    TEXT    NOT NULL UNIQUE,
    name         TEXT    NOT NULL DEFAULT '',
    description  TEXT    NOT NULL DEFAULT '',
    code         TEXT    NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    last_run_at  TEXT,
    last_status  TEXT,
    last_error   TEXT,
    run_count    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_script_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id     TEXT    NOT NULL,
    timestamp     TEXT    NOT NULL,
    source        TEXT    NOT NULL DEFAULT '',
    ok            INTEGER NOT NULL,
    status        TEXT    NOT NULL DEFAULT '',
    error         TEXT    NOT NULL DEFAULT '',
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    payload_bytes INTEGER NOT NULL DEFAULT 0,
    result_bytes  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_runs_script ON user_script_runs(script_id, id DESC);
"""


class ScriptNotFound(KeyError):
    """脚本不存在。"""


class ScriptIdInvalid(ValueError):
    """脚本 ID 不合法。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def valid_script_id(script_id: str) -> bool:
    return bool(isinstance(script_id, str) and SCRIPT_ID_RE.match(script_id))


def default_script_dir() -> Path:
    """默认脚本目录：``<APP_ROOT>/lua_script``。"""
    return Path(APP_ROOT) / SCRIPT_DIR_NAME


class UserScriptStore:
    """用户脚本 CRUD + 执行审计（正文落 .lua 文件，元信息落 SQLite）。"""

    def __init__(self, root_dir: str | Path | None = None):
        root = Path(root_dir) if root_dir is not None else default_script_dir()
        root.mkdir(parents=True, exist_ok=True)
        self.root_dir = root
        self.db_path = root / INDEX_DB_NAME
        self.backup_dir = root / BACKUP_DIR_NAME
        self.init_db()
        # 只有默认目录才做旧库迁移：指定了别的目录（测试、多套环境）就别去动旧库
        if root_dir is None:
            self.migrate_legacy()

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def script_path(self, script_id: str) -> Path:
        """脚本正文文件路径。script_id 已由正则限定，不含路径分隔符。"""
        return self.root_dir / f"{script_id}.lua"

    # ------------------------------------------------------------------
    # 正文文件读写
    # ------------------------------------------------------------------
    def _read_code_file(self, script_id: str) -> str | None:
        path = self.script_path(script_id)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            return None

    def _write_code_file(self, script_id: str, code: str) -> Path:
        """原子写：先写临时文件再 replace，避免半截文件被读到。"""
        path = self.script_path(script_id)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(code, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        return path

    def _backup_code(self, script_id: str, version: int, code: str | None) -> None:
        """覆盖/删除前留一份历史正文，每个脚本最多 MAX_BACKUPS 份。"""
        if not code:
            return
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            (self.backup_dir / f"{script_id}.v{int(version):04d}.lua").write_text(
                code, encoding="utf-8", newline="\n"
            )
            files = sorted(
                self.backup_dir.glob(f"{script_id}.v*.lua"),
                key=lambda p: p.name,
                reverse=True,
            )
            for stale in files[MAX_BACKUPS:]:
                stale.unlink(missing_ok=True)
        except OSError:
            # 备份是锦上添花，失败不影响主流程
            pass

    def list_backups(self, script_id: str) -> list[dict]:
        if not self.backup_dir.exists():
            return []
        out = []
        for path in sorted(self.backup_dir.glob(f"{script_id}.v*.lua"), reverse=True):
            try:
                out.append({
                    "name": path.name,
                    "version": int(path.name.rsplit(".v", 1)[1].split(".")[0]),
                    "bytes": path.stat().st_size,
                })
            except (OSError, ValueError, IndexError):
                continue
        return out

    # ------------------------------------------------------------------
    # 行 -> dict
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_script(row: sqlite3.Row, code: str, include_code: bool) -> dict:
        data = {
            "script_id": row["script_id"],
            "name": row["name"],
            "description": row["description"],
            "enabled": bool(row["enabled"]),
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_run_at": row["last_run_at"],
            "last_status": row["last_status"],
            "last_error": row["last_error"],
            "run_count": row["run_count"],
            "code_bytes": len(code.encode("utf-8")),
            "code_lines": (code.count("\n") + 1) if code else 0,
            "file": f"{row['script_id']}.lua",
        }
        if include_code:
            data["code"] = code
        return data

    def _resolve_code(self, row: sqlite3.Row) -> tuple[str, dict]:
        """取正文，返回 ``(code, 行数据)``。

        文件优先；文件被外部改过就回写库里的副本并递增版本（同步更新返回的行
        数据，避免调用方看到旧版本号）；文件被误删时用库里的副本自愈。
        """
        script_id = row["script_id"]
        cached = row["code"] or ""
        code = self._read_code_file(script_id)
        if code is None:
            if cached:
                try:
                    self._write_code_file(script_id, cached)
                except OSError:
                    pass
            return cached, dict(row)

        if code != cached:
            self._sync_code(script_id, code)
            fresh = dict(row)
            fresh["version"] = fresh["version"] + 1
            fresh["updated_at"] = _now()
            return code, fresh
        return code, dict(row)

    def _sync_code(self, script_id: str, code: str) -> None:
        """文件内容变化时回写库里的副本并递增版本（外部编辑也算一次修订）。"""
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE user_scripts
                   SET code = ?, version = version + 1, updated_at = ?
                   WHERE script_id = ? AND code <> ?""",
                (code, _now(), script_id, code),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list(self, include_code: bool = False) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM user_scripts ORDER BY script_id").fetchall()
            out = []
            for r in rows:
                code, fresh = self._resolve_code(r)
                out.append(self._row_to_script(fresh, code, include_code))
            return out
        finally:
            conn.close()

    def get(self, script_id: str, include_code: bool = True) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM user_scripts WHERE script_id = ?", (script_id,)
            ).fetchone()
            if row is None:
                return None
            code, fresh = self._resolve_code(row)
            return self._row_to_script(fresh, code, include_code)
        finally:
            conn.close()

    def create(
        self,
        script_id: str,
        code: str,
        *,
        name: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> dict:
        if not valid_script_id(script_id):
            raise ScriptIdInvalid(
                "脚本 ID 只能包含字母、数字、下划线、点和短横线，长度 1-64"
            )
        if not isinstance(code, str) or not code.strip():
            raise ValueError("脚本内容不能为空")

        now = _now()
        conn = self._connect()
        try:
            try:
                conn.execute(
                    """INSERT INTO user_scripts
                       (script_id, name, description, code, enabled, version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                    (script_id, name, description, code, 1 if enabled else 0, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"脚本 ID 已存在: {script_id}") from exc
            conn.commit()
        finally:
            conn.close()

        # 正文落文件；写失败就把刚插入的行回滚掉，保持文件与库一致
        try:
            self._write_code_file(script_id, code)
        except OSError as exc:
            self.delete(script_id)
            raise ValueError(f"脚本文件写入失败: {exc}") from exc
        return self.get(script_id)

    def update(
        self,
        script_id: str,
        *,
        code: str | None = None,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> dict:
        current = self.get(script_id, include_code=False)
        if current is None:
            raise ScriptNotFound(script_id)

        fields: list[str] = []
        params: list = []
        if code is not None:
            if not isinstance(code, str) or not code.strip():
                raise ValueError("脚本内容不能为空")
            # 覆盖前先把当前正文留一份历史
            self._backup_code(script_id, current["version"], self._read_code_file(script_id))
            try:
                self._write_code_file(script_id, code)
            except OSError as exc:
                raise ValueError(f"脚本文件写入失败: {exc}") from exc
            fields.append("code = ?")
            params.append(code)
            # 正文变化才递增版本
            fields.append("version = version + 1")
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(1 if enabled else 0)

        if not fields:
            return self.get(script_id)

        fields.append("updated_at = ?")
        params.append(_now())
        params.append(script_id)

        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE user_scripts SET {', '.join(fields)} WHERE script_id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(script_id)

    def delete(self, script_id: str, keep_backup: bool = True) -> bool:
        row = self.get(script_id, include_code=False)
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM user_scripts WHERE script_id = ?", (script_id,))
            conn.execute("DELETE FROM user_script_runs WHERE script_id = ?", (script_id,))
            conn.commit()
        finally:
            conn.close()

        if cur.rowcount > 0 and row is not None:
            if keep_backup:
                self._backup_code(script_id, row["version"], self._read_code_file(script_id))
            self.script_path(script_id).unlink(missing_ok=True)
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # 执行审计
    # ------------------------------------------------------------------
    def record_run(
        self,
        script_id: str,
        *,
        ok: bool,
        status: str,
        error: str = "",
        duration_ms: int = 0,
        payload_bytes: int = 0,
        result_bytes: int = 0,
        source: str = "",
    ) -> None:
        now = _now()
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO user_script_runs
                   (script_id, timestamp, source, ok, status, error,
                    duration_ms, payload_bytes, result_bytes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (script_id, now, source, 1 if ok else 0, status, error[:2000],
                 int(duration_ms), int(payload_bytes), int(result_bytes)),
            )
            # 只保留最近 MAX_RUN_ROWS 条
            conn.execute(
                """DELETE FROM user_script_runs WHERE id NOT IN (
                       SELECT id FROM user_script_runs ORDER BY id DESC LIMIT ?
                   )""",
                (MAX_RUN_ROWS,),
            )
            conn.execute(
                """UPDATE user_scripts
                   SET last_run_at = ?, last_status = ?, last_error = ?,
                       run_count = run_count + 1
                   WHERE script_id = ?""",
                (now, status, error[:2000], script_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_runs(self, script_id: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(500, int(limit)))
        conn = self._connect()
        try:
            if script_id:
                rows = conn.execute(
                    "SELECT * FROM user_script_runs WHERE script_id = ? ORDER BY id DESC LIMIT ?",
                    (script_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM user_script_runs ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [
                {
                    "id": r["id"],
                    "script_id": r["script_id"],
                    "timestamp": r["timestamp"],
                    "source": r["source"],
                    "ok": bool(r["ok"]),
                    "status": r["status"],
                    "error": r["error"],
                    "duration_ms": r["duration_ms"],
                    "payload_bytes": r["payload_bytes"],
                    "result_bytes": r["result_bytes"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 目录信息 / 旧库迁移
    # ------------------------------------------------------------------
    def count(self) -> int:
        conn = self._connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM user_scripts").fetchone()[0])
        finally:
            conn.close()

    def storage_info(self) -> dict:
        return {
            "dir": str(self.root_dir),
            "db": str(self.db_path),
            "backup_dir": str(self.backup_dir),
            "script_count": self.count(),
            "lua_files": sorted(p.name for p in self.root_dir.glob("*.lua")),
        }

    def migrate_legacy(self) -> int:
        """把旧版 ``<APP_ROOT>/data/user_scripts.db`` 搬到新目录，返回迁移条数。

        迁移完成后把旧库改名成 ``user_scripts.db.migrated``：数据还在，但不会
        被反复导入。新库已有脚本时不覆盖，只改名。
        """
        legacy = Path(APP_ROOT) / LEGACY_DB_RELATIVE
        if not legacy.exists() or legacy.resolve() == self.db_path.resolve():
            return 0

        moved = 0
        try:
            conn = sqlite3.connect(f"file:{legacy.as_posix()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("SELECT * FROM user_scripts").fetchall()
                runs = conn.execute(
                    "SELECT * FROM user_script_runs ORDER BY id DESC LIMIT ?", (MAX_RUN_ROWS,)
                ).fetchall()
            finally:
                conn.close()

            if rows and self.count() == 0:
                index = self._connect()
                try:
                    for r in rows:
                        index.execute(
                            """INSERT OR IGNORE INTO user_scripts
                               (script_id, name, description, code, enabled, version,
                                created_at, updated_at, last_run_at, last_status,
                                last_error, run_count)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (r["script_id"], r["name"], r["description"], r["code"],
                             r["enabled"], r["version"], r["created_at"], r["updated_at"],
                             r["last_run_at"], r["last_status"], r["last_error"],
                             r["run_count"]),
                        )
                        try:
                            self._write_code_file(r["script_id"], r["code"] or "")
                        except OSError:
                            pass
                    for r in reversed(runs):
                        index.execute(
                            """INSERT INTO user_script_runs
                               (script_id, timestamp, source, ok, status, error,
                                duration_ms, payload_bytes, result_bytes)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (r["script_id"], r["timestamp"], r["source"], r["ok"],
                             r["status"], r["error"], r["duration_ms"],
                             r["payload_bytes"], r["result_bytes"]),
                        )
                    index.commit()
                    moved = len(rows)
                finally:
                    index.close()

            legacy.rename(legacy.with_name(legacy.name + ".migrated"))
        except (sqlite3.Error, OSError):
            # 旧库坏了/被占用就算了，不能因此让服务起不来
            return moved

        if moved:
            try:
                from util.logger import logger

                logger.info(f"用户脚本库已迁移到 {self.root_dir}：{moved} 个脚本")
            except Exception:
                pass
        return moved


# 默认单例（延迟创建，避免 import 阶段就落盘）
_store: UserScriptStore | None = None


def get_store() -> UserScriptStore:
    global _store
    if _store is None:
        _store = UserScriptStore()
    return _store
