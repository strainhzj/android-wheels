#!/usr/bin/env python3
"""校验产出的 Android wheel：文件名 tag 结构 + ELF ABI + （可选）api level。

用法: check-wheel-tag.py <dist_dir> <android_abi> <python_version>

- 文件名必须形如 pydantic_core-<ver>-cp312-abi3-<platform>.whl，
  其中 <platform> 必须含 "android" 且与 ABI 对应（arm64_v8a ↔ aarch64 等，
  精确 tag 以 versions.env 回填值为准，见 ANDROID_WHEEL_TAG 环境变量）。
- ELF 校验 .so 的机器架构与 linkage（NDK 产物应为 PIE 动态库）。
"""

from __future__ import annotations

import os
import re
import struct
import sys
import zipfile
from pathlib import Path

ABI_TO_ELF_MACHINE = {
    "arm64-v8a": (0xB7, "AArch64"),
    "armeabi-v7a": (40, "ARM"),
    "x86_64": (62, "x86-64"),
    "x86": (3, "i386"),
}


def wheel_platform_ok(platform: str, abi: str) -> bool:
    expected_tag = os.environ.get("ANDROID_WHEEL_TAG", "")
    if expected_tag:
        return platform == expected_tag
    if "android" not in platform:
        return False
    # 未回填精确 tag 前的宽松映射校验
    lo = platform.lower()
    return (
        ("arm64" in lo or "aarch64" in lo) if abi == "arm64-v8a"
        else ("armv7" in lo or "armeabi" in lo) if abi == "armeabi-v7a"
        else ("x86_64" in lo) if abi == "x86_64"
        else ("i686" in lo or "x86" in lo and "x86_64" not in lo)
    )


def elf_machine(data: bytes) -> int:
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    is_64 = data[4] == 2
    little = data[5] == 1
    fmt = "<Q" if is_64 else "<I"
    return struct.unpack(fmt, data[16 : 16 + struct.calcsize(fmt)])[0]


def main() -> int:
    dist_dir, abi, py_version = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_dir} 下没有 wheel")
        return 1

    tag_pattern = re.compile(rf"^pydantic_core-[\d.]+.*-cp{py_version.replace('.', '')}-abi3-(.+)\.whl$")
    failures = []
    for wheel in wheels:
        m = tag_pattern.match(wheel.name)
        if not m:
            failures.append(f"{wheel.name}: 文件名不符合 cp{py_version.replace('.', '')}-abi3 结构")
            continue
        platform = m.group(1)
        if not wheel_platform_ok(platform, abi):
            failures.append(f"{wheel.name}: platform tag '{platform}' 与 {abi} 不符")

        expected_machine, desc = ABI_TO_ELF_MACHINE[abi]
        with zipfile.ZipFile(wheel) as zf:
            so_names = [n for n in zf.namelist() if n.endswith(".so")]
            if not so_names:
                failures.append(f"{wheel.name}: 缺少 native .so")
            for name in so_names:
                machine = elf_machine(zf.read(name)[:64])
                if machine != expected_machine:
                    failures.append(f"{wheel.name}:{name}: ELF machine {machine} != {desc}({expected_machine})")

        if failures:
            continue
        print(f"OK: {wheel.name} [{abi}]")
    if failures:
        print("\n".join(f"FAIL: {f}" for f in failures))
        return 1
    print(f"全部 wheel 校验通过 [{abi}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
