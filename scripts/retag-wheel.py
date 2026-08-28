#!/usr/bin/env python3
"""把 maturin 产出的 wheel 重标为 Chaquopy 认可的 Android tag（PEP 738）。

用法: retag-wheel.py <dist_dir> <android_abi> <python_version> <expected_platform_tag>

背景（2026-08-28 首建修正）：
- maturin 对 android 目标产出的 platform tag 形态不保证与 Chaquopy 仓库一致；
  Chaquopy 官方仓库 cp312 wheel 实测形态为 `cp312-cp312-android_21_arm64_v8a`
  （版本专属 Python tag + PEP 738 android_<api>_<abi> 平台 tag，非 abi3）。
- 本脚本重写 *.dist-info/WHEEL 的 Tag 行并重命名文件为目标 tag；
  已符合目标 tag 时原样通过（幂等）。
- 重标前断言 .so 的 ELF machine 与目标 ABI 一致，防止跨 ABI 错标。
"""

from __future__ import annotations

import re
import shutil
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


def elf_machine(data: bytes) -> int:
    # ELF64/32 头：e_ident[16] + e_type@16(u16) + e_machine@18(u16)
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    return struct.unpack_from("<H", data, 18)[0]


def main() -> int:
    dist_dir = Path(sys.argv[1])
    abi = sys.argv[2]
    py_tag = f"cp{sys.argv[3].replace('.', '')}"
    expected_platform = sys.argv[4]

    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_dir} 下没有 wheel")
        return 1

    expected_machine, desc = ABI_TO_ELF_MACHINE[abi]
    final_tag = f"{py_tag}-{py_tag}-{expected_platform}"
    final_name_pattern = re.compile(
        rf"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[^-]+)-"
        rf"{re.escape(final_tag)}\.whl$"
    )
    failures: list[str] = []

    for wheel in wheels:
        if final_name_pattern.match(wheel.name):
            print(f"PASS-THROUGH: {wheel.name} 已是目标 tag")
            continue

        # 解析原文件名：<name>-<ver>[-build]-<py>-<abi>-<platform>.whl
        m = re.match(r"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[^-]+)-.+-[^-]+\.whl$", wheel.name)
        if not m:
            failures.append(f"{wheel.name}: 无法解析文件名结构")
            continue
        name, ver = m.group("name"), m.group("ver")

        # ELF machine 与目标 ABI 一致才允许重标
        with zipfile.ZipFile(wheel) as zf:
            so_names = [n for n in zf.namelist() if n.endswith(".so")]
            if not so_names:
                failures.append(f"{wheel.name}: 缺少 native .so")
                continue
            for so in so_names:
                machine = elf_machine(zf.read(so)[:64])
                if machine != expected_machine:
                    failures.append(f"{wheel.name}:{so}: ELF machine {machine} != {desc}({expected_machine})")
        if failures:
            continue

        new_name = f"{name}-{ver}-{final_tag}.whl"
        dest = wheel.with_name(new_name)

        # 重写 dist-info/WHEEL 的 Tag 行后重打包
        tmp = wheel.with_name(".retag-" + wheel.name)
        with zipfile.ZipFile(wheel) as zin, zipfile.ZipFile(
            tmp, "w", compression=zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(".dist-info/WHEEL"):
                    text = data.decode("utf-8")
                    text = re.sub(r"^Tag: .*$", f"Tag: {final_tag}", text, flags=re.M)
                    data = text.encode("utf-8")
                zout.writestr(item, data)
        shutil.move(str(tmp), str(dest))
        wheel.unlink()
        print(f"RETAG: {wheel.name} -> {new_name}")

    if failures:
        print("\n".join(f"FAIL: {f}" for f in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
