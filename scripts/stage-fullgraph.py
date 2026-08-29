#!/usr/bin/env python3
"""把 BtDeck 后端完整资源 staging 到 testapp 的 fullgraph 源集。

用法: stage-fullgraph.py [--btdeck <主仓路径>]   （默认与本仓同级 ../BtDeck）

产物（gitignored，testapp/app/src/fullgraph/）：
  python/app/**            ← backend/app（除 __pycache__）
  python/alembic/**        ← backend/alembic + backend/alembic.ini
  python/frontend/dist/**  ← frontend/dist（factory 候选路径 3 命中）
  python/fullgraph_bootstrap.py ← scripts/fullgraph_bootstrap.py 副本
  fullgraph-requirements.txt    ← backend/requirements.txt + Android 版本覆写

布局与后端锚定关系（零后端改动）：
  settings.ROOT_PATH = app/core/config.py 上溯两级 = staged python 目录 →
  migration 的 alembic.ini/alembic 绝对锚定与 factory 的 ROOT_PATH/frontend/dist
  候选路径同时命中。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTAPP = REPO / "testapp"
DST = TESTAPP / "app" / "src" / "fullgraph"

# Android 版本覆写：Chaquopy 官方仓库 cp312 现有 Android wheel 的版本。
# 后端 pin 与官方仓库存量的差集；闸门判据 5 以可安装可运行为准，版本对齐度
# 登记于 docs/gate.md（后续增强：自建 wheel 收窄差集）。
# 已自建对齐后端 pin（android-wheels 仓索引，无需覆写）：bcrypt 5.0.0、
# greenlet 3.0.1、regex 2024.11.6、pycryptodomex 3.23.0。
ANDROID_OVERRIDES: dict[str, str] = {
    # pillow：x86_64 有自建 11.1.0（索引优先解析高版本）；arm64 自建链接谜题
    # 未破（continue-on-error 隔离），回落官方 11.0.0——arm64 真机 16KB 验证
    # 属 Phase 5 设备矩阵，届时攻破
    "pillow": "pillow>=11.0.0,<12",
}


def copytree_clean(src: Path, dst: Path) -> int:
    n = 0
    for item in src.rglob("*"):
        if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache"} for part in item.parts):
            continue
        if item.suffix in {".pyc", ".pyo"}:
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btdeck", default=str(REPO.parent / "BtDeck"))
    args = parser.parse_args()
    btdeck = Path(args.btdeck)
    backend = btdeck / "backend"
    frontend_dist = btdeck / "frontend" / "dist"
    for required in (backend / "app", backend / "alembic", backend / "alembic.ini", frontend_dist):
        if not required.exists():
            print(f"FAIL: 缺少 {required}")
            return 1

    py_dst = DST / "python"
    if py_dst.exists():
        shutil.rmtree(py_dst)
    py_dst.mkdir(parents=True)

    n_app = copytree_clean(backend / "app", py_dst / "app")
    n_alembic = copytree_clean(backend / "alembic", py_dst / "alembic")
    shutil.copy2(backend / "alembic.ini", py_dst / "alembic.ini")
    # Chaquopy 源集会丢弃非包目录中的孤儿 .py（alembic/versions 整目录实证消失，
    # 而 frontend/dist 非 py 数据全量幸存）。加 __init__.py 成包又会遮蔽
    # requirements 里的真 alembic 库（run 实证 cannot import name 'command'）。
    # 方案：迁移脚本以 .pymig 数据扩展名打包（数据不被丢、目录保持命名空间形态
    # 不遮蔽真包——PEP 420 命名空间不阻断后置常规包），bootstrap 首跑物化回 .py。
    for f in (py_dst / "alembic").rglob("*.py"):
        f.rename(f.with_name(f.name + ".pymig"))
    n_dist = copytree_clean(frontend_dist, py_dst / "frontend" / "dist")
    shutil.copy2(REPO / "scripts" / "fullgraph_bootstrap.py", py_dst / "fullgraph_bootstrap.py")

    # 生成 requirements：逐行带出 + 覆写
    out_lines: list[str] = [
        "# 由 stage-fullgraph.py 生成——backend/requirements.txt + Android 版本覆写",
        "# 覆写原因：Chaquopy 官方仓库 cp312 现有 Android wheel 的版本差集（gate.md 登记）",
    ]
    for line in (backend / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split("~")[0].split("=")[0].split(">")[0].split("<")[0].strip().lower()
        override = ANDROID_OVERRIDES.get(name)
        if override:
            out_lines.append(f"{override}  # ANDROID-OVERRIDE（后端 pin: {stripped}）")
        else:
            out_lines.append(stripped)
    # Android 无系统 tz 数据库（zoneinfo 报 No time zone found with key GMT，
    # run 实证调度器启动失败）——tzdata 纯 Python 包是嵌入式标准补法（Phase 3 依赖）
    out_lines.append("tzdata>=2024.1  # ANDROID-ADD：Android 无系统 tz 数据库")
    (DST / "fullgraph-requirements.txt").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    print(f"staged: app {n_app} 文件 / alembic {n_alembic} 文件 / frontend dist {n_dist} 文件")
    print(f"输出目录: {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
