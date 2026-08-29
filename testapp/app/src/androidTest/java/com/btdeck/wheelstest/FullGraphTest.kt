package com.btdeck.wheelstest

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.PyException
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.BeforeClass
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Phase 0B.4 阶段 2（闸门判据 5）：BtDeck 完整 import graph。
 *
 * 资源由 `scripts/stage-fullgraph.py` 注入 `app/src/fullgraph/`（gitignored），
 * 未 staging 时整体 assumeTrue 跳过——普通构建/CI 不受影响。
 * 运行：gradle :app:connectedDebugAndroidTest -Pbtdeck.fullgraph=true
 */
@RunWith(AndroidJUnit4::class)
class FullGraphTest {

    companion object {
        private var staged = false

        @BeforeClass
        @JvmStatic
        fun startPython() {
            if (!Python.isStarted()) {
                Python.start(
                    AndroidPlatform(InstrumentationRegistry.getInstrumentation().targetContext)
                )
            }
            staged = try {
                Python.getInstance().getModule("fullgraph_bootstrap")
                true
            } catch (e: PyException) {
                false
            }
        }
    }

    private fun run(check: String): JSONObject {
        assumeTrue("fullgraph 未 staging（先跑 scripts/stage-fullgraph.py）", staged)
        val raw = Python.getInstance()
            .getModule("fullgraph_bootstrap").callAttr(check).toString()
        return JSONObject(raw)
    }

    @Test
    fun fullImportGraph() {
        val result = run("check_import")
        assertTrue(result.getBoolean("ok"))
        assertTrue("版本缺失", result.optString("version").isNotEmpty())
    }

    @Test
    fun fullMigration() {
        val result = run("check_migration")
        assertTrue(result.getBoolean("ok"))
        assertTrue(
            "迁移链版本异常: ${result}",
            result.optString("version").matches(Regex("[0-9a-f]{12}"))
        )
        assertTrue("建表数异常: ${result}", result.getInt("tables") >= 10)
    }

    @Test
    fun fullServer() {
        val result = run("check_server")
        assertTrue(result.getBoolean("ok"))
        assertEquals("alive", result.getJSONObject("live").optString("status"))
        assertTrue("静态首页过小", result.getInt("index_bytes") > 500)
    }
}
