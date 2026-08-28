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
    # ELF64/32 头：e_ident[16] + e_type@16(u16) + e_machine@18(u16)
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    return struct.unpack_from("<H", data, 18)[0]


def elf_dt_needed(data: bytes) -> list[str]:
    # ELF64：PT_DYNAMIC → DT_NEEDED（tag=1），字符串经 DT_STRTAB（文件偏移）
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise ValueError("not an ELF64 file")
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    dyn = strtab = None
    needed_offs: list[int] = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if struct.unpack_from("<I", data, off)[0] != 2:  # PT_DYNAMIC
            continue
        p_offset = struct.unpack_from("<Q", data, off + 8)[0]
        p_filesz = struct.unpack_from("<Q", data, off + 32)[0]
        o, end = p_offset, p_offset + p_filesz
        while o < end:
            tag, val = struct.unpack_from("<QQ", data, o)
            if tag == 0:
                break
            if tag == 1:
                needed_offs.append(val)
            elif tag == 5:
                strtab = val
            o += 16
        break
    if strtab is None:
        raise ValueError("no DT_STRTAB")
    out = []
    for v in needed_offs:
        e = data.index(b"\x00", strtab + v)
        out.append(data[strtab + v : strtab + v + (e - strtab - v)].decode())
    return out


def main() -> int:
    dist_dir, abi, py_version = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_dir} 下没有 wheel")
        return 1

    # Chaquopy cp312 形态为 cp312-cp312（版本专属，见官方仓库 wheel 文件名）；
    # abi3 形态保留兼容以防未来切换
    v = py_version.replace(".", "")
    tag_pattern = re.compile(rf"^pydantic_core-[\d.]+.*-cp{v}-(?:abi3|cp{v})-(.+)\.whl$")
    # Chaquopy 官方扩展形态（bcrypt 解剖实证）：DT_NEEDED 含 libpython<ver>.so，
    # 扩展 .so 为裸名（不带 cpython/abi3 后缀）
    libpython = f"libpython{py_version}.so"
    failures = []
    for wheel in wheels:
        m = tag_pattern.match(wheel.name)
        if not m:
            failures.append(f"{wheel.name}: 文件名不符合 cp{v} 结构")
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
                if re.search(r"\.(cpython-[\d]|abi3).*\.so$", name.rsplit("/", 1)[-1]):
                    failures.append(f"{wheel.name}:{name}: 扩展 .so 应为裸名（Chaquopy 形态）")
                data = zf.read(name)
                machine = elf_machine(data[:64])
                if machine != expected_machine:
                    failures.append(f"{wheel.name}:{name}: ELF machine {machine} != {desc}({expected_machine})")
                    continue
                try:
                    needed = elf_dt_needed(data)
                    if libpython not in needed:
                        failures.append(
                            f"{wheel.name}:{name}: DT_NEEDED 缺 {libpython}（实际 {needed}）"
                            "——Chaquopy 扩展运行时经它解析 Py 符号"
                        )
                except ValueError as exc:
                    failures.append(f"{wheel.name}:{name}: ELF 解析失败 {exc}")

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
