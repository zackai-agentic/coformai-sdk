# Sessions, streaming, approvals, and multimodal input

Every mounted core route requires `inference:execute` and access to the Division.
The core verifies dashboard-generated API keys through the existing verification
flow. Configure the core root directly; it is independent of the dashboard API root.

## Create and inspect a session

```python
from coformai import Coform, HistoryPair

with Coform() as client:
    created = client.sessions.create(division_id, session_params={"customer": "A"})
    print(created)  # Read the returned session_id.
    status = client.sessions.status(session_id, division_id)
    client.sessions.add_agent_history(session_id, division_id, agent_id, [
        HistoryPair(input_inquiry="Hello", output="How can I help?"),
    ])
```

Creation sends the required `session_id` field as null when you want a generated
identifier. History appends prior input/output pairs to a bound agent session.
The core enforces Division/session ownership and active-operation conflicts.

## Consume a closable stream

```python
with Coform() as client:
    with client.invocations.process_inquiry(division_id, session_id=session_id,
            input_inquiry="Help with my account") as stream:
        for event in stream:
            print(event.result, event.content)
```

Async stream factories are synchronous and lazy:

```python
from coformai import AsyncCoform

async with AsyncCoform() as client:
    async with client.invocations.trigger_automation(division_id,
            input_inquiry="Generate the report") as stream:
        async for event in stream:
            print(event.result)
```

The POST begins on context entry or iteration. Use a context manager when
breaking early. Closing releases the HTTP response and does not guarantee
server cancellation. Streams are single-use and never replay their POST.

`cumulative_stream`, `one_token_at_a_time_stream`, and `no_stream` all return
newline-delimited JSON. Network chunks can split UTF-8 characters or JSON lines;
the SDK decodes incrementally and handles blank lines, CRLF, and final lines
without a newline. Unknown fields/result codes are retained. Invalid JSON or
invalid event envelopes raise `StreamProtocolError`, with consumed events in
`stream.partial_result`.

## Collect an outcome

```python
result = client.invocations.trigger_automation(division_id,
    input_inquiry="Generate the report").collect()
print(result.outcome, result.responses)
```

Await `collect()` for async streams. `responses` is indexed by `response_id`.
Cumulative/no-stream text replaces the buffer; token deltas append. A new server
retry attempt resets that response's buffer. This handles server events without
causing client retries.

| Terminal result | Collected outcome |
|---|---|
| `COMPLETED` | `completed` |
| `WORKFLOW_FAILED` | `failed` |
| `WORKFLOW_CANCELLED` | `cancelled` |
| `AGENT_LOOP_AWAITING_APPROVAL` | `awaiting_approval` |
| No terminal event | `indeterminate` |

A workflow failure is a collected event, not necessarily an HTTP exception.
Missing terminal events never imply success. Intermediate failure/retry events
remain in `events`. Recover by reading `sessions.status()` before replaying.

## Approval continuation

```python
if result.outcome == "awaiting_approval":
    resumed = client.invocations.continue_agent_loop(
        session_id, division_id, result.approval_id, approved=True).collect()
```

Require an explicit approval decision from your application. The approval ID is
bound to the suspended loop. Sending `approved=False` permits the core's denial
path, whose terminal outcome can be cancelled. Do not automatically approve
every request or reuse an approval ID for a different session.

## Binary attachments

```python
from coformai import InputItem

inputs = [InputItem(type="text", text="Summarize this file"),
          InputItem.from_file("report.pdf", type="file"),
          InputItem.from_file("photo.png", type="image")]
result = client.invocations.process_inquiry(division_id, session_id=session_id,
    inputs=inputs).collect()
```

`from_file` reads locally and base64-encodes bytes, inferring MIME from the
filename. Override `media_type`, `description`, or `input_id` when needed. Audio
uses `type="audio"`. Text inputs require nonblank text; binary inputs require
filename, MIME, and base64 content. Service attachment size/modality/model
support still applies. Large attachments are held in memory by this helper.
