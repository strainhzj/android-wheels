# Phase 0B 闸门判据与执行记录

> 对应 `PLANS/dual-mode-client.md`（BtDeck 主仓）第 3 节。
> 每次结论以新章节追加，不覆盖历史。

## 判据（全部满足才放行 Phase 3）

| # | 判据 | 证据形式 |
|---|---|---|
| 1 | 四 ABI `pydantic-core` cp312 wheels 构建成功，版本/hash 固定 | Actions run 链接 + versions.env 回填的 sha256 |
| 2 | wheel tag / ELF ABI / libc++ 链接经 `check-wheel-tag.py` 校验 | build job 日志 |
| 3 | PEP 503 索引发布 GitHub Pages，含 hash/SBOM/BUILD-INFO | Pages URL |
| 4 | 最小 Chaquopy 17 FastAPI + pydantic hello world（模拟器） | connectedDebugAndroidTest 通过 |
| 5 | BtDeck 完整 import graph 四 ABI 安装/导入/`/health/live`/一次迁移/静态资源 | import-matrix full-graph run |
| 6 | 16 KB page-size、冷启动、升级安装、wheel 缺失明确失败信息 | 模拟器 API 35 run + 记录 |

## 失败分支

任一判据失败 → BtDeck 服务端模式暂停，先交付伴侣模式（主仓 Phase 2），
并重估备选：Termux 方案 / 推迟服务端 / 裁剪后端能力清单。

## 执行记录

### （待首次 CI 运行后追加）

模板：

```markdown
## YYYY-MM-DD <结论：通过/失败/部分>
- run: <Actions 链接>
- 变更: <versions.env 变更 diff>
- 判据: 1 ✅ 2 ✅ 3 ✅ 4 ❌ ...
- 结论与下一步: <...>
```
