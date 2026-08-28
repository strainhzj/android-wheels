package com.btdeck.wheelstest

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Phase 0B.4 导入矩阵判据（connectedDebugAndroidTest）：
 * 1. pydantic/pydantic_core/fastapi 可导入且版本与 versions.env 固定值一致；
 * 2. pydantic-core native 校验路径（Rust 扩展）真实执行；
 * 3. 最小 FastAPI 应用 /health/live 返回 200。
 */
@RunWith(AndroidJUnit4::class)
class PythonImportTest {

    companion object {
        /** Chaquopy 17 要求先 Python.start(AndroidPlatform)（run 33171733060 实证）。 */
        @BeforeClass
        @JvmStatic
        fun startPython() {
            if (!Python.isStarted()) {
                Python.start(
                    AndroidPlatform(InstrumentationRegistry.getInstrumentation().targetContext)
                )
            }
        }
    }

    private fun py() = Python.getInstance()

    @Test
    fun importsMatchPinnedVersions() {
        // 不用 asMap()：其无推断依据的泛型签名会让 Kotlin 编译失败
        // （run 33165645655 实证），改为按名取版本的字符串接口
        val wc = py().getModule("wheelcheck")
        assertEquals("2.41.5", wc.callAttr("check_imports_str", "pydantic_core").toString())
        assertEquals("2.12.4", wc.callAttr("check_imports_str", "pydantic").toString())
        assertEquals("0.115.6", wc.callAttr("check_imports_str", "fastapi").toString())
    }

    @Test
    fun pydanticCoreNativeRoundtrip() {
        val result = py().getModule("wheelcheck").callAttr("check_model_roundtrip").toString()
        assertEquals("ok", result)
    }

    @Test
    fun fastapiHealthLive() {
        val status = py().getModule("wheelcheck").callAttr("check_fastapi_app").toString()
        assertEquals("ok", status)
    }

    @Test
    fun abiAndPageSize() {
        // 16 KB page-size 兼容性（Android 15+/API 35 镜像）留证
        val abi = android.os.Build.SUPPORTED_ABIS.firstOrNull()
        assertTrue("unexpected ABI: $abi", abi in setOf("arm64-v8a", "x86_64", "armeabi-v7a", "x86"))
    }
}
