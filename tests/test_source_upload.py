"""Knowledge source ingestion contracts across synchronous and async clients."""

from email.parser import BytesParser
from email.policy import default

import httpx
import pytest

from coformai import APIStatusError, AsyncCoform, Coform

CONFIG = {
    "api_key": "ak_test",
    "organization_id": "org",
    "dashboard_url": "https://dashboard.test/prefix/api/",
    "core_url": "https://core.test/runtime/",
}


def parts(request):
    raw = b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n"
    message = BytesParser(policy=default).parsebytes(raw + request.content)
    return {
        part.get_param("name", header="Content-Disposition"): part.get_payload(decode=True)
        for part in message.iter_parts()
    }


def test_semantic_source_upload_preserves_bytes_and_does_not_forge_ready_status(tmp_path):
    path = tmp_path / "billing-policy.txt"
    content = "Billing policy: \u20ac20 demonstration limit.".encode()
    path.write_bytes(content)
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda request: (
                calls.append(request)
                or httpx.Response(201, json={"source_id": "source", "status": "processing"})
            )
        ),
    ) as client:
        result = client.sources.upload(
            path,
            name="Billing policy",
            description="Demo rules",
            enable_semantic_retrieval=True,
            embedding_model_connection_id="embed",
            max_tokens_in_chunk=512,
        )
    assert len(calls) == 1
    assert calls[0].url.path == "/prefix/api/clients/org/sources/"
    assert parts(calls[0]) == {
        "client": b"org",
        "name": b"Billing policy",
        "description": b"Demo rules",
        "enable_semantic_retrieval": b"true",
        "embedding_model_connection": b"embed",
        "max_tokens_in_chunk": b"512",
        "file": content,
    }
    assert result == {"source_id": "source", "status": "processing"}


async def test_async_nonsemantic_source_omits_embedding_and_chunk_metadata(tmp_path):
    path = tmp_path / "charter.txt"
    path.write_bytes(b"Short service charter")
    calls = []
    async with AsyncCoform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(201, json={"source_id": "s"})
        ),
    ) as client:
        await client.sources.upload(
            path, name="Charter", embedding_model_connection_id="unused", max_tokens_in_chunk=0
        )
    assert parts(calls[0]) == {
        "client": b"org",
        "name": b"Charter",
        "enable_semantic_retrieval": b"false",
        "file": b"Short service charter",
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "  "},
        {"name": "Policy", "enable_semantic_retrieval": True, "max_tokens_in_chunk": 0},
    ],
)
def test_invalid_metadata_fails_before_network_or_file_read(fields):
    calls = []
    with Coform(**CONFIG, transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
        with pytest.raises(ValueError):
            client.sources.upload("missing.txt", **fields)
    assert calls == []


def test_missing_source_file_fails_without_network(tmp_path):
    calls = []
    with Coform(**CONFIG, transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
        with pytest.raises(OSError):
            client.sources.upload(tmp_path / "missing.txt", name="Missing")
    assert calls == []


def test_rejected_source_upload_is_not_retried(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"Demo")
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(503, json={"detail": "busy"})
        ),
    ) as client:
        with pytest.raises(APIStatusError, match="503"):
            client.sources.upload(path, name="Source")
    assert len(calls) == 1


def test_replace_source_file_uses_quoted_detail_path_and_preserves_processing_response(tmp_path):
    path = tmp_path / "replacement.html"
    path.write_bytes(b"<p>Reviewed policy</p>")
    calls = []
    with Coform(
        **CONFIG,
        transport=httpx.MockTransport(
            lambda request: (
                calls.append(request)
                or httpx.Response(200, json={"source_id": "source id", "status": "processing"})
            )
        ),
    ) as client:
        result = client.sources.upload(path, name="Policy", source_id="source id")
    assert calls[0].method == "PATCH"
    assert calls[0].url.raw_path.endswith(b"/sources/source%20id/")
    assert parts(calls[0])["file"] == b"<p>Reviewed policy</p>"
    assert result["status"] == "processing"
