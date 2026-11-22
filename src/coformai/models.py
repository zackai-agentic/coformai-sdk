"""Typed wire envelopes and input helpers; unknown server event fields are retained."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

StreamMode = Literal["cumulative_stream", "one_token_at_a_time_stream", "no_stream"]
"""Response text framing; every mode still uses incremental NDJSON events."""
Outcome = Literal["completed", "failed", "cancelled", "awaiting_approval", "indeterminate"]
"""Observed execution outcome; a missing terminal event remains indeterminate."""


class WireModel(BaseModel):
    """Forward-compatible wire data with unknown response fields preserved."""

    model_config = ConfigDict(extra="allow")


class InputItem(WireModel):
    """A text, file, image, or audio input accepted by the core service.

    Text requires a nonblank text value. Binary inputs require file_name,
    media_type, and data_base64. File content is transmitted to the core service.

    Attributes:
        type: Required modality: text, file, image, or audio.
        input_id: Optional caller correlation ID, default None.
        text: Required text for text inputs, otherwise None.
        file_name: Required original filename for binary inputs, otherwise None.
        media_type: Required MIME type for binary inputs, otherwise None.
        data_base64: Required encoded bytes for binary inputs; excluded from repr.
        description: Optional attachment context, default None.
    """

    type: Literal["text", "file", "image", "audio"] = Field(description="Input modality")
    input_id: str | None = Field(default=None, description="Optional caller correlation ID")
    text: str | None = Field(default=None, description="Text content for text inputs")
    file_name: str | None = Field(default=None, description="Original binary input filename")
    media_type: str | None = Field(default=None, description="Binary input MIME type")
    data_base64: str | None = Field(default=None, repr=False, description="Base64-encoded bytes")
    description: str | None = Field(default=None, description="Optional attachment description")

    @model_validator(mode="after")
    def validate_content(self) -> InputItem:
        """Reject inputs missing the fields required for their modality."""
        required = (
            (self.text,)
            if self.type == "text"
            else (
                self.file_name,
                self.media_type,
                self.data_base64,
            )
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError("Text requires text; binary inputs require filename, MIME, and base64")
        return self

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        type: Literal["file", "image", "audio"] = "file",
        media_type: str | None = None,
        description: str | None = None,
        input_id: str | None = None,
    ) -> InputItem:
        """Read a local attachment into a core-service input.

        Args:
            path: File to read. This helper performs no network request.
            type: Input modality; defaults to a document/file.
            media_type: MIME override, otherwise inferred from the filename.
            description: Optional attachment context.
            input_id: Optional caller correlation identifier.

        Returns:
            A validated input with base64 content.

        Raises:
            OSError: The file cannot be read.
        """
        file = Path(path)
        return cls(
            type=type,
            file_name=file.name,
            media_type=media_type
            or mimetypes.guess_type(file.name)[0]
            or "application/octet-stream",
            data_base64=base64.b64encode(file.read_bytes()).decode("ascii"),
            description=description,
            input_id=input_id,
        )


class HistoryPair(WireModel):
    """One prior agent input/output pair to append with inference:execute permission.

    Attributes:
        input_inquiry: Optional text input, default None.
        inputs: Optional multimodal inputs, default None. Supply input in either form.
        output: Required nonblank prior output.
    """

    input_inquiry: str | None = None
    inputs: list[InputItem] | None = None
    output: str = Field(min_length=1, description="Prior agent output")

    @model_validator(mode="after")
    def validate_pair(self) -> HistoryPair:
        """Require an input and a nonblank output, as the core service does."""
        if not ((self.input_inquiry or "").strip() or self.inputs) or not self.output.strip():
            raise ValueError("A history pair requires input and nonblank output")
        return self


class InvocationEvent(WireModel):
    """A single NDJSON invocation event, including unknown future result codes.

    Attributes:
        status: Required server status string.
        result: Required server event code; unknown codes remain valid events.
        content: Event-specific fields, default empty mapping.
        session_id: Optional session identity, default None.
        division_id: Optional Division identity, default None.
        ts: Optional server timestamp, default None.

    Unknown fields are retained in model_extra and model_dump().
    """

    status: str
    result: str
    content: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")
    session_id: str | None = None
    division_id: str | None = None
    ts: float | None = None


class InvocationResult(WireModel):
    """Collected events and output, with an explicit execution outcome.

    A failed workflow is returned with outcome='failed'; it is not an HTTP
    exception. Indeterminate means the stream ended without a terminal event.
    Use session status to reconcile before deciding whether replay is safe.

    Attributes:
        outcome: Terminal outcome, default indeterminate until observed.
        events: All parsed events in order, default empty list.
        responses: Collected text by response_id, default empty mapping.
        session_id: Most recently observed session ID, default None.
        approval_id: Pending approval correlation ID, default None.
    """

    outcome: Outcome = "indeterminate"
    events: list[InvocationEvent] = Field(default_factory=list)
    responses: dict[str, str] = Field(default_factory=dict, description="Text by response_id")
    session_id: str | None = None
    approval_id: str | None = None
    _attempts: dict[str, int] = PrivateAttr(default_factory=dict)

    def add(self, event: InvocationEvent, mode: StreamMode) -> None:
        """Accumulate one parsed event without making any request.

        Args:
            event: Event to retain, including unknown fields and codes.
            mode: Replace cumulative text or append deltas; retry attempts reset deltas.

        Returns:
            None. Updates this result's events, text, session, and terminal outcome.
        """
        self.events.append(event)
        content = event.content
        self.session_id = content.get("session_id") or event.session_id or self.session_id
        if event.result == "RESPOND" and content.get("response_id") and "buffer" in content:
            response_id = str(content["response_id"])
            buffer = str(content.get("buffer") or "")
            if mode == "one_token_at_a_time_stream":
                retry = content.get("invocation_retry") or {}
                attempt = retry.get("attempt", 1) if isinstance(retry, dict) else 1
                if self._attempts.get(response_id, attempt) != attempt:
                    self.responses.pop(response_id, None)
                self._attempts[response_id] = attempt
                self.responses[response_id] = self.responses.get(response_id, "") + buffer
            else:
                self.responses[response_id] = buffer
        terminal: dict[str, Outcome] = {
            "COMPLETED": "completed",
            "WORKFLOW_FAILED": "failed",
            "WORKFLOW_CANCELLED": "cancelled",
            "AGENT_LOOP_AWAITING_APPROVAL": "awaiting_approval",
        }
        if event.result in terminal:
            self.outcome = terminal[event.result]
        if event.result == "AGENT_LOOP_AWAITING_APPROVAL":
            self.approval_id = content.get("approval_id")


TrimStep = Literal["trim_turns_from_start", "trim_most_recent_input_text"]


class TrimPastContext(BaseModel):
    """Trim selected sources in priority order until the final text input fits."""

    model_config = ConfigDict(extra="forbid")
    method: Literal["trim_past_context"] = "trim_past_context"
    target_percent: int = Field(default=80, strict=True, ge=5, le=95, multiple_of=5)
    submethods: list[TrimStep] = Field(
        default_factory=lambda: ["trim_turns_from_start", "trim_most_recent_input_text"],
        min_length=1,
    )

    @model_validator(mode="after")
    def _check_priority(self) -> TrimPastContext:
        if len(self.submethods) != len(set(self.submethods)):
            raise ValueError("Each selected submethod must appear once.")
        return self


class ContextCompacting(BaseModel):
    """Policy for one entity's model-visible text in the current session."""

    model_config = ConfigDict(extra="forbid")
    trigger: Literal["before_request", "after_context_error"] = "after_context_error"
    allowance_percent: int = Field(default=100, strict=True, ge=10, le=100, multiple_of=5)
    methods: list[TrimPastContext] = Field(
        default_factory=lambda: [TrimPastContext()], min_length=1, max_length=1
    )

    @model_validator(mode="after")
    def _check_targets(self) -> ContextCompacting:
        if self.trigger == "after_context_error" and self.allowance_percent != 100:
            raise ValueError("After-error checks use the full input limit.")
        if any(method.target_percent >= self.allowance_percent for method in self.methods):
            raise ValueError("The shrink target must be below the allowance.")
        return self

    def entity_fields(self, *, enabled: bool = True) -> dict[str, Any]:
        """Build fields for create, update, or a staged graph mutation."""
        return {
            "automatic_context_compacting_enabled": enabled,
            "context_compacting": self.model_dump(mode="json"),
        }
