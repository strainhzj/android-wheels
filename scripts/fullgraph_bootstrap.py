# -*- coding: utf-8 -*-
"""fullgraph 阶段 2 运行体（闸门判据 5）：BtDeck 完整 import graph。

由 stage-fullgraph.py 拷入 staged python 目录（与 app/、alembic/、frontend/ 同级）。
Kotlin FullGraphTest 经 callAttr 逐项调用；每项独立可归因。

- 深导入一律在 16MB 大栈线程执行（ps16k 实证：默认线程栈在 Python 递归限
  触发前先耗尽 C 栈——Phase 3 同款要求）；
- 路径锚定零后端改动：ROOT_PATH=本目录 → migration 绝对锚定与 factory
  frontend/dist 候选路径 3 同时命中。
"""

import json
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _prepare_env() -> Path:
    base = ROOT.parent / "btdeck-test"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "torrents").mkdir(parents=True, exist_ok=True)
    os.environ["CONFIG_DIR"] = str(base / "config")
    os.environ["DATABASE_PATH"] = str(base / "config" / "app.db")
    os.environ["TORRENTS_DIR"] = str(base / "torrents")
    return base


def _run_on_big_stack(fn, stack_bytes: int = 16 * 1024 * 1024):
    result = {}

    def runner():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            import traceback
            result["error"] = "".join(traceback.format_exception(exc))

    threading.stack_size(stack_bytes)
    t = threading.Thread(target=runner, name="btdeck-fullgraph")
    t.start()
    t.join()
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("value")


def check_import() -> str:
    """判据 5a：完整 import graph（app.main，含 factory/路由/服务装配）。"""
    def _do():
        _prepare_env()
        from app import main  # noqa: F401
        from app.version import CURRENT_VERSION
        return CURRENT_VERSION
    version = _run_on_big_stack(_do)
    return json.dumps({"ok": True, "version": version})


def check_migration() -> str:
    """判据 5b：一次完整迁移（空库 → head，幂等重跑二次）。"""
    def _do():
        _prepare_env()
        from app.core.migration import migrate_database
        assert migrate_database(), "首次迁移失败"
        assert migrate_database(), "幂等重跑失败"
        from app.core.config import settings
        db = Path(settings.DATABASE_PATH)
        assert db.exists() and db.stat().st_size > 0, "数据库文件缺失"
        import sqlite3
        conn = sqlite3.connect(str(db))
        try:
            (ver,) = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            tables = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        finally:
            conn.close()
        return {"version": ver, "tables": tables}
    result = _run_on_big_stack(_do)
    return json.dumps({"ok": True, **result})


def check_server() -> str:
    """判据 5c：uvicorn loopback 服务 /health/live + 静态资源首页。"""
    def _do():
        _prepare_env()
        import uvicorn

        config = uvicorn.Config(
            "app.main:app", host="127.0.0.1", port=18080, log_level="warning"
        )
        server = uvicorn.Server(config)
        t = threading.Thread(target=server.run, daemon=True, name="btdeck-uvicorn")
        threading.stack_size(16 * 1024 * 1024)
        t.start()

        import httpx
        live = index = None
        last_error: Exception | None = None
        for _ in range(120):  # 服务+迁移+首启初始化最长 120s
            if not t.is_alive():
                raise RuntimeError("uvicorn 线程提前退出")
            try:
                live = httpx.get("http://127.0.0.1:18080/health/live", timeout=5)
                if live.status_code == 200:
                    index = httpx.get("http://127.0.0.1:18080/", timeout=10)
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(1)
        server.should_exit = True
        t.join(timeout=30)

        assert live is not None and live.status_code == 200, f"/health/live 失败: {last_error}"
        body = live.json()
        assert body.get("data", {}).get("status") == "alive", body
        assert index is not None and index.status_code == 200, f"/ 静态首页失败: {index}"
        assert "<div id=\"app\"" in index.text or "<html" in index.text.lower(), \
            "首页不是 SPA index.html"
        return {
            "live": body.get("data"),
            "index_bytes": len(index.content),
            "index_title_ok": "btdeck" in index.text.lower() or "<html" in index.text.lower(),
        }
    result = _run_on_big_stack(_do)
    return json.dumps({"ok": True, **result})
