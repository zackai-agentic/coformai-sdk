# Runnable examples

Install the SDK and set the four `COFORM_*` configuration variables described
in the main README. Use your own dashboard/core roots and dashboard-issued key.

| Script | Prerequisites | Expected result |
|---|---|---|
| `python examples/create_division.py` | agents write | Saved draft graph and resolved IDs; creates resources |
| `python examples/create_sample_division.py` | agents/chains/functions/integrations read and write; connected language model or `--allow-unconfigured` | Saved conversational Division with three agents, two REST functions, context, and a dependent task chain |
| `python examples/async_list.py` | agents read | List of accessible Division dictionaries |
| `python examples/run_division.py` | inference execute, deployed automation, COFORM_DIVISION_ID | Terminal or approval outcome and output |
| `python examples/upload_integrations.py` | integrations write, COFORM_MCP_URL | Uploaded REST/MCP definitions or OAuth links |

Create examples save drafts; they require valid model configuration before
deploying. Upload examples contact the configured MCP server through the
dashboard. No credentials are embedded in example source. These scripts are
verified with MockTransport by `python -m pytest tests/test_examples.py`, which
does not contact services or create real resources.

## Full task-briefing sample

After setting the four environment variables, inspect available model choices:

```sh
python examples/create_sample_division.py --inspect
```

Create the sample with an existing connected language model:

```sh
python examples/create_sample_division.py --model-connection-id "<connection-uuid>" --model-name "<model-name>"
```

Omitting model options selects the first connected model whose name is nonempty
and does not identify an embedding or reranking model. The selected connection
and model name are printed before saving; use explicit options when your
organization has several choices.

If the organization has no model connections, save the same map as a model-free
draft with `python examples/create_sample_division.py --allow-unconfigured`.
The result reports `model_configured: false`; configure a model connection before
deploying or invoking it. Hosted catalog entries alone do not provide an
organization model connection or its provider credentials.

The sample uses fictitious JSONPlaceholder users and tasks. The SDK imports two
GET endpoints, wraps them as Agentic Functions with a default `userId` of `1`,
attaches them to Task Researcher, and adds the user function as static context.
Task Briefing Pipeline runs Task Researcher followed by Briefing Writer, whose
input depends on the research step's output. Briefing Coordinator exposes that
chain as an action. All three agents and the chain appear on the Division map.

The expected result is a saved, inactive Division named
`SDK Sample - Task Briefing`, its entity IDs, and `map_retrieved: true`. It is
not deployed or invoked. No schedule is enabled. A subsequent invocation could
use: "Brief me on the tasks for demo user 1."

All platform calls use SDK resource methods. An existing Division with the same
name is retrieved without modification. The sample integration is reused if
present. Import, entity save, and chain-step save are separate transactions.
The current dashboard cannot dry-run chain steps referencing a newly created
chain, so steps are validated and saved after entity IDs are available. If a
later phase fails, earlier phases remain saved. The script prints its integration
ID and graph request IDs for reconciliation and never automatically retries
mutations. A connection failure after commit requires checking the saved map
before another creation attempt.
