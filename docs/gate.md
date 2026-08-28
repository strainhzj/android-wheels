# Phase 0B 闸门判据与执行记录

> 对应 `PLANS/dual-mode-client.md`（BtDeck 主仓）第 3 节。
> 每次结论以新章节追加，不覆盖历史。

## 判据（全部满足才放行 Phase 3）

| # | 判据 | 证据形式 |
|---|---|---|
| 1 | pydantic-core cp312 wheels 构建成功（ABI 集合见下方修正），版本/hash 固定 | Actions run 链接 + versions.env 回填的 sha256 |
| 2 | wheel tag / ELF ABI / libc++ 链接经 `check-wheel-tag.py` 校验 | build job 日志 |
| 3 | PEP 503 索引发布 GitHub Pages，含 hash/SBOM/BUILD-INFO | Pages URL |
| 4 | 最小 Chaquopy 17 FastAPI + pydantic hello world（模拟器） | connectedDebugAndroidTest 通过 |
| 5 | BtDeck 完整 import graph 全部支持 ABI 安装/导入/`/health/live`/一次迁移/静态资源 | import-matrix full-graph run |
| 6 | 16 KB page-size、冷启动、升级安装、wheel 缺失明确失败信息 | 模拟器 API 35 run + 记录 |

> **ABI 集合修正（2026-08-28）**：原计划"四 ABI"（含 armeabi-v7a/x86）不可行——
> Chaquopy 15.0.1 changelog 明确 "The 32-bit ABIs armeabi-v7a and x86 will no
> longer be supported on Python 3.12 and later"，且官方仓库 cp312 wheel 实测
> 仅有 arm64_v8a / x86_64。Phase 0 目标矩阵收敛为 **arm64-v8a + x86_64**。

## 失败分支

任一判据失败 → BtDeck 服务端模式暂停，先交付伴侣模式（主仓 Phase 2），
并重估备选：Termux 方案 / 推迟服务端 / 裁剪后端能力清单。

## 决策记录

### 2026-08-28 首建修正轮（run 33163185434 / 33163406032 失败归因）

1. **cargo-ndk 安装方式**：cargo-ndk 只发布在 crates.io，PyPI 无此包
   （首建 run 33163185434 四 job 同步失败于 `pip install cargo-ndk==3.3.0`）。
   改为 `cargo install cargo-ndk --locked --version 3.3.0`（版本锚定不变）。
2. **maturin 无 `--abi3` CLI 参数**（run 33163406032 `unexpected argument '--abi3'`）；
   pydantic-core 2.41.5 sdist 的 Cargo.toml 亦无 abi3 feature。
   改为版本专属 wheel（cp312-cp312），与 Chaquopy 官方仓库形态一致。
3. **wheel tag 形态**：Chaquopy 官方仓库实测（bcrypt/regex cp312 wheel 文件名）
   为 `cp312-cp312-android_21_arm64_v8a`（PEP 738 `android_<api>_<abi>`）。
   本仓按 NDK API 24 构建锚定 `android_24_<abi>`，新增
   `scripts/retag-wheel.py` 在 maturin 产出后确定性重标（含 ELF machine 断言防错标）。
4. **PEP 503 索引路径**：URL 归一化必须用连字符（pip 请求
   `/simple/pydantic-core/`），`make-simple-index.py` 原下划线目录在静态 Pages
   上会 404，已修正。
5. **ABI 敏感依赖面收窄**：chaquo.com/pypi-13.1 官方仓库存量核查——
   bcrypt/regex/pillow/pycryptodomex 已有 Android wheel；gmssl 3.2.2 为
   py3-none-any 纯 Python wheel。唯一自建项 = pydantic-core。
6. **import-matrix 修正**：仓库不带 gradlew wrapper → CI 用
   gradle/actions/setup-gradle@v4 安装 Gradle 8.9；android-emulator-runner 在
   step 结束时关闭模拟器 → connectedDebugAndroidTest 移入其 script 块；
   索引地址经 `-Pbtdeck.wheels.index` 注入（原 local.properties 写法无人消费）；
   CI 模拟器仅 x86_64 可行（arm64 无 x86_64 宿主镜像），arm64-v8a 导入验证走真机。
7. **testapp AGP 8.5.2 → 8.7.3**：AGP 8.5 不支持 compileSdk 35
   （主仓 companion 工程已实证同样问题）。

## 执行记录

### 2026-08-28 run 33163185434（失败）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33163185434
- 变更: 无（ee65481 首推）
- 判据: 1 ❌（cargo-ndk 不在 PyPI，四 job 挂"安装构建工具"）3-6 未执行
- 结论与下一步: 见决策记录 #1。

### 2026-08-28 run 33163406032（失败）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33163406032
- 变更: 53e18e0（cargo-ndk 改 cargo install；import-matrix 三处修正；AGP 8.7.3）
- 判据: 1 ❌（maturin `--abi3` 参数不存在，四 job 挂"构建 wheel"）3-6 未执行
- 结论与下一步: 见决策记录 #2/#3；随后提交 abi3 移除 + retag + 两 ABI 矩阵 + versions.env 回填。

### 2026-08-28 run 33164038645（失败）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33164038645
- 变更: bdb09d7（去 --abi3 + retag + 两 ABI + versions.env 回填）
- 判据: 1 ❌（maturin 交叉模式不自动发现解释器：Couldn't find any python interpreters,
  请以 -i 指定；同时 sdist 无 [features] 表，需构建期 --features pyo3/extension-module
  防止扩展链接 libpython——Android 为嵌入式解释器，链接会在加载时产生双运行时）
- 结论与下一步: 修 maturin 调用（-i 3.12 + extension-module），第四轮重试。
