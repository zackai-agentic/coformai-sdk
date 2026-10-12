"""Run a deployed automation. Requires inference:execute.

Set COFORM_* configuration and COFORM_DIVISION_ID. Expected: collected outcome
and response text, or awaiting_approval with an approval ID. No auto approval.
"""
import os
from coformai import Coform, InvocationResult


def run(client: Coform, division_id: str) -> InvocationResult:
    """Execute once and retain all events for inspection."""
    return client.invocations.trigger_automation(division_id,
        input_inquiry="Summarize the current situation.").collect()


if __name__ == "__main__":
    with Coform() as client:
        result = run(client, os.environ["COFORM_DIVISION_ID"])
        print(result.outcome, result.responses, result.approval_id)
