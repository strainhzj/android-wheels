// 最小 Chaquopy 验证 App（Phase 0B.4：FastAPI + pydantic hello world 导入矩阵）
// 版本以 docs/../versions.env 与 Chaquopy 官方矩阵为准；首次 CI 运行校验。
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.20" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
