# 同一个 Echo API：DRF 与 Pydantic 对照

这两个 endpoint 执行同一个业务函数，接收相同 JSON，并返回相同的成功结构：

```text
POST /api/demo/comparison/drf-echo
POST /api/demo/comparison/pydantic-echo
```

请求：

```json
{
  "name": "  Demo User  ",
  "age": 29,
  "active": true,
  "metadata": {"source": "manual-test"},
  "tags": ["django", "migration"]
}
```

## DRF 版本

```text
APIView
  -> JSONParser 自动产生 request.data
  -> DrfEchoSerializer
  -> DRF ValidationError/exception handler
  -> Response/renderer
```

View 只需要处理验证和业务调用：

```python
serializer = DrfEchoSerializer(data=request.data)
serializer.is_valid(raise_exception=True)
return Response(...)
```

代价是引入 `djangorestframework`，并采用 DRF 的 APIView、Request、parser、
exception handler 和 Response 生命周期。DRF 默认忽略额外输入字段；为了保持
当前 Fdc contract，本例额外实现了 `StrictSerializer`。

## Pydantic 版本

```text
django.views.View
  -> 手动检查 Content-Type
  -> 手动读取和解析 request.body
  -> PydanticEchoPayload.model_validate()
  -> 手动转换 ValidationError
  -> JsonResponse
```

Pydantic model 很紧凑，并原生支持 `extra='forbid'` 和 JSON Schema：

```python
PydanticEchoPayload.model_json_schema()
```

代价是 Pydantic 不接管 Django HTTP 生命周期，必须自己实现 request/response adapter，
包括 media type、JSON parse error、CSRF 策略和统一错误格式。

## 同一错误的原生响应差异

`age=17` 时，DRF 默认返回 HTTP 400 和 field-keyed errors：

```json
{
  "age": ["Ensure this value is greater than or equal to 18."]
}
```

Pydantic 版本返回 HTTP 422 和带位置的 errors：

```json
{
  "errors": [
    {
      "type": "greater_than_equal",
      "loc": ["age"],
      "msg": "Input should be greater than or equal to 18",
      "input": 17,
      "ctx": {"ge": 18}
    }
  ]
}
```

如果项目要求两者都返回 `FdcJsonResponse`，还需要为两种错误写 adapter。

## Trade-off

| 项目 | DRF APIView + Serializer | Django View + Pydantic |
|---|---|---|
| JSON parsing | 自动 | 手动 adapter |
| multipart parsing | 自动 | Django/Pydantic adapter |
| validation | Serializer | BaseModel |
| extra fields | 默认忽略，本例定制拒绝 | `extra='forbid'` |
| error response | DRF 自动 400 | 手动捕获，通常 422 |
| response rendering | `Response` 自动 | `JsonResponse`/自定义 |
| permissions/throttling | DRF 原生 | 使用 Django/自行接入 |
| JSON Schema | OpenAPI tooling | `model_json_schema()` |
| 对现有 FdcView 改动 | 较大，换生命周期 | 较小，可替换字段验证层 |

## 手工验证

```bash
curl -sS -X POST http://127.0.0.1:8001/api/demo/comparison/drf-echo \
  -H 'Content-Type: application/json' \
  -d '{"name":"  Demo User  ","age":29,"active":true,"metadata":{"source":"curl"},"tags":["django"]}'

curl -sS -X POST http://127.0.0.1:8001/api/demo/comparison/pydantic-echo \
  -H 'Content-Type: application/json' \
  -d '{"name":"  Demo User  ","age":29,"active":true,"metadata":{"source":"curl"},"tags":["django"]}'
```
