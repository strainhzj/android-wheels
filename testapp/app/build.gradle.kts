plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.btdeck.wheelstest"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.btdeck.wheelstest"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        ndk {
            // Chaquopy 官方错误实证（import-matrix run 33165163903）：
            // "Python 3.12 is not available for the ABI 'armeabi-v7a'.
            //  Supported ABIs are [arm64-v8a, x86_64]."
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

chaquopy {
    defaultConfig {
        // Android 目标 Python（与 versions.env 的 CHAQUOPY_PYTHON_VERSION 一致）
        version = "3.12"
        pip {
            // 本仓 GitHub Pages 索引：CI 以 -Pbtdeck.wheels.index=... 注入实际 owner。
            // Chaquopy 无 extraIndexUrls DSL 属性，pip 旗标统一经 options(...) 传
            options(
                "--extra-index-url",
                providers.gradleProperty("btdeck.wheels.index")
                    .orElse("https://example.github.io/android-wheels/simple/")
                    .get()
            )
            // 固定版本：pydantic-core 来自本仓索引，其余纯 Python 依赖来自 PyPI
            install("pydantic-core==2.41.5")
            install("pydantic==2.12.4")
            install("fastapi==0.115.6")
            install("uvicorn==0.35.0")
            // wheelcheck.check_fastapi_app 的 TestClient 依赖
            install("httpx==0.28.0")
            // 阶段 2（闸门判据 5）：BtDeck 完整 import graph——
            // 先 python scripts/stage-fullgraph.py，再 -Pbtdeck.fullgraph=true 构建
            if (providers.gradleProperty("btdeck.fullgraph").getOrElse("") == "true") {
                val req = rootProject.file("app/src/fullgraph/fullgraph-requirements.txt")
                if (req.exists()) {
                    options("-r", req.absolutePath)
                    // 自建 x86_64 wheel 本地候选（索引版本竞争会被官方同代胜出，
                    // find-links 直连文件候选参与最高版本裁决）；arm64 无本地候选
                    // 自然回落官方——pillow-arm64 链接谜题攻破后移除
                    options("--find-links", File(rootProject.projectDir, "../extra-wheels/local").absolutePath)
                } else {
                    throw GradleException("btdeck.fullgraph=true 但缺 ${req}——先运行 scripts/stage-fullgraph.py")
                }
            }
        }
    }
    productFlavors { }
    sourceSets {
        getByName("main") {
            if (providers.gradleProperty("btdeck.fullgraph").getOrElse("") == "true") {
                srcDir("src/fullgraph/python")
            }
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.13.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
