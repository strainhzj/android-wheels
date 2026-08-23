# testapp — 最小 Chaquopy 验证 App

仅用于 Phase 0B.4 导入矩阵，不进入任何发布渠道。

## 首次准备（仓库初始化后执行一次）

```bash
# 1. 生成 gradle wrapper（wrapper jar 不入库，需本机有任意 gradle）
cd testapp && gradle wrapper --gradle-version 8.9

# 2. 本地运行时注入索引地址（CI 由 workflow 以 -P 参数注入）
echo "btdeck.wheels.index=https://<owner>.github.io/android-wheels/simple/" >> gradle.properties
```

## 运行

```bash
./gradlew :app:assembleDebug               # 构建即验证 pip 解析（wheel 缺失会在构建期明确报错）
./gradlew :app:connectedDebugAndroidTest   # 模拟器/真机上跑导入矩阵
```

## 结构

- `app/src/main/python/wheelcheck.py` — 导入/模型校验/FastAPI 冒烟（Python 侧判据）
- `app/src/androidTest/.../PythonImportTest.kt` — 仪表测试驱动，断言固定版本与结果
- 版本固定在 `versions.env` 与 `app/build.gradle.kts` 的 pip install 列表（两处需同步 PR）
