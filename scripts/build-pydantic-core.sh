#!/usr/bin/env bash
# 构建 pydantic-core 的 Android wheel（单 ABI；由 GitHub Actions matrix 调用）
# 约束：版本/hash 固定在 versions.env；cargo-ndk 提供 NDK 工具链布局，
# wheel tag/ABI/metadata 由 scripts/check-wheel-tag.py 强制校验。
# 注意：maturin 以 abi3 模式产出（cp312-abi3），平台 tag 必须是 Chaquopy
# 认可的 Android tag（首次 CI 回填 versions.env 后强制断言）。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../versions.env
source "${REPO_DIR}/versions.env"

RUST_TARGET="${1:?usage: build-pydantic-core.sh <rust-target> <android-abi>}"
ANDROID_ABI="${2:?usage: build-pydantic-core.sh <rust-target> <android-abi>}"

: "${ANDROID_NDK_HOME:?需要 ANDROID_NDK_HOME（GitHub Actions 由 NDK 安装步骤提供）}"

echo "==> pydantic-core ${PYDANTIC_CORE_VERSION} for ${ANDROID_ABI} (${RUST_TARGET})"
echo "    NDK=${ANDROID_NDK_VERSION} API=${ANDROID_API_LEVEL} python=cp${CHAQUOPY_PYTHON_VERSION//./}"

# 1) 固定版本 sdist 下载 + hash 校验（首次运行记录 hash 回填 versions.env 后强制）
SDIST="pydantic_core-${PYDANTIC_CORE_VERSION}.tar.gz"
curl -fsSLO "https://files.pythonhosted.org/packages/source/p/pydantic-core/${SDIST}"
if [[ "${PYDANTIC_CORE_SDIST_SHA256}" != TBD_FIRST_CI_RUN ]]; then
    echo "${PYDANTIC_CORE_SDIST_SHA256}  ${SDIST}" | sha256sum --check -
else
    echo "::warning::versions.env 尚未固定 sdist sha256，本次记录值（回填后强制校验）"
    sha256sum "${SDIST}"
fi
tar -xzf "${SDIST}"
cd "pydantic_core-${PYDANTIC_CORE_VERSION}"

# 2) NDK 交叉编译（llvm clang 链接器按 API level 命名：<target><api>-clang）
TRIPLE_UPPER="${RUST_TARGET//-/_}"
TRIPLE_UPPER="${TRIPLE_UPPER^^}"
export "CARGO_TARGET_${TRIPLE_UPPER}_LINKER=${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin/${RUST_TARGET}${ANDROID_API_LEVEL}-clang"
export PYO3_CROSS_PYTHON_VERSION="${CHAQUOPY_PYTHON_VERSION}"
export PYO3_CROSS_PYTHON_IMPLEMENTATION=CPython

maturin build --release \
    --target "${RUST_TARGET}" \
    --abi3 "cp${CHAQUOPY_PYTHON_VERSION//./}" \
    --out "${REPO_DIR}/dist/${ANDROID_ABI}"

echo "==> wheel 产物："
ls -l "${REPO_DIR}/dist/${ANDROID_ABI}/"

# 3) wheel tag / ELF ABI 校验（Android platform tag 基线确认）
python "${REPO_DIR}/scripts/check-wheel-tag.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" "${CHAQUOPY_PYTHON_VERSION}"
