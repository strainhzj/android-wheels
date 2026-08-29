# extra-wheels — 纯 Python sdist-only 依赖的预构建 wheel

后端 requirements 中仅以 sdist 发布、且其老式构建（distutils 等）在
Chaquopy 构建环境失败的纯 Python 包，在此以通用 wheel（py3-none-any）
形式随 PEP 503 索引一并分发（index job 会把本目录全部 wheel 并入索引）。

| 包 | 版本 | 原因 |
|---|---|---|
| bencodepy | 0.9.5 | sdist-only，distutils.core 构建（run 实测 No matching distribution） |

构建：`python -m pip wheel --no-deps --wheel-dir extra-wheels <pkg>==<ver>`
