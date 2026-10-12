"""Verify runnable example contracts against mock services without credentials."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from test_sdk import CONFIG

from coformai import AsyncCoform, Coform


def module(name):
    path = Path(__file__).resolve().parents[1] / "examples" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_create_example_contract():
    calls = []

    def handler(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert len(payload["operations"]) == 3
        assert payload["operations"][2]["child"]["temp_id"]
        return httpx.Response(200, json={"status": "success", "id_map": {}})

    with Coform(**CONFIG, transport=httpx.MockTransport(handler)) as client:
        result = module("create_division").run(client)
    assert result["status"] == "success"
    assert len(calls) == 2


def test_execution_example():
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, content=b'{"status":"success","result":"COMPLETED","content":{}}\n'
            )
        ),
    ) as client:
        assert module("run_division").run(client, "division").outcome == "completed"


def test_upload_example():
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda r: calls.append(r) or httpx.Response(200, json={"success": True})
        ),
    ) as client:
        result = module("upload_integrations").run(client, "https://mcp.test/tools")
    assert len(calls) == 2
    assert all(response["success"] for response in result)


async def test_async_example():
    async with AsyncCoform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"results": [{"division_id": "division"}], "next": None}
            )
        ),
    ) as client:
        assert await module("async_list").run(client) == [{"division_id": "division"}]


@pytest.mark.parametrize("unconfigured", [False, True])
def test_full_sample_imports_validates_commits_and_reads_map(unconfigured):
    """Exercise the full public SDK workflow without contacting demo services."""
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if request.method == "GET" and path.endswith("/divisions/"):
            return httpx.Response(200, json=[])
        if path.endswith("/connected-models/"):
            if unconfigured:
                return httpx.Response(200, json={"models": []})
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "model_connection_id": "model-id",
                            "model_name": "demo-language-model",
                            "model_provider": "openai",
                            "available_model_capabilities": [],
                        }
                    ]
                },
            )
        if path.endswith("/integrations/catalog/"):
            return httpx.Response(200, json={"integrations": []})
        if "openapi" in path:
            document = json.loads(json.loads(request.content)["openapi_string"])
            assert set(document["paths"]) == {"/users/{userId}", "/todos"}
            return httpx.Response(
                201,
                json={
                    "api_integration_id": "integration-id",
                    "functions": [
                        {
                            "function_id": "user-endpoint",
                            "function_method": "GET",
                            "function_path": "/users/{userId}",
                        },
                        {
                            "function_id": "tasks-endpoint",
                            "function_method": "GET",
                            "function_path": "/todos",
                        },
                    ],
                },
            )
        if "/graph-mutations/" in path:
            operations = json.loads(request.content)["operations"]
            creations = [op for op in operations if op["op"] == "create_entity"]
            if creations:
                assert len(creations) == 7
                assert creations[0]["data"]["active"] is False
                assert ("model_connection_id" in creations[0]["data"]) is not unconfigured
                assert not any(op["op"] == "replace_collection" for op in operations)
                assert any(
                    op.get("relation") == "static_augmentation_functions" for op in operations
                )
            else:
                chain = next(op for op in operations if op["op"] == "replace_collection")
                assert chain["parent"]["entity_id"] == "new-chain"
                assert chain["items"][0]["entity_ref"]["entity_id"] == "new-researcher"
                assert chain["items"][1]["output_dependency_refs"] == [{"temp_id": "research-step"}]
            if path.endswith("/validate/"):
                return httpx.Response(200, json={"status": "validated", "operation_errors": []})
            return httpx.Response(
                201,
                json={
                    "status": "committed",
                    "root": {"entity_id": "new-division"},
                    "request_id": "saved-request",
                    "new_graph_revision": 1,
                    "id_map": {
                        "researcher": "new-researcher",
                        "writer": "new-writer",
                        "briefing-chain": "new-chain",
                    }
                    if creations
                    else {"research-step": "new-step-one", "writing-step": "new-step-two"},
                },
            )
        if path.endswith("/divisions/new-division/map/"):
            return httpx.Response(200, json={"division_id": "new-division"})
        raise AssertionError(f"Unexpected SDK request: {request.method} {path}")

    with Coform(**CONFIG, transport=httpx.MockTransport(handler)) as client:
        result = module("create_sample_division").run(client, allow_unconfigured=unconfigured)
    assert result["division_id"] == "new-division"
    assert result["map_retrieved"] is True
    assert result["model_configured"] is not unconfigured
    assert [method for method, _ in calls] == [
        "GET",
        "GET",
        "GET",
        "POST",
        "POST",
        "POST",
        "POST",
        "POST",
        "GET",
    ]


def test_full_sample_existing_division_does_not_mutate():
    def handler(request):
        assert request.method == "GET"
        if request.url.path.endswith("/divisions/"):
            return httpx.Response(
                200,
                json=[
                    {
                        "division_id": "existing",
                        "division_name": "SDK Sample - Task Briefing",
                    }
                ],
            )
        assert request.url.path.endswith("/divisions/existing/map/")
        return httpx.Response(200, json={"division_id": "existing"})

    with Coform(**CONFIG, transport=httpx.MockTransport(handler)) as client:
        result = module("create_sample_division").run(client)
    assert result["status"] == "already_exists"
