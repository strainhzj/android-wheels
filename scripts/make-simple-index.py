#!/usr/bin/env python3
"""从 dist/ 目录生成 PEP 503 simple index（多包，含 sha256 fragment 与 hash 清单）。

用法: make-simple-index.py <dist_root> <output_dir>

产物（按包名归组）：
  <out>/simple/<pkg>/index.html           # PEP 503 索引（sha256 fragment）
  <out>/simple/<pkg>/hashes-SHA256SUMS    # 审计用 hash 清单
  <out>/simple/<pkg>/*.whl                # 复制自 dist
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path


def normalize(name: str) -> str:
    # PEP 503：URL 路径归一化把 [-_.] 连串替换为 "-"（连字符），pip 请求
    # /simple/<pkg>/；静态 Pages 无服务端归一化，目录名必须与之一致
    return name.replace("_", "-").replace(".", "-").lower()


def pkg_of(wheel_name: str) -> str:
    # wheel 文件名：<distribution>-<version>[-<build>]-<py>-<abi>-<plat>.whl
    return wheel_name.split("-")[0]


def main() -> int:
    dist_root, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    wheels = sorted(dist_root.rglob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_root} 无 wheel")
        return 1

    by_pkg: dict[str, list[Path]] = {}
    for wheel in wheels:
        by_pkg.setdefault(normalize(pkg_of(wheel.name)), []).append(wheel)

    for pkg, pkg_wheels in sorted(by_pkg.items()):
        pkg_dir = out_dir / "simple" / pkg
        pkg_dir.mkdir(parents=True, exist_ok=True)

        rows = []
        for wheel in pkg_wheels:
            dest = pkg_dir / wheel.name
            if not dest.exists():  # 同名去重（artifact 合并时）
                shutil.copy2(wheel, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            rows.append((dest.name, digest))

        (pkg_dir / "hashes-SHA256SUMS").write_text(
            "\n".join(f"{digest}  {name}" for name, digest in rows) + "\n", encoding="utf-8"
        )

        links = "\n".join(
            f'    <a href="{name}#sha256={digest}">{name}</a><br/>' for name, digest in rows
        )
        html = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "  <head>\n"
            '    <meta name="pypi:repository-version" content="1.0">\n'
            f"    <title>Links for {pkg}</title>\n"
            "  </head>\n"
            "  <body>\n"
            f"    <h1>Links for {pkg}</h1>\n"
            f"{links}\n"
            "  </body>\n"
            "</html>\n"
        )
        (pkg_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"索引: {pkg_dir / 'index.html'}（{len(rows)} 个 wheel）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
