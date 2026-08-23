# btdeck/android-wheels — Android 预编译 wheel 仓库（Phase 0B 风险闸门）

> 对应计划：`PLANS/dual-mode-client.md`（BtDeck 主仓）第 3 节 Phase 0B。
> **本仓库是闸门本体**：所有 ABI 均能安装、导入、启动 `/health/live`、完成一次
> 数据库迁移与前端静态资源加载，才允许 BtDeck 进入安卓服务端工程（Phase 3）。

## 目标

1. 用 GitHub Actions + `cargo-ndk` 构建固定版本、固定 hash 的 `pydantic-core`
   cp312 Android wheels：`arm64-v8a`、`armeabi-v7a`、`x86_64`、`x86`。
2. 正确的 Android wheel tag / Python ABI / NK API level / libc++ 链接 / wheel
   metadata —— `cargo-ndk` 只解决 native 编译，不替代 wheel 打包与索引验证。
3. GitHub Pages 发布 PEP 503 simple index；保留 wheel hash、构建日志、
   SBOM/license、源码与工具链版本。
4. 验证链路：最小 Chaquopy 17 FastAPI + pydantic hello world → BtDeck 完整
   import graph（四 ABI 矩阵）→ 16 KB page-size / 冷启动 / 升级安装 /
   wheel 缺失明确失败。

## 布局

```text
versions.env                 # 所有固定版本与 hash（单一来源，改动需走 PR）
scripts/build-pydantic-core.sh
scripts/make-simple-index.py # 生成 PEP 503 索引（含 sha256）
.github/workflows/build-pydantic-core.yml   # 构建 + 发布 Pages 索引
.github/workflows/import-matrix.yml         # Chaquopy 导入矩阵（模拟器）
testapp/                     # 最小 Chaquopy 验证 App（FastAPI+pydantic hello world）
docs/gate.md                 # 闸门判据与执行记录（每次 CI 结论追加）
```

## 使用（BtDeck Android 侧消费方式，Phase 3 落地）

```python
# Chaquopy build.gradle.kts
chaquopy {
    defaultConfig {
        pip {
            extraIndexUrls("https://<owner>.github.io/android-wheels/simple/")
            install("pydantic-core==<versions.env 中固定版本>")
        }
    }
}
```

## 语义约束（与 Chaquopy 官方一致）

- [Chaquopy 版本兼容矩阵](https://chaquo.com/chaquopy/doc/current/versions.html)
- [自定义 wheels FAQ](https://chaquo.com/chaquopy/doc/current/faq.html)
- [Chaquopy wheel 索引说明](https://github.com/chaquo/chaquopy/blob/master/server/pypi/README.md)
- Android wheel 的 platform tag、NDK/API level、libc++（c++_shared）链接要求
  以 Chaquopy 文档为准；**首次 CI 运行即验证**，`versions.env` 中的 tag
  参数是待验证基线，不是既成事实。

## 状态

- [ ] pydantic-core 四 ABI wheels 构建成功（tag/ABI/链接方式经 CI 验证）
- [ ] PEP 503 索引发布 GitHub Pages（含 hash/SBOM/license）
- [ ] 最小 Chaquopy hello world（四 ABI）
- [ ] BtDeck 完整 import graph（四 ABI）
- [ ] `/health/live` + 一次迁移 + 静态资源加载
- [ ] 16 KB page-size / 冷启动 / 升级安装 / wheel 缺失失败信息
- [ ] 闸门结论登记（docs/gate.md）

**以上任何一项未完成前，BtDeck 主仓不得启动 Phase 3。**
