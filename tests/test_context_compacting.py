import json

import httpx
import pytest
from pydantic import ValidationError

from coformai import AsyncCoform, Coform, ContextCompacting, InvocationEvent, TrimPastContext


def test_entity_payload_and_event():
    policy = ContextCompacting(trigger="before_request", allowance_percent=95)
    fields = policy.entity_fields()
    assert fields["automatic_context_compacting_enabled"] is True
    assert fields["context_compacting"]["methods"][0]["target_percent"] == 80
    code = "AUTOMATIC_CONTEXT_COMPACTING"
    event = InvocationEvent(status="success", result=code, respond=code)
    assert event.model_dump()["respond"] == code


def test_target_and_order_validation():
    with pytest.raises(ValidationError):
        ContextCompacting(trigger="before_request", allowance_percent=80)
    with pytest.raises(ValidationError):
        TrimPastContext(submethods=["trim_turns_from_start", "trim_turns_from_start"])


@pytest.mark.asyncio
async def test_sync_and_async_resource_round_trip():
    config = dict(
        api_key="test",
        organization_id="org",
        dashboard_url="https://dashboard.test/",
        core_url="https://core.test/",
    )
    fields = ContextCompacting(
        methods=[TrimPastContext(submethods=["trim_most_recent_input_text"])]
    ).entity_fields()
    rows = {}

    def handler(request):
        if request.method == "PATCH":
            rows[request.url.path] = json.loads(request.content)
        return httpx.Response(200, json=rows[request.url.path])

    with Coform(**config, transport=httpx.MockTransport(handler)) as client:
        for resource in (client.swift_agents, client.flow_agents, client.agentic_functions):
            assert resource.update("entity", **fields) == fields
    async with AsyncCoform(**config, transport=httpx.MockTransport(handler)) as client:
        for resource in (client.swift_agents, client.flow_agents, client.agentic_functions):
            assert await resource.get("entity") == fields
            assert await resource.update("entity", **fields) == fields
