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

# NDK 交叉环境（clang wrapper 自带 --target 与 sysroot；API level 进链接语义）
export CC="${TOOLCHAIN}/${RUST_TARGET}${ANDROID_API_LEVEL}-clang"
export CXX="${TOOLCHAIN}/${RUST_TARGET}${ANDROID_API_LEVEL}-clang++"
export AR="${TOOLCHAIN}/llvm-ar"
export LD="${TOOLCHAIN}/ld"
export STRIP="${TOOLCHAIN}/llvm-strip"
export READELF="${TOOLCHAIN}/llvm-readelf"
# 16KB 对齐 + 允许未定义符号（扩展形态）
export CFLAGS="-Wl,-z,max-page-size=16384"
export CXXFLAGS="-Wl,-z,max-page-size=16384"
export LDFLAGS="-Wl,-z,max-page-size=16384"

pip wheel --no-deps -w "${REPO_DIR}/dist/${ANDROID_ABI}" .

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
