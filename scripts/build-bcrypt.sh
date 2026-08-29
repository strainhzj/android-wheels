#!/usr/bin/env bash
# 构建 bcrypt 的 Android wheel（单 ABI；由 GitHub Actions matrix 调用）。
# 与 build-pydantic-core.sh 同链路：maturin + cargo-ndk + NDK 交叉编译，
# 产物经 retag-wheel 对齐 Chaquopy 形态、check-wheel-tag 校验（含 16KB 对齐）。
# 动机：Chaquopy 官方 cp312 仅有 bcrypt 3.2.2，其 .so 在 Android 15 16K 镜像
# dlopen 失败（empty/missing DT_HASH/DT_GNU_HASH，fullgraph run 实证）；
# bcrypt 5.0.0 为 pyo3/Rust，直接对齐后端 ~=5.0.0 pin（消版本覆写）。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_DIR}/versions.env"

RUST_TARGET="${1:?usage: build-bcrypt.sh <rust-target> <android-abi>}"
ANDROID_ABI="${2:?usage: build-bcrypt.sh <rust-target> <android-abi>}"

: "${ANDROID_NDK_HOME:?需要 ANDROID_NDK_HOME（GitHub Actions 由 NDK 安装步骤提供）}"

echo "==> bcrypt ${BCRYPT_VERSION} for ${ANDROID_ABI} (${RUST_TARGET})"

# 1) 固定版本 sdist 下载 + hash 校验
SDIST="bcrypt-${BCRYPT_VERSION}.tar.gz"
curl -fsSLO "https://files.pythonhosted.org/packages/source/b/bcrypt/${SDIST}"
echo "${BCRYPT_SDIST_SHA256}  ${SDIST}" | sha256sum --check -
tar -xzf "${SDIST}"
cd "bcrypt-${BCRYPT_VERSION}"

# 2) NDK 交叉编译（llvm clang 链接器按 API level 命名）
TRIPLE_UPPER="${RUST_TARGET//-/_}"
TRIPLE_UPPER="${TRIPLE_UPPER^^}"
export "CARGO_TARGET_${TRIPLE_UPPER}_LINKER=${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin/${RUST_TARGET}${ANDROID_API_LEVEL}-clang"
export PYO3_CROSS_PYTHON_VERSION="${CHAQUOPY_PYTHON_VERSION}"
export PYO3_CROSS_PYTHON_IMPLEMENTATION=CPython

# 空 libpython 动态库 stub（同 pydantic-core：DT_NEEDED 记录 + 16KB 对齐）
STUB_DIR="${REPO_DIR}/dist/.pyo3-stub"
mkdir -p "${STUB_DIR}"
STUB_CC="${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin/clang"
: > "${STUB_DIR}/empty.c"
"${STUB_CC}" --target="${RUST_TARGET}${ANDROID_API_LEVEL}" -shared \
    -o "${STUB_DIR}/libpython${CHAQUOPY_PYTHON_VERSION}.so" "${STUB_DIR}/empty.c"
export RUSTFLAGS="-L ${STUB_DIR} -C link-arg=-Wl,-z,max-page-size=16384 ${RUSTFLAGS:-}"

maturin build --release \
    --target "${RUST_TARGET}" \
    -i "${CHAQUOPY_PYTHON_VERSION}" \
    --features pyo3/extension-module \
    --skip-auditwheel \
    --out "${REPO_DIR}/dist/${ANDROID_ABI}"

# 3) 重标 + 校验（tag/裸 so/DT_NEEDED/16KB 对齐）
TAG_KEY="ABI_${ANDROID_ABI//-/_}_TAG"
TAG_VAL="${!TAG_KEY:?versions.env 未回填 ${TAG_KEY}}"
python "${REPO_DIR}/scripts/retag-wheel.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" \
    "${CHAQUOPY_PYTHON_VERSION}" "${TAG_VAL}"

echo "==> wheel 产物："
ls -l "${REPO_DIR}/dist/${ANDROID_ABI}/"

export ANDROID_WHEEL_TAG="${TAG_VAL}"
python "${REPO_DIR}/scripts/check-wheel-tag.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" "${CHAQUOPY_PYTHON_VERSION}" bcrypt
