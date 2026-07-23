# KORYAO Model Contract

`model_contracts` 是 `koryao-model-contract/v1` 的公共协议包，只包含 JSON Schema、抽象接口和交叉安全验证。

```python
from model_contracts import ensure_plan_response, load_schema

plan_schema = load_schema("plan_response.schema.json")
ensure_plan_response(request_payload, response_payload)
```

协议的架构与安全边界见 [`docs/CLOSED_MODEL_ARCHITECTURE.md`](../docs/CLOSED_MODEL_ARCHITECTURE.md)。

本目录禁止加入真实模型 Provider、私有 prompt、训练数据、训练代码或权重。
