"""Wire-contract, builder, configuration, error, and sync/async parity tests."""

import inspect
import json

import httpx
import pytest

from coformai import (
    APIConnectionError,
    APIStatusError,
    AsyncCoform,
    AuthenticationError,
    ChainStep,
    Coform,
    CoformError,
    ConflictError,
    EntityRef,
    GraphMutationBuilder,
    InputItem,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    StreamProtocolError,
    ValidationError,
    async_resources,
    resources,
)

CONFIG = {
    "api_key": "ak_test",
    "organization_id": "org",
    "dashboard_url": "https://dashboard.test/prefix/api/",
    "core_url": "https://core.test/runtime/",
}


def test_configuration_prefix_and_bearer():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    with Coform(**CONFIG, transport=httpx.MockTransport(handler)) as client:
        client.divisions.list(limit=5)
        client.sessions.create("div")
    assert (
        str(captured[0].url) == "https://dashboard.test/prefix/api/clients/org/divisions/?limit=5"
    )
    assert captured[0].headers["Authorization"] == "Bearer ak_test"
    assert json.loads(captured[1].content) == {
        "division_id": "div",
        "session_id": None,
        "session_params": {},
    }
    assert str(captured[1].url) == "https://core.test/runtime/create_session"


@pytest.mark.parametrize(
    "url",
    ["https://evil.test/api/", "https://dashboard.test/elsewhere", "//evil.test", "../escape"],
)
def test_pagination_cannot_leak_credentials(url):
    with Coform(**CONFIG) as client:
        with pytest.raises(ValueError):
            client.configuration.url("dashboard", url)


def test_env_precedence(monkeypatch):
    for key, value in zip(
        ["COFORM_API_KEY", "COFORM_ORGANIZATION_ID", "COFORM_DASHBOARD_URL", "COFORM_CORE_URL"],
        CONFIG.values(),
    ):
        monkeypatch.setenv(key, value)
    with Coform(api_key="override") as client:
        assert client.configuration.api_key == "override"
        assert "override" not in repr(client.configuration)


@pytest.mark.parametrize(
    "status, error",
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (400, ValidationError),
        (422, ValidationError),
        (404, NotFoundError),
        (409, ConflictError),
        (429, RateLimitError),
        (500, APIStatusError),
    ],
)
def test_errors_do_not_retry(status, error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"detail": "diagnostic"},
            headers={"x-request-id": "rid", "retry-after": "2"},
        )

    with Coform(**CONFIG, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(error) as exc:
            client.divisions.create(division_name="X")
    assert len(calls) == 1
    assert exc.value.body["detail"] == "diagnostic"
    assert exc.value.request_id == "rid"


def test_graph_temporary_ids_metadata_and_detach():
    builder = GraphMutationBuilder.new_root("division", {"division_name": "Example"})
    fn = builder.create_entity("agentic_function", {"name": "Function"}, temp_id="fn")
    builder.patch_entity(fn, {"description": "Draft changes"})
    agent = EntityRef(entity_type="swift_agent", entity_id="agent")
    builder.attach_relation(
        "division_agents", builder.root, agent, relation_data={"label": "preserved"}
    )
    builder.detach_relation("division_agents", builder.root, agent)
    payload = builder.build().model_dump(exclude_none=True)
    assert payload["operations"][1]["temp_id"] == "fn"
    assert payload["operations"][1]["data"]["description"] == "Draft changes"
    assert payload["operations"][-1]["op"] == "detach_relation"
    assert payload["operations"][-2]["relation_data"] == {"label": "preserved"}
    assert not any(op["op"] == "delete_entity" for op in payload["operations"])


def test_collection_and_request_correlation():
    requests = []
    builder = GraphMutationBuilder(
        EntityRef(entity_type="swift_chain", entity_id="chain"), request_id="req"
    )
    builder.replace_collection(
        "swift_chain_steps",
        builder.root,
        [
            ChainStep(
                step_type="agent",
                entity_ref=EntityRef(entity_type="swift_agent", entity_id="agent"),
                order_index=0,
            )
        ],
    )
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200, json={})),
    ) as client:
        client.graph.validate(builder)
        client.graph.commit(builder.build())
    assert requests[0].headers["Idempotency-Key"] == "req"
    assert (
        json.loads(requests[1].content)["operations"][0]["items"][0]["entity_ref"]["entity_id"]
        == "agent"
    )


def test_reference_validation_and_file_input(tmp_path):
    with pytest.raises(ValueError):
        EntityRef(entity_type="division", entity_id="a", temp_id="b")
    file = tmp_path / "image.png"
    file.write_bytes(b"binary")
    item = InputItem.from_file(file, type="image")
    assert item.media_type == "image/png"
    assert item.data_base64 == "YmluYXJ5"
    with pytest.raises(ValueError):
        InputItem(type="text", text=" ")


def test_upload_contracts_and_nested_factories(tmp_path):
    calls = []
    file = tmp_path / "spec.json"
    file.write_text('{"openapi":"3.0.0"}')
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda r: (
                calls.append(r)
                or httpx.Response(200, json={"oauth_start_url": "https://provider.test"})
            )
        ),
    ) as client:
        client.uploads.rest(file, name="REST", trust_url=True)
        client.uploads.openapi_string(file.read_text())
        result = client.uploads.mcp(
            "MCP", "Tools", '{"servers":{"test":{"url":"https://tools.test"}}}'
        )
        client.function_parameters("fn").list()
        client.integration_parameters("integration", "endpoint").list()
        client.uploads.clear_scheduled_inputs("div")
    assert b'name="file"' in calls[0].content
    assert b'name="trust_url"' in calls[0].content
    assert result["oauth_start_url"] == "https://provider.test"
    assert calls[-1].url.path.endswith("scheduled-input-files/")


def test_resource_sync_async_parity():
    for name in vars(resources):
        cls = getattr(resources, name)
        if not inspect.isclass(cls) or cls.__module__ != resources.__name__:
            continue
        other = getattr(async_resources, "Async" + name)
        for method, member in vars(cls).items():
            if method.startswith("_") or not inspect.isfunction(member):
                continue
            async_member = getattr(other, method)
            assert list(inspect.signature(member).parameters) == list(
                inspect.signature(async_member).parameters
            )
            if name != "InvocationResource":
                assert inspect.iscoroutinefunction(async_member) or inspect.isasyncgenfunction(
                    async_member
                )


async def test_async_wire_contract_and_context():
    calls = []
    async with AsyncCoform(
        **CONFIG,
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})),
    ) as client:
        await client.divisions.update("div", description=None)
        await client.sessions.add_agent_history(
            "session", "div", "agent", [{"input_inquiry": "Hello", "output": "Hi"}]
        )
    assert json.loads(calls[0].content) == {"description": None}
    assert calls[1].url.path.endswith("add_agent_history")


class Fragments(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, content):
        self.content, self.closed = content, False

    def __iter__(self):
        for byte in self.content:
            yield bytes([byte])

    async def __aiter__(self):
        for byte in self.content:
            yield bytes([byte])

    def close(self):
        self.closed = True

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("mode", ["no_stream", "cumulative_stream", "one_token_at_a_time_stream"])
@pytest.mark.parametrize(
    "terminal, outcome",
    [
        ("COMPLETED", "completed"),
        ("WORKFLOW_FAILED", "failed"),
        ("WORKFLOW_CANCELLED", "cancelled"),
        ("AGENT_LOOP_AWAITING_APPROVAL", "awaiting_approval"),
        ("UNKNOWN", "indeterminate"),
    ],
)
def test_fragmented_stream_and_outcomes(mode, terminal, outcome):
    content = (
        "\n"
        + json.dumps(
            {
                "status": "success",
                "result": "RESPOND",
                "content": {"response_id": "r", "buffer": "Çağrı"},
                "future": 7,
            },
            ensure_ascii=False,
        )
        + "\r\n"
        + json.dumps(
            {"status": "success", "result": terminal, "content": {"approval_id": "approval"}}
        )
    )
    fragments = Fragments(content.encode())
    with Coform(
        **CONFIG, transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=fragments))
    ) as client:
        stream = client.invocations.process_inquiry(
            "div", session_id="session", input_inquiry="Hello", entity_response_stream_option=mode
        )
        result = stream.collect()
        assert result.outcome == outcome
        assert result.responses["r"] == "Çağrı"
        assert result.events[0].model_extra["future"] == 7
        assert fragments.closed
        with pytest.raises(CoformError):
            stream.collect()


def test_malformed_events_close_and_partial_result():
    fragments = Fragments(b'{"status":"success","result":"UNKNOWN"}\nmalformed\n')
    with Coform(
        **CONFIG, transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=fragments))
    ) as client:
        stream = client.invocations.trigger_automation("div", input_inquiry="run")
        with pytest.raises(StreamProtocolError):
            stream.collect()
        assert stream.partial_result.outcome == "indeterminate"
        assert len(stream.partial_result.events) == 1
    assert fragments.closed


async def test_async_stream_early_close_and_approval_continuation():
    calls = []
    fragments = Fragments(
        b'{"status":"success","result":"AGENT_LOOP_AWAITING_APPROVAL","content":{"approval_id":"approval"}}\n'
    )

    def handler(r):
        calls.append(r)
        return httpx.Response(200, stream=fragments)

    async with AsyncCoform(**CONFIG, transport=httpx.MockTransport(handler)) as client:
        async with client.invocations.trigger_automation("div", input_inquiry="run") as stream:
            async for event in stream:
                break
        assert fragments.closed
        resumed = client.invocations.continue_agent_loop("session", "div", "approval", False)
        await resumed.collect()
    assert json.loads(calls[1].content)["approved"] is False
    assert calls[1].url.path.endswith("continue_agent_loop")


def test_typed_mutations_and_snapshot_isolation():
    from coformai import GraphMutationRequest, PatchEntityMutation

    operation = PatchEntityMutation(
        entity_type="division", entity_id="div", changes={"description": None}
    )
    payload = GraphMutationRequest(
        root=EntityRef(entity_type="division", entity_id="div"), operations=[operation]
    )
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})),
    ) as client:
        client.graph.commit(payload)
    assert json.loads(calls[0].content)["operations"][0]["changes"]["description"] is None
    builder = GraphMutationBuilder(EntityRef(entity_type="division", entity_id="div"))
    builder.patch_entity(builder.root, {"description": "before"})
    snapshot = builder.build()
    builder.operations[0]["changes"]["description"] = "after"
    assert snapshot.model_dump()["operations"][0]["changes"]["description"] == "before"


def test_stream_error_body_and_transport_failure_not_replayed():
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda r: calls.append(r) or httpx.Response(403, json={"detail": "missing inference"})
        ),
    ) as client:
        with pytest.raises(PermissionDeniedError) as exc:
            client.invocations.trigger_automation("div", input_inquiry="Run").collect()
    assert exc.value.body["detail"] == "missing inference"
    assert len(calls) == 1

    def fail(r):
        calls.append(r)
        raise httpx.ReadError("disconnect")

    with Coform(**CONFIG, transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(APIConnectionError):
            client.invocations.trigger_automation("div", input_inquiry="Run").collect()
    assert len(calls) == 2


def test_sync_early_closure_and_closed_lazy_stream():
    fragments = Fragments(b'{"status":"success","result":"UNKNOWN"}\n' * 2)
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda r: calls.append(r) or httpx.Response(200, stream=fragments)
        ),
    ) as client:
        with client.invocations.trigger_automation("div", input_inquiry="Run") as stream:
            for event in stream:
                break
        assert fragments.closed
        unopened = client.invocations.trigger_automation("div", input_inquiry="Run")
        unopened.close()
        with pytest.raises(CoformError):
            unopened.collect()
    assert len(calls) == 1


def test_delta_attempt_reset_and_usage_event_keeps_output():
    from coformai import InvocationEvent, InvocationResult

    result = InvocationResult()
    for attempt, buffer in [(1, "Bad"), (2, "Good"), (2, " answer")]:
        result.add(
            InvocationEvent(
                status="success",
                result="RESPOND",
                content={
                    "response_id": "r",
                    "buffer": buffer,
                    "invocation_retry": {"attempt": attempt},
                },
            ),
            "one_token_at_a_time_stream",
        )
    result.add(
        InvocationEvent(
            status="success", result="RESPOND", content={"response_id": "r", "usage": {"tokens": 2}}
        ),
        "one_token_at_a_time_stream",
    )
    assert result.responses["r"] == "Good answer"


@pytest.mark.parametrize(
    "terminal,outcome",
    [
        ("COMPLETED", "completed"),
        ("WORKFLOW_FAILED", "failed"),
        ("WORKFLOW_CANCELLED", "cancelled"),
        ("AGENT_LOOP_AWAITING_APPROVAL", "awaiting_approval"),
        ("UNKNOWN", "indeterminate"),
    ],
)
async def test_async_fragmented_utf8_and_terminal_outcomes(terminal, outcome):
    content = json.dumps(
        {
            "status": "success",
            "result": "RESPOND",
            "content": {"response_id": "r", "buffer": "Çağrı"},
        },
        ensure_ascii=False,
    )
    content += "\n" + json.dumps(
        {"status": "success", "result": terminal, "content": {"approval_id": "a"}}
    )
    fragments = Fragments(content.encode("utf-8"))
    async with AsyncCoform(
        **CONFIG, transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=fragments))
    ) as client:
        result = await client.invocations.trigger_automation(
            "division", input_inquiry="Run"
        ).collect()
    assert result.outcome == outcome
    assert result.responses["r"] == "Çağrı"
    assert fragments.closed


def test_settings_catalog_and_spec_replacement_contracts(tmp_path):
    calls = []
    file = tmp_path / "spec.json"
    file.write_text("{}")
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})),
    ) as client:
        client.share.regenerate("div")
        client.embed.rotate_token("div")
        client.catalogs.hosted_models()
        client.operations_sources("div").update("source", name="Name")
        client.uploads.rest(file, name="Name", update=True)
        assert not hasattr(client.share, "rotate_token")
        assert not hasattr(client.operations_sources("div"), "get")
    assert calls[0].url.path.endswith("share/regenerate/")
    assert calls[1].url.path.endswith("embed/rotate-token/")
    assert calls[2].url.path == "/prefix/api/hosted-models/catalog/"
    assert calls[3].method == "PATCH"
    assert b'name="update"\r\n\r\ntrue' in calls[4].content
