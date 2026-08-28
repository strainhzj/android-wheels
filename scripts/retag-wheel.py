#!/usr/bin/env python3
"""把 maturin 产出的 wheel 重标为 Chaquopy 认可的 Android 形态。

用法: retag-wheel.py <dist_dir> <android_abi> <python_version> <expected_platform_tag>

对齐 Chaquopy 官方仓库扩展 wheel 的实测形态（bcrypt cp312 android_21，2026-08-28 解剖）：
1. 文件名 tag：cp312-cp312-android_<api>_<abi>（PEP 738，非 abi3）；
2. 包内扩展 .so 用裸文件名（_pydantic_core.so），不带 cpython-312-<triple> 后缀；
3. .so 的 DT_NEEDED 须含 libpython3.12.so —— Py 符号运行时由 Chaquopy 内嵌的
   libpython3.12.so 解析。链接期空 stub 无符号可解析，lld --as-needed 会丢弃
   NEEDED（run 33168402257 实证），故经 patchelf --add-needed 显式补记；
   RECORD 哈希随内容同步更新。

幂等：已符合目标形态时原样通过。处理前断言 .so ELF machine 与 ABI 一致。
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import shutil
import struct
import subprocess
import sys
import tempfile
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


def patchelf_add_needed(data: bytes, libname: str) -> bytes:
    """经 patchelf 给 .so 补 DT_NEEDED（patchelf 由 CI pip 安装）。"""
    with tempfile.TemporaryDirectory() as td:
        so = Path(td) / "lib.so"
        so.write_bytes(data)
        subprocess.run(
            ["patchelf", "--add-needed", libname, str(so)],
            check=True,
            capture_output=True,
        )
        return so.read_bytes()


def main() -> int:
    dist_dir = Path(sys.argv[1])
    abi = sys.argv[2]
    py_tag = f"cp{sys.argv[3].replace('.', '')}"
    expected_platform = sys.argv[4]
    libpython = f"libpython{sys.argv[3]}.so"
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
        # 目标形态 = 文件名正确 + 包内 so 裸名 + NEEDED 含 libpython
        if final_name_pattern.match(wheel.name):
            with zipfile.ZipFile(wheel) as zf:
                ok_form = not any(
                    re.search(r"\.cpython-[\d].*\.so$|\.abi3\.so$", n) for n in zf.namelist()
                )
                ok_needed = all(
                    libpython in elf_dt_needed(zf.read(n))
                    for n in zf.namelist() if n.endswith(".so")
                )
            if ok_form and ok_needed:
                print(f"PASS-THROUGH: {wheel.name} 已是目标形态")
                continue

        m = re.match(r"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[^-]+)-.+-[^-]+\.whl$", wheel.name)
        if not m:
            failures.append(f"{wheel.name}: 无法解析文件名结构")
            continue
        name, ver = m.group("name"), m.group("ver")

        # 更新计划：{原路径: (新路径 or None, 新内容 or None)}
        so_updates: dict[str, tuple[str | None, bytes | None]] = {}
        with zipfile.ZipFile(wheel) as zf:
            so_names = [n for n in zf.namelist() if n.endswith(".so")]
            if not so_names:
                failures.append(f"{wheel.name}: 缺少 native .so")
                continue
            for so in so_names:
                data = zf.read(so)
                machine = elf_machine(data[:64])
                if machine != expected_machine:
                    failures.append(f"{wheel.name}:{so}: ELF machine {machine} != {desc}({expected_machine})")
                    continue
                new_path = None
                base = so.rsplit("/", 1)[-1]
                mm = so_ext_pattern.match(base)
                bare = mm.group("base") + ".so"
                if base != bare:
                    new_path = (so.rsplit("/", 1)[0] + "/" + bare) if "/" in so else bare
                new_data = None
                try:
                    needed_missing = libpython not in elf_dt_needed(data)
                except ValueError:
                    needed_missing = True  # 异常形态（无动态段等）→ 交 patchelf 处理
                if needed_missing:
                    try:
                        new_data = patchelf_add_needed(data, libpython)
                    except FileNotFoundError:
                        failures.append(
                            f"{wheel.name}:{so}: DT_NEEDED 缺 {libpython} 且本机无 patchelf"
                            "（CI 由 pip install patchelf 提供）"
                        )
                        continue
                    except subprocess.CalledProcessError as exc:
                        failures.append(f"{wheel.name}:{so}: patchelf 失败 {exc.stderr!r}")
                        continue
                if new_path or new_data is not None:
                    so_updates[so] = (new_path, new_data)
            if failures:
                continue

        new_name = f"{name}-{ver}-{final_tag}.whl"
        dest = wheel.with_name(new_name)
        tmp = wheel.with_name(".retag-" + wheel.name)
        with zipfile.ZipFile(wheel) as zin, zipfile.ZipFile(
            tmp, "w", compression=zipfile.ZIP_DEFLATED
        ) as zout:
            record_name = next(
                (n for n in zin.namelist() if n.endswith(".dist-info/RECORD")), None
            )
            record_new: bytes | None = None
            if record_name and so_updates:
                rows = list(csv.reader(io.StringIO(zin.read(record_name).decode("utf-8"))))
                # 键必须按 RECORD 行里的原始（旧）路径匹配：行内是旧名，
                # so_updates 的 key 也是旧名（值才是新名/新内容）
                overrides = {}
                for old, (new_path, new_data) in so_updates.items():
                    payload = new_data if new_data is not None else zin.read(old)
                    overrides[old] = (new_path or old, payload)
                out_rows = []
                for row in rows:
                    if not row:
                        out_rows.append(row)
                        continue
                    fname = row[0]
                    if fname in overrides:
                        new_fname, payload = overrides[fname]
                        digest = base64.urlsafe_b64encode(
                            hashlib.sha256(payload).digest()
                        ).rstrip(b"=").decode()
                        out_rows.append([new_fname, f"sha256={digest}", str(len(payload))])
                    else:
                        out_rows.append(row)
                buf = io.StringIO()
                csv.writer(buf, lineterminator="\n").writerows(out_rows)
                record_new = buf.getvalue().encode("utf-8")
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(".dist-info/WHEEL"):
                    text = data.decode("utf-8")
                    text = re.sub(r"^Tag: .*$", f"Tag: {final_tag}", text, flags=re.M)
                    data = text.encode("utf-8")
                elif record_new is not None and item.filename.endswith(".dist-info/RECORD"):
                    data = record_new
                elif item.filename in so_updates:
                    new_path, new_data = so_updates[item.filename]
                    if new_data is not None:
                        data = new_data
                    if new_path:
                        item = zipfile.ZipInfo(new_path, date_time=item.date_time)
                        item.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(item, data)
        shutil.move(str(tmp), str(dest))
        wheel.unlink()
        n_rename = sum(1 for _, (np_, _) in so_updates.items() if np_)
        n_patch = sum(1 for _, (_, nd) in so_updates.items() if nd is not None)
        print(f"RETAG: {wheel.name} -> {new_name}（so 改名 {n_rename}、补 NEEDED {n_patch}）")

    if failures:
        print("\n".join(f"FAIL: {f}" for f in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
