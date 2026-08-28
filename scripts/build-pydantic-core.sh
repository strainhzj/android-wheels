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

# pydantic-core 无 abi3 Cargo feature（2.41.5 sdist 实查），按版本专属 wheel 构建；
# -i 3.12：交叉模式下 maturin 不自动发现解释器，需显式给目标版本（run 33164038645 实证）；
# --features pyo3/extension-module：Android 为嵌入式解释器，扩展不得链接 libpython
#   （sdist Cargo.toml 无 [features] 表，官方构建同样在构建期启用该 feature）
# pyo3 链接层在交叉配置下仍请求 -lpython3.12（run 33164202997 实证；Android 为
# 嵌入式解释器，无独立 libpython 共享库可链）。提供空静态档案满足 -l 解析：
# extension-module 模式不从档案取任何符号，Py* 符号保持未定义、由 Chaquopy
# 运行时内嵌解释器解析。经 RUSTFLAGS -L 注入搜索路径（maturin 会在 cargo 调用
# 中显式覆盖 PYO3_CONFIG_FILE/PYO3_CROSS_LIB_DIR，环境变量路线不可靠）。
STUB_DIR="${REPO_DIR}/dist/.pyo3-stub"
mkdir -p "${STUB_DIR}"
"${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-ar" crs \
    "${STUB_DIR}/libpython${CHAQUOPY_PYTHON_VERSION}.a"
export RUSTFLAGS="-L ${STUB_DIR} ${RUSTFLAGS:-}"

maturin build --release \
    --target "${RUST_TARGET}" \
    -i "${CHAQUOPY_PYTHON_VERSION}" \
    --features pyo3/extension-module \
    --out "${REPO_DIR}/dist/${ANDROID_ABI}"

# 2b) 重标为 Chaquopy 认可的 PEP 738 tag：cp312-cp312-android_<api>_<abi>
TAG_KEY="ABI_${ANDROID_ABI//-/_}_TAG"
TAG_VAL="${!TAG_KEY:-}"
if [[ -z "${TAG_VAL}" || "${TAG_VAL}" == TBD* ]]; then
    echo "::error::versions.env 未回填 ${TAG_KEY}（预期 android_<api>_<abi> 形态）"
    exit 1
fi
python "${REPO_DIR}/scripts/retag-wheel.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" \
    "${CHAQUOPY_PYTHON_VERSION}" "${TAG_VAL}"

echo "==> wheel 产物："
ls -l "${REPO_DIR}/dist/${ANDROID_ABI}/"

# 3) wheel tag / ELF ABI 校验（精确匹配 versions.env 回填值）
export ANDROID_WHEEL_TAG="${TAG_VAL}"
python "${REPO_DIR}/scripts/check-wheel-tag.py" \
    "${REPO_DIR}/dist/${ANDROID_ABI}/" "${ANDROID_ABI}" "${CHAQUOPY_PYTHON_VERSION}"
