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


def elf_pt_load_aligns(data: bytes) -> list[int]:
    # ELF64：遍历程序头，收集 PT_LOAD 的 p_align（@48）
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise ValueError("not an ELF64 file")
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    out = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if struct.unpack_from("<I", data, off)[0] == 1:  # PT_LOAD
            out.append(struct.unpack_from("<Q", data, off + 48)[0])
    return out


def elf_dt_needed(data: bytes) -> list[str]:
    # ELF64：PT_DYNAMIC → DT_NEEDED（tag=1）；DT_STRTAB 的 d_ptr 是虚拟地址，
    #须经 PT_LOAD 映射翻译成文件偏移（patchelf 重写后 vaddr≠offset）
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise ValueError("not an ELF64 file")
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    loads: list[tuple[int, int, int]] = []  # (p_vaddr, p_filesz, p_offset)
    dyn = None
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        p_offset = struct.unpack_from("<Q", data, off + 8)[0]
        p_vaddr = struct.unpack_from("<Q", data, off + 16)[0]
        p_filesz = struct.unpack_from("<Q", data, off + 32)[0]
        if p_type == 1:  # PT_LOAD
            loads.append((p_vaddr, p_filesz, p_offset))
        elif p_type == 2 and dyn is None:  # PT_DYNAMIC
            dyn = (p_offset, p_offset + p_filesz)

    def v2o(v: int) -> int:
        for va, fs, fo in loads:
            if va <= v < va + fs:
                return fo + (v - va)
        raise ValueError(f"vaddr {v:#x} 不在任何 PT_LOAD 内")

    strtab = None
    needed_offs: list[int] = []
    if dyn is None:
        raise ValueError("no PT_DYNAMIC")
    o, end = dyn
    while o < end:
        tag, val = struct.unpack_from("<QQ", data, o)
        if tag == 0:
            break
        if tag == 1:
            needed_offs.append(val)
        elif tag == 5:
            strtab = val
        o += 16
    if strtab is None:
        raise ValueError("no DT_STRTAB")
    strtab_off = v2o(strtab)
    out = []
    for v in needed_offs:
        e = data.index(b"\x00", strtab_off + v)
        out.append(data[strtab_off + v : e].decode())
    return out


def main() -> int:
    dist_dir, abi, py_version = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    pkg = (sys.argv[4] if len(sys.argv) > 4 else "pydantic-core").replace("-", "_")
    # 模式：rust（pyo3 系，强制 DT_NEEDED libpython——Chaquopy 扩展形态）/
    #       c-ext（setuptools 系，CPython 扩展标准形态不链 libpython，跳过该断言）
    mode = sys.argv[5] if len(sys.argv) > 5 else "rust"
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_dir} 下没有 wheel")
        return 1

    # Chaquopy cp312 形态为 cp312-cp312（版本专属，见官方仓库 wheel 文件名）；
    # abi3 形态保留兼容以防未来切换
    v = py_version.replace(".", "")
    tag_pattern = re.compile(rf"^{re.escape(pkg)}-[\d.]+.*-cp{v}-(?:abi3|cp{v})-(.+)\.whl$")
    # Chaquopy 官方扩展形态（bcrypt 解剖实证）：DT_NEEDED 含 libpython<ver>.so，
    # 扩展 .so 为裸名（不带 cpython/abi3 后缀）
    libpython = f"libpython{py_version}.so"
    failures = []
    for wheel in wheels:
        m = tag_pattern.match(wheel.name)
        if not m:
            failures.append(f"{wheel.name}: 文件名不符合 {pkg} cp{v} 结构")
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
                # 16 KB page-size：所有 PT_LOAD 的 p_align 必须 ≥16384
                # （ps16k 镜像实测 p_align=4096 的扩展 dlopen 即 SIGSEGV）
                for align in elf_pt_load_aligns(data):
                    if align < 16384:
                        failures.append(
                            f"{wheel.name}:{name}: PT_LOAD p_align={align} <16384"
                            "——16KB page-size 设备不可加载"
                        )
                try:
                    needed = elf_dt_needed(data)
                    if mode == "rust" and libpython not in needed:
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
