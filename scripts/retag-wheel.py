#!/usr/bin/env python3
"""把 maturin 产出的 wheel 重标为 Chaquopy 认可的 Android 形态。

用法: retag-wheel.py <dist_dir> <android_abi> <python_version> <expected_platform_tag>

对齐 Chaquopy 官方仓库扩展 wheel 的实测形态（bcrypt cp312 android_21，2026-08-28 解剖）：
1. 文件名 tag：cp312-cp312-android_<api>_<abi>（PEP 738，非 abi3）；
2. 包内扩展 .so 用裸文件名（_pydantic_core.so），不带 cpython-312-<triple> 后缀；
3. （由 check-wheel-tag.py 断言）.so 的 DT_NEEDED 须含 libpython3.12.so —— 构建侧
   以空动态库 stub + -lpython3.12 产生该依赖，符号在运行时由 Chaquopy 的
   libpython3.12.so 解析。

幂等：已符合目标形态时原样通过。重标前断言 .so ELF machine 与 ABI 一致。
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
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


def rewrite_record(zin: zipfile.ZipFile, renames: dict[str, str]) -> bytes:
    """按 so 重命名同步 dist-info/RECORD（哈希与文件名）。"""
    record_name = next(n for n in zin.namelist() if n.endswith(".dist-info/RECORD"))
    rows = list(csv.reader(io.StringIO(zin.read(record_name).decode("utf-8"))))
    out_rows = []
    for row in rows:
        if not row:
            out_rows.append(row)
            continue
        name = row[0]
        if name in renames:
            data = zin.read(name)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            out_rows.append([renames[name], f"sha256={digest}", str(len(data))])
        else:
            out_rows.append(row)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(out_rows)
    return buf.getvalue().encode("utf-8")


def main() -> int:
    dist_dir = Path(sys.argv[1])
    abi = sys.argv[2]
    py_tag = f"cp{sys.argv[3].replace('.', '')}"
    expected_platform = sys.argv[4]
    bare_so_suffix = ".so"
    so_ext_pattern = re.compile(r"^(?P<base>.+?)(?:\.cpython-[\d]+[^/]*|\.abi3)?\.so$")

    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        print(f"FAIL: {dist_dir} 下没有 wheel")
        return 1

    expected_machine, desc = ABI_TO_ELF_MACHINE[abi]
    final_tag = f"{py_tag}-{py_tag}-{expected_platform}"
    final_name_pattern = re.compile(
        rf"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[^-]+)-{re.escape(final_tag)}\.whl$"
    )
    failures: list[str] = []

    for wheel in wheels:
        # 已处理过的（包内 so 已是裸名）且文件名正确 → 幂等通过
        already = False
        if final_name_pattern.match(wheel.name):
            with zipfile.ZipFile(wheel) as zf:
                already = not any(
                    re.search(r"\.cpython-[\d].*\.so$|\.abi3\.so$", n) for n in zf.namelist()
                )
        if already:
            print(f"PASS-THROUGH: {wheel.name} 已是目标形态")
            continue

        m = re.match(r"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[^-]+)-.+-[^-]+\.whl$", wheel.name)
        if not m:
            failures.append(f"{wheel.name}: 无法解析文件名结构")
            continue
        name, ver = m.group("name"), m.group("ver")

        # ELF machine 与目标 ABI 一致才允许处理
        renames: dict[str, str] = {}
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
            # 计划 so 重命名：去平台后缀，保留裸 .so
            for so in so_names:
                mm = so_ext_pattern.match(so.rsplit("/", 1)[-1])
                if mm and so.rsplit("/", 1)[-1] != mm.group("base") + bare_so_suffix:
                    renames[so] = so.rsplit("/", 1)[0] + "/" + mm.group("base") + bare_so_suffix \
                        if "/" in so else mm.group("base") + bare_so_suffix

        new_name = f"{name}-{ver}-{final_tag}.whl"
        dest = wheel.with_name(new_name)
        tmp = wheel.with_name(".retag-" + wheel.name)
        with zipfile.ZipFile(wheel) as zin, zipfile.ZipFile(
            tmp, "w", compression=zipfile.ZIP_DEFLATED
        ) as zout:
            record_new = rewrite_record(zin, renames) if renames else None
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(".dist-info/WHEEL"):
                    text = data.decode("utf-8")
                    text = re.sub(r"^Tag: .*$", f"Tag: {final_tag}", text, flags=re.M)
                    data = text.encode("utf-8")
                elif record_new is not None and item.filename.endswith(".dist-info/RECORD"):
                    data = record_new
                elif item.filename in renames:
                    item = zipfile.ZipInfo(renames[item.filename], date_time=item.date_time)
                    item.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(item, data)
        shutil.move(str(tmp), str(dest))
        wheel.unlink()
        extra = f"；so 重命名 {len(renames)} 个" if renames else ""
        print(f"RETAG: {wheel.name} -> {new_name}{extra}")

    if failures:
        print("\n".join(f"FAIL: {f}" for f in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
