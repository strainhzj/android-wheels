#!/usr/bin/env bash
# 构建 setuptools 系 C/C++ 扩展的 Android wheel（单 ABI；CI matrix 调用）。
# 与 Rust 系不同：走 NDK clang 交叉 + pip wheel（包自身构建后端），产物经
# retag 对齐 Chaquopy 形态、check-wheel-tag 校验（c-ext 模式：不强制
# DT_NEEDED libpython——CPython 扩展标准形态即不链 libpython，Py 符号运行时
# 由 Chaquopy libpython 解析）。
# 动机：Chaquopy 官方仓库存量 wheel（老 NDK 构建）在 Android15 16K 镜像上
# dlopen 系统性失败（bcrypt 3.2.2/regex 2023.10.3 实证）。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_DIR}/versions.env"

PKG="${1:?usage: build-ndk-cext.sh <pkg> <rust-target> <android-abi>}"
RUST_TARGET="${2:?<rust-target>}"
ANDROID_ABI="${3:?<android-abi>}"

: "${ANDROID_NDK_HOME:?需要 ANDROID_NDK_HOME}"

# 包名 → versions.env 变量名（greenlet → GREENLET_VERSION / GREENLET_SDIST_SHA256）
VAR_PREFIX="$(echo "${PKG}" | tr '[:lower:]-' '[:upper:]_')"
VER_VAR="${VAR_PREFIX}_VERSION"
SHA_VAR="${VAR_PREFIX}_SDIST_SHA256"
PKG_VER="${!VER_VAR:?versions.env 未定义 ${VER_PREFIX}_VERSION}"
PKG_SHA="${!SHA_VAR:?versions.env 未定义 ${SHA_VAR}}"

echo "==> ${PKG} ${PKG_VER} for ${ANDROID_ABI} (${RUST_TARGET})"
TOOLCHAIN="${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin"

SDIST="${PKG}-${PKG_VER}.tar.gz"
curl -fsSLO "https://files.pythonhosted.org/packages/source/${PKG:0:1}/${PKG}/${SDIST}"
echo "${PKG_SHA}  ${SDIST}" | sha256sum --check -
tar -xzf "${SDIST}"
cd "${PKG}-${PKG_VER}"

# NDK 交叉环境（clang wrapper 自带 --target 与 sysroot；API level 进链接语义）。
# CC/CXX 经中间包装器：剥离宿主 Python sysconfig CFLAGS 注入的 -I/usr/include
# 等 glibc 路径（与 NDK sysroot 头冲突是唯一致命项；对一切注入来源生效）
REAL_CC="${TOOLCHAIN}/${RUST_TARGET}${ANDROID_API_LEVEL}-clang"
REAL_CXX="${TOOLCHAIN}/${RUST_TARGET}${ANDROID_API_LEVEL}-clang++"
make_wrapper() {
    local real="$1" out="$2"
    {
        echo '#!/bin/bash'
        echo 'args=()'
        echo 'for a in "$@"; do'
        echo '  case "$a" in'
        echo '    -I/usr/include|-I/usr/local/include|-I/usr/include/x86_64-linux-gnu) ;;'
        echo '    --fix-cortex-a53-843419|-Wl,--fix-cortex-a53-843419) ;;'
        echo '    -m64|-m32|-march=*|-mtune=*) ;;'
        echo '    *) args+=("$a");;'
        echo '  esac'
        echo 'done'
        # 输出为 .so 时确保 -shared（宿主 LDSHARED 自带而 wrapper 透传丢失；
        # 缺失时 lld 按可执行链 → undefined symbol: main/PyModule_Create2）
        echo 'out=""; prev="";'
        echo 'for a in "${args[@]}"; do'
        echo '  if [ "$prev" = "-o" ]; then out="$a"; fi'
        echo '  prev="$a"'
        echo 'done'
        # 诊断：完整 argv 回显（链接谜题归因用，稳定后可移除）
        echo 'echo "WRAPPER-ARGV: ${args[*]}" >&2'
        echo 'if [[ "$out" == *.so && " ${args[*]} " != *" -shared "* ]]; then'
        echo '  exec "'"${real}"'" --target='"${RUST_TARGET}${ANDROID_API_LEVEL}"' -shared "${args[@]}"'
        echo 'fi'
        echo "exec '${real}' --target=${RUST_TARGET}${ANDROID_API_LEVEL} "'"${args[@]}"'
    } > "${out}"
    chmod +x "${out}"
}
WRAP_DIR="$(mktemp -d)"
make_wrapper "${REAL_CC}" "${WRAP_DIR}/cc"
make_wrapper "${REAL_CXX}" "${WRAP_DIR}/cxx"
export CC="${WRAP_DIR}/cc"
export CXX="${WRAP_DIR}/cxx"
export AR="${TOOLCHAIN}/llvm-ar"
export LD="${TOOLCHAIN}/ld"
export STRIP="${TOOLCHAIN}/llvm-strip"
export READELF="${TOOLCHAIN}/llvm-readelf"
# 16KB 对齐 + 允许未定义符号（扩展形态）；
# 前置 NDK sysroot include：宿主 Python sysconfig 会注入 -I/usr/include 等
# glibc 路径（platform-guessing=disable 也拦不住，pillow run 实证），
# 让 NDK 的 stdlib.h 等先行命中即可绕开 bits/* 冲突（-I 按命令序生效）
SYSROOT="${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/sysroot"
export CFLAGS="-I${SYSROOT}/usr/include/${RUST_TARGET} -I${SYSROOT}/usr/include -Wl,-z,max-page-size=16384"
export CXXFLAGS="-I${SYSROOT}/usr/include/${RUST_TARGET} -I${SYSROOT}/usr/include -Wl,-z,max-page-size=16384"
export LDFLAGS="-Wl,-z,max-page-size=16384"

if [[ "${PKG}" == "pillow" ]]; then
    # pillow 自定义后端的 .so 链接显式走宿主 LDSHARED（x86 gcc + --fix-cortex
    # 旗标，arm64 挂点）——指到 wrapper 的 clang；其余包链接经 CC/CXX 派生，
    # 全局覆盖会破坏其可执行特性探测（undefined symbol: main，run 实证）
    export LDSHARED="${WRAP_DIR}/cc"
    export LDCXXSHARED="${WRAP_DIR}/cxx"
    # 外科手术：摘除 setup.py 中全部绝对路径的 include/library 注入
    # （sdist 与 git tag 文本有差异，精确串不可靠；/usr/include 的 glibc 头
    # 与 NDK sysroot 冲突是唯一致命项，运行实证 platform-guessing 只护一段）
    python3 - <<'SED'
import re, pathlib
p = pathlib.Path("setup.py")
src = p.read_text(encoding="utf-8")
pattern = re.compile(
    r'(?m)^(?P<indent>[ \t]*)_add_directory\((include_dirs|library_dirs), "/[^"]*"\)\s*$'
)
src, n = pattern.subn(
    lambda m: f"{m.group('indent')}pass  # CROSS-STRIPPED ({m.group(2)})",
    src,
)
print(f"CROSS-STRIPPED {n} host-path injections")
p.write_text(src, encoding="utf-8")
SED
    # Pillow 11 的 jpeg 默认强制依赖；经其自定义后端的 config-settings 禁用全部
    # 可选特性、仅留 zlib（NDK sysroot 自带 zlib.h/libz；PNG 即 qrcode 场景所需），
    # 并关平台猜测。官方 wheel 链私有 libjpeg_chaquopy.so 在 16K 镜像找不到——
    # 自建静态化规避。其自定义构建后端在隔离环境会丢交叉 CC 链路，
    # 故 --no-build-isolation。
    PIP_CONFIG_FLAGS=(
        -C jpeg=disable -C jpeg2000=disable -C tiff=disable
        -C freetype=disable -C lcms=disable -C webp=disable -C xcb=disable
        -C platform-guessing=disable
        --no-build-isolation
    )
    pip install -q setuptools wheel
else
    PIP_CONFIG_FLAGS=()
fi

pip wheel --no-deps "${PIP_CONFIG_FLAGS[@]}" -w "${REPO_DIR}/dist/${ANDROID_ABI}" .

# 重标 + 校验（c-ext 模式）
TAG_KEY="ABI_${ANDROID_ABI//-/_}_TAG"
TAG_VAL="${!TAG_KEY:?versions.env 未回填 ${TAG_KEY}}"
python "${REPO_DIR}/scripts/retag-wheel.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" \
    "${CHAQUOPY_PYTHON_VERSION}" "${TAG_VAL}" c-ext

echo "==> wheel 产物："
ls -l "${REPO_DIR}/dist/${ANDROID_ABI}/"

export ANDROID_WHEEL_TAG="${TAG_VAL}"
python "${REPO_DIR}/scripts/check-wheel-tag.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" "${CHAQUOPY_PYTHON_VERSION}" \
    "${PKG}" c-ext
