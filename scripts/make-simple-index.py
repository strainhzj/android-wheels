#!/usr/bin/env python3
"""从 dist/ 目录生成 PEP 503 simple index（含 sha256 fragment 与 hash 清单）。

用法: make-simple-index.py <dist_root> <output_dir>

产物:
  <output_dir>/simple/pydantic-core/index.html      # PEP 503 索引
  <output_dir>/simple/pydantic-core/hashes-SHA256SUMS  # 审计用 hash 清单
  <output_dir>/simple/pydantic-core/*.whl           # 复制自 dist（按 ABI 全量）
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

PKG = "pydantic-core"


def normalize(name: str) -> str:
    return name.replace("-", "_").replace(".", "_").lower()


def main() -> int:
    dist_root, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    wheels = sorted(dist_root.rglob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_root} 无 wheel")
        return 1

    pkg_dir = out_dir / "simple" / normalize(PKG)
    pkg_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for wheel in wheels:
        dest = pkg_dir / wheel.name
        shutil.copy2(wheel, dest)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        rows.append((wheel.name, digest))

    (pkg_dir / "hashes-SHA256SUMS").write_text(
        "\n".join(f"{digest}  {name}" for name, digest in rows) + "\n", encoding="utf-8"
    )

    links = "\n".join(f'    <a href="{name}#sha256={digest}">{name}</a><br/>' for name, digest in rows)
    html = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "  <head>\n"
        f'    <meta name="pypi:repository-version" content="1.0">\n'
        f"    <title>Links for {PKG}</title>\n"
        "  </head>\n"
        "  <body>\n"
        f"    <h1>Links for {PKG}</h1>\n"
        f"{links}\n"
        "  </body>\n"
        "</html>\n"
    )
    (pkg_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"索引已生成: {pkg_dir / 'index.html'}（{len(rows)} 个 wheel）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
