"""Dashboard operation identity and recovery contracts for both clients."""

import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest

from coformai import APITimeoutError, AsyncCoform, Coform, ConflictError, GraphMutationBuilder

CONFIG = dict(
    api_key="ak_fixture",
    organization_id="tenant",
    dashboard_url="https://dashboard.test/api/",
    core_url="https://core.test/",
)


def test_dashboard_write_ids_stay_out_of_payloads_reads_and_core_requests():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={})

    chosen = uuid4()
    with Coform(**CONFIG, transport=httpx.MockTransport(handle)) as client:
        client.divisions.create(division_name="First", operation_id=chosen)
        client.divisions.replace("d", description="New")
        client.divisions.delete("d")
        client.divisions.get("d")
        client.sessions.create("d")
        with pytest.raises(ValueError):
            client.divisions.update("d", operation_id="invalid")

    assert len(requests) == 5
    assert requests[0].headers["X-Operation-ID"] == str(chosen)
    assert json.loads(requests[0].content) == {"division_name": "First"}
    assert len({UUID(r.headers["X-Operation-ID"]) for r in requests[:3]}) == 3
    assert all("X-Operation-ID" not in r.headers for r in requests[3:])


@pytest.mark.parametrize("correlation", [str(uuid4()), "batch-from-previous-client"])
def test_graph_reuses_operation_identity_across_clients(correlation):
    graph = GraphMutationBuilder.new_root("division", {"division_name": "Draft"})
    graph.request_id = correlation
    requests = []
    for _ in range(2):
        with Coform(
            **CONFIG,
            transport=httpx.MockTransport(
                lambda r: requests.append(r) or httpx.Response(200, json={})
            ),
        ) as client:
            client.graph.commit(graph)
    first, second = requests
    assert first.headers["X-Operation-ID"] == second.headers["X-Operation-ID"]
    assert str(UUID(first.headers["X-Operation-ID"])) == first.headers["X-Operation-ID"]
    if correlation != "batch-from-previous-client":
        assert first.headers["X-Operation-ID"] == correlation
    assert (
        first.headers["Idempotency-Key"] == json.loads(first.content)["request_id"] == correlation
    )


async def test_concurrent_uploads_keep_distinct_ids_and_original_receipts(tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"sample")
    ids = [uuid4(), uuid4()]

    async def respond(request):
        await asyncio.sleep(0)
        return httpx.Response(
            202,
            json={
                "operation": {"phase": "pending", "operation_id": request.headers["X-Operation-ID"]}
            },
        )

    async with AsyncCoform(**CONFIG, transport=httpx.MockTransport(respond)) as client:
        results = await asyncio.gather(
            *[client.sources.upload(path, name="Reference", operation_id=value) for value in ids]
        )
    assert [r["operation"] for r in results] == [
        {"phase": "pending", "operation_id": str(value)} for value in ids
    ]


async def test_interrupted_write_can_be_reconciled_by_its_original_id():
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        return httpx.Response(200, json={"phase": "succeeded"})

    async with AsyncCoform(**CONFIG, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(APITimeoutError) as caught:
            await client.divisions.deploy("d")
        operation_id = caught.value.operation_id
        assert operation_id == calls[0].headers["X-Operation-ID"]
        assert await client.get_operation(operation_id) == {"phase": "succeeded"}
        await client.reconcile_operation(operation_id)

    assert [r.method for r in calls] == ["POST", "GET", "POST"]
    assert (
        calls[1].url.path == calls[2].url.path == f"/api/clients/tenant/operations/{operation_id}/"
    )


def test_explicit_request_id_is_preserved_on_http_failure():
    value = uuid4()
    with Coform(**CONFIG, transport=httpx.MockTransport(lambda r: httpx.Response(409))) as client:
        with pytest.raises(ConflictError) as caught:
            client.request("PATCH", "clients/tenant/divisions/d/", operation_id=value)
    assert caught.value.operation_id == str(value)
