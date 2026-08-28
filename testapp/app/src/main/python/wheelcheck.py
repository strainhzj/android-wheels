# -*- coding: utf-8 -*-
"""Chaquopy 导入矩阵的 Python 侧检查点（Phase 0B.4）。

由 androidTest 的 PythonImportTest 调用；每一步失败都抛异常，
失败信息即"wheel 缺失时的明确失败信息"验收材料。
"""


def check_imports() -> dict:
    import pydantic_core
    import pydantic
    import fastapi

    return {
        "pydantic_core": pydantic_core.__version__,
        "pydantic": pydantic.VERSION,
        "fastapi": fastapi.__version__,
    }


def check_imports_str(name: str) -> str:
    """按包名返回固定版本（Kotlin 侧经 callAttr 消费，规避 asMap 泛型推断）。"""
    return check_imports()[name]


def check_model_roundtrip() -> str:
    """pydantic-core native 路径冒烟：模型构建 + 校验 + 序列化。"""
    from pydantic import BaseModel

    class Model(BaseModel):
        name: str
        port: int

    m = Model(name="btdeck", port=5001)
    assert m.model_dump() == {"name": "btdeck", "port": 5001}
    return Model.model_validate_json('{"name":"ok","port":1}').name


def check_fastapi_app() -> str:
    """阶段 1 hello world 判据：最小 FastAPI + TestClient /health/live 200。"""

    def _do():
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/health/live")
        def live() -> dict:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/health/live")
        assert response.status_code == 200, response.text
        return response.json()["status"]

    return _run_on_big_stack(_do)


def _run_on_big_stack(fn, stack_bytes: int = 16 * 1024 * 1024):
    """在大栈线程中执行 fn。

    ps16k 镜像实证（2026-08-28）：fastapi→pydantic→pydantic_core→typing_extensions
    模块初始化含 typing.Optional/Union 超深一次性求值；ps16k 构建的每帧 C 栈消耗
    更大，主线程默认栈在 Python 递归限触发前先耗尽（硬崩溃而非 RecursionError）。
    API34 默认镜像可容纳同一链。此技法同样是 Phase 3 深导入图的前置要求。
    """
    import threading
    result = {}

    def runner():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    threading.stack_size(stack_bytes)
    t = threading.Thread(target=runner, name="btdeck-import")
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")



def check_httpx_import() -> str:
    """httpx/anyio/selectors 全链导入（16K 页上 dlopen 探针）。"""
    def _do():
        import httpx._client  # 懒加载全链
        import anyio
        import selectors
        return "ok"
    return _run_on_big_stack(_do)


def check_testclient_import() -> str:
    """fastapi.testclient 完整导入（触发 pydantic_core→typing_extensions 深链）。"""
    def _do():
        import fastapi.testclient  # noqa: F401
        return "ok"
    return _run_on_big_stack(_do)
