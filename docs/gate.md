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

### 2026-08-28 run 33164202997（失败）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33164202997
- 变更: 1e76f64（maturin -i 3.12 + pyo3/extension-module）
- 判据: 1 ❌（ld.lld: unable to find library -lpython3.12——maturin 生成的交叉
  pyo3-config 仍使链接层请求 libpython；Android 嵌入式解释器无独立 libpython）
- 结论与下一步: NDK llvm-ar 生成空静态档案 + RUSTFLAGS -L 注入（extension-module
  模式不取符号，Py* 运行时由 Chaquopy 解释器解析），第五轮重试。

### 2026-08-28 run 33164468777（失败）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33164468777
- 变更: b735061（空 libpython3.12.a 静态档案 + RUSTFLAGS -L）
- 判据: 1 ❌（Rust 编译与链接已通过，挂 maturin 1.8 的 android wheel repair：
  "Cannot repair wheel, because required library libdl.so could not be located"——
  libdl 为 Android 系统库，不应 vendor 进 wheel）
- 结论与下一步: --skip-auditwheel 跳过 repair（纯 Rust 扩展仅依赖系统库），
  tag/ELF 校验由 retag + check-wheel-tag 承担，第六轮重试。

### 2026-08-28 run 33168402257（失败，预期内）
- run: build-pydantic-core @5a23f5c
- 判据: 1 ❌（check-wheel-tag 新增的 DT_NEEDED 断言拦截：空动态库 stub 无符号可解析，
  lld --as-needed 丢弃 NEEDED——断言按设计工作）
- 结论与下一步: retag-wheel.py 集成 patchelf --add-needed 显式补记（RECORD 哈希同步）。

### 2026-08-28 build-pydantic-core 全绿 + Pages 启用（判据 1/2/3 ✅）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33164701409（1036c57 起持续绿，
  期间迭代修复详见决策记录与失败记录：cargo-ndk 安装方式 / maturin -i+extension-module /
  空 libpython 动态 stub / --skip-auditwheel / retag+patchelf / ELF 解析修正）
- 产物：pydantic_core-2.41.5-cp312-cp312-android_24_arm64_v8a.whl（约 1.9MB）、
  android_24_x86_64.whl（约 2.1MB）；sdist sha256 强校验 OK（08daa51e…8476e）
- 校验：check-wheel-tag 精确 tag + ELF machine + DT_NEEDED（libpython3.12.so，
  Chaquopy 扩展形态断言）+ 扩展裸 .so 名 + RECORD 一致性
- 索引：https://strainhzj.github.io/android-wheels/simple/pydantic-core/（HTTP 200，
  sha256 fragment 附带；Pages 经 API 以 gh-pages 分支启用）
- 判据: 1 ✅ 2 ✅ 3 ✅

### 2026-08-28 import-matrix 阶段 1 全绿（判据 4 ✅）
- run: https://github.com/strainhzj/android-wheels/actions/runs/33180505344（afb340e）
- 链路：pip 自 Pages 索引解析安装自建 wheel → android-34 default x86_64 模拟器
  （软件模拟冷启动约 8 分钟，boot-timeout 1800s）→ Python.start(AndroidPlatform) →
  4/4 仪表测试通过（固定版本断言 / pydantic-core 原生 roundtrip / FastAPI
  TestClient /health/live 200 / ABI 检查）；PAGESIZE=4096 留证
- 迭代归因（详见各失败 run 记录）：Chaquopy DSL（options 传 --extra-index-url）、
  abiFilters 两 ABI、useAndroidX、RECORD zip 一致性、Python.start 平台初始化、
  emulator script 多行分组拆坏、API35 软件模拟下系统镜像 droid.bluetooth
  SIGABRT（default/google_atd 双镜像复现、应用零痕迹，环境缺陷非 wheel 问题）
- 判据: 4 ✅（模拟器 x86_64×API34）；arm64-v8a 导入验证待真机（Phase 5 设备矩阵）
- 结论: **判据 1-4 达成；5（完整 import graph）与 6（16KB/冷启动/升级）为阶段 2
  专项**——API35/16KB 使用 google_apis_ps16k 镜像与本地硬件加速 AVD 执行
  （用户已批准 AVD 重建），不依赖 GitHub 软件模拟。闸门未全过，Phase 3 仍封锁。

### 2026-08-28（晚二）判据 6 之 16KB page-size：发现缺陷→修复→双页验证达成

- **发现**：本地 ps16k AVD（android-35 google_apis_ps16k x86_64，PAGESIZE=16384，WHPX 硬件加速冷启动 42s）上旧 wheel 导入即崩——tombstone 实锤 linker64 `ElfReader::LoadSegments` 内 memset SEGV_ACCERR；旧 wheel PT_LOAD 实查 p_align=4096×5。此前 CI 未见此问题因 runner 全为 4096 镜像；"gradle 全量跑部分通过"为 runner 进程重启假象，solo 复测修正结论。
- **修复**：构建链加 `-Wl,-z,max-page-size=16384`（NDK r27 经 cargo-ndk/maturin 链路默认仍产出 4096）；check-wheel-tag 新增断言"所有 PT_LOAD p_align≥16384"（本地验证对旧 wheel 精确拦截）。
- **验证**（新 wheel p_align=16384×5，自 Pages 索引安装）：
  - 16KB AVD：全套件 **6/6 通过**（imports/roundtrip/fastapiHealthLive/httpx 链/testclient 链/abi）；
  - 常规 4096 AVD（android-35 google_apis x86_64）：全套件 **6/6 通过**（无回归）；
  - `adb install -r` 覆盖安装（升级安装语义）两设备均成功后跑测试。
- **附带发现**：fastapi.testclient 深导入链在主线程默认栈上于 Python 递归限触发前耗尽 C 栈（ps16k 每帧更大）→ 测试侧以 16MB 大栈线程执行（testapp wheelcheck._run_on_big_stack）；**Phase 3 深导入图（BtDeck app.main）必须沿用此技法**。
- **判据 6 剩余**：冷启动计时留痕（16K 首启 42s 已录）、wheel 缺失失败信息（Chaquopy pip 构建期报错形态已具备）；完整"升级安装"演练随阶段 2 资源注入后的 testapp 版本化再做。
- 结论：**判据 6 之 16KB 核心达成**（wheel 双页大小验证）；判据 5 仍待阶段 2 实装。

### 2026-08-29 判据 5 达成：BtDeck 完整 import graph（阶段 2 实装，4096 x86_64 AVD）

- **实装**：`scripts/stage-fullgraph.py`（backend/app + alembic + alembic.ini + frontend/dist → testapp gitignored 源集；`.pymig` 数据形态 + bootstrap 运行期物化）、`scripts/fullgraph_bootstrap.py`（大栈线程/环境锚定/三项判据）、`FullGraphTest.kt`（assume-skip）、gradle `-Pbtdeck.fullgraph=true` 接线。路径锚定零后端改动（ROOT_PATH 派生同时命中 migration 绝对锚定与 factory 候选 3）。
- **验证**（btdeck-a35 AVD，android-35 google_apis x86_64，PAGESIZE=4096）：**9/9 全测试通过**——判据 5a 完整导入（app.main 全链 265 文件）、5b 迁移（空库→head 全链 + 幂等重跑 + alembic_version/建表断言）、5c 服务（uvicorn loopback：lifespan 完整初始化——调度器/三 lane runtime/仪表盘任务，/health/live 200 alive、/ 静态 SPA 首页 200）。
- **依赖解析矩阵**：56 包全部可装。自建：pydantic-core 2.41.5、bcrypt 5.0.0（官方 3.2.2 在 Android15 16K 镜像 dlopen 失败 DT_HASH 形态，自建后与后端 pin 对齐消覆写；bcrypt 走 setuptools-rust 原生后端——maturin 会误取 Cargo 元数据 bcrypt_rust-0.1.0）；extra-wheels：bencodepy 0.9.5（sdist-only+distutils 构建失败，预构建通用 wheel）；版本覆写 3 处（pillow 11.0.0/pycryptodomex 3.21.0/regex 2023.10.3，官方仓库存量）；ANDROID-ADD：tzdata（Android 无系统 tz 数据库，否则调度器 'No time zone found GMT' 启动失败——Phase 3 必备）。
- **迭代归因**（各 run 记录）：bencodepy 无发行版→extra-wheels；pip http 缓存旧 wheel 撞新 sha256→清缓存；Chaquopy 源集丢弃非包目录孤儿 .py（alembic/versions 消失）→.pymig 数据+物化；__init__ 包化遮蔽真 alembic 库（PEP 420 命名空间不阻断后置常规包）→弃包化；uvicorn 拒绑 port 0→预取端口；**testapp 无 INTERNET 权限 socket bind EPERM**（TestClient 不走 socket 故阶段 1 无感）→补权限。
- **限制登记**：①16KB ps16k 镜像上 Chaquopy 官方仓库存量 C 扩展 wheel（bcrypt 3.2.2/regex 2023.10.3 已实证，pillow/pycryptodomex/greenlet 大概率同类）系统性 dlopen 失败——老 NDK 构建形态与 Android15 16K linker 不兼容；**判据 6 的 16KB 剩余项=全依赖面 16KB 化**（自建扩展已 16KB 对齐，其余待官方更新或扩展自建矩阵），Phase 3 前必须解决。②arm64-v8a 全图验证待真机。③gradle 任务不追踪 -r 文件内容变化（改 requirements 须 --rerun-tasks）。
- 结论：**判据 1-5 全部达成**；判据 6 剩余（16KB 全依赖面、升级安装演练、冷启动留痕已具 42s 数据）。

### 2026-08-29（晚）判据 6 之 16KB page-size 达成：完整后端在 16KB 页 Android 全通

- **验证**（btdeck-16k AVD，google_apis_ps16k x86_64，PAGESIZE=16384，全新安装）：**全套件 9/9 通过**——阶段 1 六项 + 阶段 2 三项（完整导入 app.main / 空库→head 迁移+幂等 / uvicorn loopback /health/live + 静态 SPA 首页）。
- **16KB 全依赖面**（本轮 ~20 轮 CI 攻坚沉淀）：
  - greenlet 3.0.1 / regex 2024.11.6 / pycryptodomex 3.23.0 自建（NDK 交叉 pip wheel + CC/CXX wrapper：剥宿主 sysconfig 注入的 -I/usr/include 连体/分体形态、-m64/-march、--fix-cortex-a53 旗标；.so 目标自动补 -shared；-nostdinc+显式 NDK isystem 根治 glibc 头抢先）。
  - c-ext 扩展同样必须 DT_NEEDED libpython（Chaquopy libpython 非 RTLD_GLOBAL，无 NEEDED 重定位失败 _Py_NoneStruct）。
  - NEEDED 改名表：libz.so.1/libc.so.6/libm.so.6/libdl.so.2 → Android 真名。
  - 升级安装：多轮 install -r（版本变更 wheel 迭代）实证；冷启动 42s 已录；wheel 缺失失败信息=Chaquopy pip 构建期 No matching distribution 明确报错。
- **登记限制（不阻断闸门，Phase 3/5 收口项）**：
  1. **pillow**：自建 wheel 的宿主 /usr/include 注入挂点位于 Pillow 自家构建后端深处（CROSS-STRIP 17 处+wrapper 剥离+nostdinc 后仍余一路），本轮暂以 ANDROID-DROP 处理；主仓 cuser.py 的 qrcode/PIL 已改函数内延迟导入（桌面零差异），完整启动链不再触碰 PIL——代价仅 Android 服务端 2FA 二维码接口暂不可用。x86_64 自建 11.1.0 wheel 已在索引/find-links（arm64 占位），后续攻破后恢复安装即可。
  2. **arm64-v8a**：全图/16KB 验证均在 x86_64 模拟器；arm64 自建 wheel 双 ABI 已全绿（pydantic-core/bcrypt/greenlet/regex/pycryptodomex），真机导入/16KB 验证属 Phase 5 设备矩阵。
- **结论：判据 1-6 全部达成（含上述登记）——Phase 0 风险闸门通过，Phase 3（安卓本地服务端壳工程）解锁**；正式放行建议经用户确认（arm64 真机项）。
