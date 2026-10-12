"""Create a task-briefing Division using only public Coform SDK methods.

Set the four COFORM_* variables described in examples/README.md. Requires
agents:read/write, chains:read/write, functions:read/write, and
integrations:read/write. A connected language model is required unless
--allow-unconfigured is supplied to save a model-free draft. This saves
an inactive conversational Division, three agents, two Agentic Functions, a
two-step task chain, action attachments, and function-based context. It imports
a read-only demonstration REST integration when that sample integration does
not already exist. Nothing is deployed, scheduled, or invoked.

Run with --inspect to check connectivity and list model choices without saving.
No credentials are written to disk. Mutations are never automatically retried;
the sample name and printed request ID support reconciliation after a disconnect.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from coformai import (
    APIConnectionError,
    APIStatusError,
    ChainStep,
    Coform,
    EntityRef,
    GraphMutationBuilder,
    StepDependencyRef,
)

DIVISION_NAME = "SDK Sample - Task Briefing"
INTEGRATION_NAME = "SDK Sample Task API"


def openapi_document() -> str:
    """Describe two public, read-only JSONPlaceholder demonstration endpoints."""
    return json.dumps(
        {
            "openapi": "3.0.3",
            "info": {
                "title": INTEGRATION_NAME,
                "version": "1.0.0",
                "description": "Public fictitious users and tasks for the SDK sample.",
            },
            "servers": [{"url": "https://jsonplaceholder.typicode.com"}],
            "paths": {
                "/users/{userId}": {
                    "get": {
                        "operationId": "getDemoUser",
                        "summary": "Read a demonstration user profile",
                        "parameters": [
                            {
                                "name": "userId",
                                "in": "path",
                                "required": True,
                                "description": "Fictitious user identifier; use 1 for the example.",
                                "schema": {"type": "integer", "default": 1},
                            }
                        ],
                        "responses": {"200": {"description": "Fictitious user profile"}},
                    }
                },
                "/todos": {
                    "get": {
                        "operationId": "getDemoTasks",
                        "summary": "Read demonstration tasks for a user",
                        "parameters": [
                            {
                                "name": "userId",
                                "in": "query",
                                "required": False,
                                "description": "Filter tasks by fictitious user identifier.",
                                "schema": {"type": "integer", "default": 1},
                            }
                        ],
                        "responses": {"200": {"description": "Fictitious task list"}},
                    }
                },
            },
        }
    )


def connected_models(client: Coform) -> list[dict[str, Any]]:
    """Read model choices without exposing provider credentials."""
    return list(client.catalogs.connected_models()["models"])


def select_model(
    models: list[dict[str, Any]],
    connection_id: str | None,
    model_name: str | None,
) -> dict[str, Any]:
    """Select an existing language-model connection before any mutation occurs."""
    candidates = [
        model
        for model in models
        if (connection_id is None or model["model_connection_id"] == connection_id)
        and (model_name is None or model["model_name"] == model_name)
        and model.get("model_name")
        and not any(word in model["model_name"].lower() for word in ("embed", "rerank"))
    ]
    if not candidates:
        raise ValueError("No matching connected language model; inspect and supply a model choice.")
    choice = candidates[0]
    return {
        "model_connection_id": choice["model_connection_id"],
        "model_name": choice["model_name"],
        "provider": choice["model_provider"],
    }


def build_graph(
    name: str,
    model: dict[str, Any],
    endpoints: dict[str, str],
) -> GraphMutationBuilder:
    """Stage entities and attachments, preserving request-local references.

    Chain steps are saved separately after the new chain receives its server ID.
    The current server's dry-run validator queries the database for a chain even
    when it is a temporary creation in the same batch.
    """
    graph = GraphMutationBuilder.new_root(
        "division",
        {
            "division_name": name,
            "division_type": "conversational",
            "description": "SDK sample: research fictitious user tasks and produce a concise briefing.",
            "supported_languages": ["en"],
            "division_rules": (
                "For task-briefing requests, route to Briefing Coordinator. "
                "Use demonstration data only. Do not claim any external task was changed."
            ),
            "active": False,
            **model,
        },
    )
    functions = {}
    for key, title, description, location in [
        ("user", "Get Demo User", "Read a fictitious user's profile.", "path"),
        ("tasks", "Get Demo Tasks", "Read a fictitious user's task list.", "query"),
    ]:
        functions[key] = graph.create_entity(
            "agentic_function",
            {
                "name": title,
                "description": description,
                "input_description": "userId is the fictitious user ID; use 1 by default.",
                "api_function_id": endpoints[key],
                "agentic_response": False,
                "if_success_terminate": False,
                "parameters": [
                    {
                        "name": "userId",
                        "description": "Fictitious user identifier.",
                        "value_type": "integer",
                        "location": location,
                        "required": location == "path",
                        "default_value": "1",
                        "is_session_parameter": True,
                    }
                ],
            },
            temp_id=f"{key}-function",
        )

    common = {"supported_languages": ["en"], "active": True, "max_iteration": 5, **model}
    researcher = graph.create_entity(
        "swift_agent",
        {
            **common,
            "name": "Task Researcher",
            "task_name": "Research demonstration tasks",
            "description": "Retrieve a demo user's tasks and report verified counts.",
            "input_description": "Task-briefing request and optional userId (default 1).",
            "task_instructions": (
                "Use Get Demo Tasks and the attached user-profile context. Count completed and "
                "pending tasks. List up to five pending task titles. Return facts with userId "
                "and source URLs; report retrieval failures without inventing results."
            ),
        },
        temp_id="researcher",
    )
    writer = graph.create_entity(
        "swift_agent",
        {
            **common,
            "name": "Briefing Writer",
            "task_name": "Write a demonstration task briefing",
            "description": "Turn the researcher's facts into a short, useful briefing.",
            "input_description": "Verified research output from the preceding chain step.",
            "task_instructions": (
                "Produce a short Markdown briefing with user, completed/pending counts, "
                "up to five pending tasks, and suggested priorities. Clearly label the data "
                "as fictitious demonstration data. Preserve any reported retrieval failure."
            ),
        },
        temp_id="writer",
    )
    coordinator = graph.create_entity(
        "flow_agent",
        {
            **common,
            "name": "Briefing Coordinator",
            "task_name": "Coordinate task briefings",
            "description": "Conversational entry point for the sample task-briefing workflow.",
            "input_description": "A request such as: Brief me on the tasks for demo user 1.",
            "task_instructions": (
                "Explain that this sample uses fictitious public demo data. For briefing "
                "requests invoke Task Briefing Pipeline, passing userId (default 1). "
                "Return its briefing. Ask a short clarification for unrelated requests."
            ),
        },
        temp_id="coordinator",
    )
    chain = graph.create_entity(
        "swift_chain",
        {
            "name": "Task Briefing Pipeline",
            "description": "Research tasks, then write a briefing from the verified research.",
            "input_description": "A task-briefing request with userId (default 1).",
        },
        temp_id="briefing-chain",
    )
    for agent in (coordinator, researcher, writer):
        graph.attach_relation("division_agents", graph.root, agent)
    graph.attach_relation("division_swift_chains", graph.root, chain)
    graph.attach_relation(
        "agent_actions",
        researcher,
        functions["tasks"],
        relation_data={
            "action_type": "agentic_function",
            "include_parent_augmentation": True,
            "output_visible_outside": True,
        },
    )
    graph.attach_relation(
        "agent_actions",
        researcher,
        functions["user"],
        relation_data={
            "action_type": "agentic_function",
            "include_parent_augmentation": True,
            "output_visible_outside": True,
        },
    )
    graph.attach_relation("static_augmentation_functions", researcher, functions["user"])
    graph.attach_relation(
        "agent_actions",
        coordinator,
        chain,
        relation_data={
            "action_type": "swift_chain",
            "include_parent_augmentation": True,
            "output_visible_outside": True,
        },
    )
    return graph


def build_steps_graph(saved: dict[str, Any]) -> GraphMutationBuilder:
    """Stage the ordered chain and its dependency using the saved entity IDs."""
    root = EntityRef(entity_type="division", entity_id=saved["root"]["entity_id"])
    ids = saved["id_map"]
    graph = GraphMutationBuilder(root, base_graph_revision=saved["new_graph_revision"])
    graph.replace_collection(
        "swift_chain_steps",
        EntityRef(entity_type="swift_chain", entity_id=ids["briefing-chain"]),
        [
            ChainStep(
                temp_id="research-step",
                step_type="swift_agent",
                entity_ref=EntityRef(entity_type="swift_agent", entity_id=ids["researcher"]),
                order_index=0,
                is_output_hidden_outside_the_chain=True,
            ),
            ChainStep(
                temp_id="writing-step",
                step_type="swift_agent",
                entity_ref=EntityRef(entity_type="swift_agent", entity_id=ids["writer"]),
                order_index=1,
                is_dependent_to_main_chain_input=False,
                output_dependency_refs=[StepDependencyRef(temp_id="research-step")],
            ),
        ],
    )
    return graph


def run(
    client: Coform,
    *,
    name: str = DIVISION_NAME,
    connection_id: str | None = None,
    model_name: str | None = None,
    allow_unconfigured: bool = False,
) -> dict[str, Any]:
    """Import sample endpoints, validate and save the map, then verify retrieval.

    Existing sample Divisions are returned rather than modified or duplicated.
    Integration upload, entity creation, and chain-step save are separate server
    transactions to accommodate the server's new-chain validation limitation. The
    integration/request IDs are printed before commit so interrupted runs can
    be reconciled; this function does not retry or delete any resource.
    """
    existing = next(
        (
            division
            for division in client.divisions.iter_all()
            if division.get("division_name") == name
        ),
        None,
    )
    if existing:
        division_id = existing["division_id"]
        client.divisions.map(division_id)
        return {"status": "already_exists", "division_id": division_id, "name": name}
    models = connected_models(client)
    if not models and allow_unconfigured and connection_id is None and model_name is None:
        model = {}
    else:
        model = select_model(models, connection_id, model_name)
    catalog = client.catalogs.integrations()["integrations"]
    integration = next(
        (item for item in catalog if item["api_integration_name"] == INTEGRATION_NAME), None
    )
    if integration is None:
        integration = client.uploads.openapi_string(openapi_document())
    print(
        json.dumps({"integration_id": integration["api_integration_id"], "model": model}),
        flush=True,
    )
    endpoints = {}
    for function in integration["functions"]:
        if function["function_method"].upper() == "GET":
            if function["function_path"] == "/users/{userId}":
                endpoints["user"] = function["function_id"]
            elif function["function_path"] == "/todos":
                endpoints["tasks"] = function["function_id"]
    if set(endpoints) != {"user", "tasks"}:
        raise ValueError("The sample integration is missing its two expected GET endpoints.")
    graph = build_graph(name, model, endpoints)
    print(
        json.dumps({"request_id": graph.request_id, "operations": len(graph.operations)}),
        flush=True,
    )
    preview = client.graph.validate(graph)
    if preview.get("status") != "validated" or preview.get("operation_errors"):
        raise ValueError(f"Graph validation did not succeed: {preview}")
    saved = client.graph.commit(graph)
    division_id = saved["root"]["entity_id"]
    # Retain the server IDs even if the subsequent read fails; never replay commit.
    result = {
        "status": saved["status"],
        "name": name,
        "division_id": division_id,
        "integration_id": integration["api_integration_id"],
        "request_id": saved["request_id"],
        "id_map": saved["id_map"],
        "warnings": saved.get("warnings", []),
        "deployed": False,
        "model_configured": bool(model),
    }
    print(json.dumps(result, indent=2), flush=True)
    steps_graph = build_steps_graph(saved)
    print(json.dumps({"chain_steps_request_id": steps_graph.request_id}), flush=True)
    steps_preview = client.graph.validate(steps_graph)
    if steps_preview.get("status") != "validated" or steps_preview.get("operation_errors"):
        raise ValueError(f"Chain-step validation did not succeed: {steps_preview}")
    steps_saved = client.graph.commit(steps_graph)
    result["chain_steps_request_id"] = steps_saved["request_id"]
    result["id_map"].update(steps_saved["id_map"])
    client.divisions.map(division_id)
    result["map_retrieved"] = True
    return result


def main() -> int:
    """Run with environment credentials and print a credential-free result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="Read model choices only.")
    parser.add_argument("--name", default=DIVISION_NAME)
    parser.add_argument("--model-connection-id")
    parser.add_argument("--model-name")
    parser.add_argument(
        "--allow-unconfigured",
        action="store_true",
        help="Allow a model-free draft when no connected models exist.",
    )
    args = parser.parse_args()
    try:
        with Coform(timeout=30) as client:
            if args.inspect:
                print(json.dumps(connected_models(client), indent=2))
            else:
                print(
                    json.dumps(
                        run(
                            client,
                            name=args.name,
                            connection_id=args.model_connection_id,
                            model_name=args.model_name,
                            allow_unconfigured=args.allow_unconfigured,
                        ),
                        indent=2,
                    )
                )
    except APIConnectionError as error:
        print(f"SDK connection failed: {error.__cause__ or error}", file=sys.stderr)
        return 1
    except APIStatusError as error:
        print(
            f"Dashboard rejected the SDK request ({error.status_code}): {error.body}",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
