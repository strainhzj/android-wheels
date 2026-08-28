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
    """最小 FastAPI 应用 + TestClient 冒烟（阶段 1 hello world 判据）。"""
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
