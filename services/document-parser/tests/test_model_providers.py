from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import urllib.error
from unittest import TestCase
from unittest.mock import patch

from bson import ObjectId

from app.services.embedding_provider import _model_center_embed_texts
from app.services.model_center_runtime import resolve_model_instance
from app.services.reranker_provider import _model_center_rerank
from app.services.secret_codec import decrypt_admin_secret


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ModelProviderTests(TestCase):
    def test_grouped_model_uses_group_connection_settings(self) -> None:
        instance_id = ObjectId()
        group_id = ObjectId()
        provider_id = ObjectId()

        class Collection:
            def __init__(self, document: dict) -> None:
                self.document = document

            def find_one(self, query: dict) -> dict:
                return self.document

        database = {
            "admin_model_instances": Collection(
                {
                    "_id": instance_id,
                    "main_id": "tenant",
                    "provider_id": provider_id,
                    "group_id": str(group_id),
                    "capabilities": ["embedding"],
                    "api_key_encrypted": "old-key",
                    "base_url": "https://old.example/v1",
                    "model_name": "embedding-model",
                }
            ),
            "admin_model_providers": Collection({"provider_type": "openai_compatible"}),
            "admin_model_groups": Collection(
                {
                    "_id": group_id,
                    "provider_id": provider_id,
                    "api_key_encrypted": "group-key",
                    "base_url": "https://group.example/v1/",
                    "api_version": "2026-01-01",
                }
            ),
        }
        with (
            patch("app.services.model_center_runtime.get_db", return_value=database),
            patch("app.services.model_center_runtime.decrypt_admin_secret", side_effect=lambda key: key),
        ):
            result = resolve_model_instance("tenant", str(instance_id), "embedding")
        self.assertEqual("group-key", result["apiKey"])
        self.assertEqual("https://group.example/v1", result["baseUrl"])
        self.assertEqual("embedding-model", result["modelName"])

    def test_embedding_uses_openai_compatible_endpoint(self) -> None:
        runtime = {
            "providerType": "openai_compatible",
            "providerCode": "openai",
            "baseUrl": "https://models.example/v1",
            "apiVersion": "",
            "apiKey": "secret",
            "modelName": "embedding-model",
        }
        with patch(
            "app.services.embedding_provider.urllib.request.urlopen",
            return_value=_Response('{"data":[{"index":0,"embedding":[0.1,0.2]}]}'),
        ) as request:
            result = _model_center_embed_texts(["hello"], runtime=runtime, batch_size=32, timeout=10)
        self.assertEqual(result, [[0.1, 0.2]])
        self.assertEqual(request.call_args.args[0].full_url, "https://models.example/v1/embeddings")

    def test_embedding_adapts_to_provider_batch_limit(self) -> None:
        runtime = {
            "providerType": "openai_compatible",
            "providerCode": "qwen",
            "baseUrl": "https://models.example/v1",
            "apiVersion": "",
            "apiKey": "secret",
            "modelName": "embedding-model",
        }
        request_sizes: list[int] = []

        def open_url(request: object, timeout: int) -> _Response:
            del timeout
            payload = json.loads(request.data.decode("utf-8"))
            size = len(payload["input"])
            request_sizes.append(size)
            if size > 20:
                detail = b'{"error":{"message":"batch size is invalid, it should not be larger than 20."}}'
                raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(detail))
            data = [{"index": index, "embedding": [float(index)]} for index in range(size)]
            return _Response(json.dumps({"data": data}))

        with patch("app.services.embedding_provider.urllib.request.urlopen", side_effect=open_url):
            result = _model_center_embed_texts(
                [f"chunk-{index}" for index in range(29)], runtime=runtime, batch_size=32, timeout=10
            )

        self.assertEqual(request_sizes, [29, 20, 9])
        self.assertEqual(len(result), 29)

    def test_qwen_rerank_uses_dashscope_endpoint(self) -> None:
        runtime = {
            "providerType": "openai_compatible",
            "providerCode": "qwen",
            "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "apiVersion": "",
            "apiKey": "secret",
            "modelName": "qwen3-rerank",
        }
        candidates = [{"text": "first"}, {"text": "second"}]
        with (
            patch("app.services.reranker_provider.resolve_model_instance", return_value=runtime),
            patch(
                "app.services.reranker_provider.urllib.request.urlopen",
                return_value=_Response('{"output":{"results":[{"index":1,"relevance_score":0.9}]}}'),
            ) as request,
        ):
            result = _model_center_rerank(
                "query", candidates, {"modelInstanceId": "instance", "topK": 2}, "tenant"
            )
        self.assertEqual(result[0]["text"], "second")
        self.assertEqual(result[0]["rerankScore"], 0.9)
        self.assertIn("/services/rerank/", request.call_args.args[0].full_url)

    def test_admin_secret_counter_is_compatible(self) -> None:
        secret = "saved-api-key"
        key = hashlib.sha256(b"shared-jwt-secret").digest()
        nonce = bytes(range(16))
        stream = bytearray()
        counter = 0
        while len(stream) < len(secret.encode("utf-8")):
            stream.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1
        cipher = bytes(left ^ right for left, right in zip(secret.encode("utf-8"), stream))
        mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        encrypted = base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")
        with patch("app.services.secret_codec.settings.admin_jwt_secret", "shared-jwt-secret"):
            self.assertEqual(decrypt_admin_secret(encrypted), secret)
