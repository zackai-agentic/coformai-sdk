# Creating and editing a Division map

## UI terminology

| Dashboard term | Wire term / SDK resource |
|---|---|
| Division | `division` / `client.divisions` |
| Task agent | `swift_agent` / `client.swift_agents` |
| Conversational agent | `flow_agent` / `client.flow_agents` |
| Task chain | `swift_chain` / `client.swift_chains` |
| Conversational chain | `flow_chain` / `client.flow_chains` |
| Agentic Function | Wrapper `agentic_function`, distinct from an integration endpoint |
| REST endpoint / MCP tool | `APIIntegrationFunction` / `client.integration_functions(id)` |
| Static / dynamic context | Static / dynamic augmentation relations |
| Map occurrence | Parent-to-child relationship; detach to remove |
| Permanent entity delete | `delete_entity` or resource `delete()` |

## Build a new graph atomically

Requires `agents:write` for this example. Newly created children do not require
read just to attach inside the same request. Model connections or other reused
objects require their selected read grants.

```python
from coformai import Coform, GraphMutationBuilder

builder = GraphMutationBuilder.new_root("division", {
    "division_name": "Support", "division_type": "conversational",
    "description": "Support routing", "supported_languages": ["en"],
})
agent = builder.create_entity("flow_agent", {
    "name": "Support agent", "task_name": "Support",
    "task_instructions": "Answer from the attached context.",
    "supported_languages": ["en"],
}, temp_id="support-agent")
builder.attach_relation("division_agents", builder.root, agent)

with Coform() as client:
    preview = client.graph.validate(builder)
    saved = client.graph.commit(builder)
    print(saved)
```

Validation executes server validation without persisting. Save responses include
temporary-ID resolution and graph state; retain returned IDs for subsequent
requests. Server serializer validation decides required profile fields and
Division type values. Use the catalog for valid model configuration. Graph
revision/request IDs preserve the dashboard contract; they do not promise
deduplication or safe replay.
Wire Division types are lowercase: `conversational` and `automation`. A new
root commit returns HTTP 201 with `status="committed"` and `id_map`; validation
returns HTTP 200 without saving. Minimal automation drafts can report the
server's missing-Octopus-manifest warning because this SDK excludes UI generation.

The remaining snippets use an open `Coform` client and saved UUIDs from your map.
Read the current graph revision before each independent change. Create a fresh
builder after each commit; a builder retains its operations and must not be
reused to replay a completed request.

## Reuse, patch, detach, and permanently delete

```python
from coformai import EntityRef, GraphMutationBuilder

root = EntityRef(entity_type="division", entity_id=division_id)
existing = EntityRef(entity_type="swift_agent", entity_id=agent_id)
builder = GraphMutationBuilder(root, base_graph_revision=revision)
builder.attach_relation("division_agents", root, existing)
builder.patch_entity(existing, {"description": "Updated reusable profile"})
client.graph.commit(builder)

remove = GraphMutationBuilder(root, base_graph_revision=revision)
remove.detach_relation("division_agents", root, existing)
client.graph.commit(remove)
```

Attach/detach requires root `agents:write` and existing-child `agents:read`.
Profile patches require the child's write grant and affect every Division using
that entity. Detach changes only a relationship. Permanent deletion uses
`builder.delete_entity(existing)` and requires `agents:delete` as well as root
write; root Division deletion uses `client.divisions.delete(division_id)`.

## Actions and context links

```python
function = EntityRef(entity_type="agentic_function", entity_id=function_id)
builder = GraphMutationBuilder(root, base_graph_revision=current_revision)
builder.attach_relation("agent_actions", existing, function, relation_data={
    "include_parent_augmentation": True, "output_visible_outside": True,
})
builder.attach_relation("static_augmentation_functions", existing, function)
builder.attach_relation("dynamic_augmentation_sources", existing,
    EntityRef(entity_type="source", entity_id=source_id),
    relation_data={"top_k": 5})
client.graph.commit(builder)
```

These links require agent write plus function/source read. Relation metadata is
preserved verbatim; action settings change the occurrence. Direct resource APIs
also expose `actions`, `static_augmentations`, and `dynamic_augmentations`.
For example, create an action using `parent_id`, `child_function_id`, and
`action_type="agentic_function"`.

## Ordered chains and dependencies

```python
from coformai import ChainStep, StepDependencyRef

chain = EntityRef(entity_type="swift_chain", entity_id=chain_id)
builder = GraphMutationBuilder(root, base_graph_revision=current_revision)
builder.replace_collection("swift_chain_steps", chain, [
    ChainStep(temp_id="first", step_type="swift_agent", entity_ref=existing,
              order_index=0),
    ChainStep(temp_id="second", step_type="agentic_function", entity_ref=function,
              order_index=1, is_dependent_to_main_chain_input=False,
              output_dependency_refs=[StepDependencyRef(temp_id="first")]),
])
client.graph.commit(builder)
```

Replacement sets the entire ordered collection and its dependencies. Include
every step to retain. `step_id` reuses saved step references; `temp_id` correlates
new steps and dependencies in the same request. Chain write and existing target
agent/function read are required. Removing a step does not permanently delete
its reusable target. Flow steps additionally support
`forward_agentic_function_ref`. Direct APIs expose `swift_chain_steps`,
`flow_chain_steps`, and `dependencies`.

## Samples and function parameters

Patch `orchestration_samples` on a Division or `invocation_samples` on an agent.
For graph patches, each sample has a description and `turns`, containing
`entity_relations` (Division) or `action_relations` (agent). Keep saved `sample_id`
values to edit existing samples. Send the complete collection to retain the
desired samples; an empty list removes occurrences. Referenced existing
entities/actions need read access and must belong to the same organization.

```python
builder = GraphMutationBuilder(root, base_graph_revision=current_revision)
builder.patch_entity(root, {"orchestration_samples": [{
    "description": "A support turn", "turns": [{
        "turn_order_index": 0, "user_prompt": "Help with my account", "entity_relations": [{
            "entity_type": "base_agent", "entity_id": agent_id,
            "entity_refined_inquiry": "Provide account help",
        }],
    }],
}]})
builder.patch_entity(function, {"parameters": [{
    "name": "account", "description": "Account identifier",
    "value_type": "string", "location": "query", "is_session_parameter": True,
}]})
client.graph.validate(builder)
client.graph.commit(builder)
```

Wrapper parameter changes require `functions:write`; saved parameters use
`action_parameter_id` or their existing name. Parameter graph patches upsert
the supplied rows; omission and an empty list do not remove parameters. Delete
a parameter explicitly through `client.function_parameters(function_id).delete(parameter_id)`
with `functions:delete`. The direct factory
`client.function_parameters(function_id)` provides CRUD methods. Payload fields
are backend-specific; inspect profiles/maps and preserve fields needed by your
server's validators. Raw graph dictionaries and `GraphMutationRequest` are also
accepted by `client.graph.validate()` and `commit()`.

Direct sample serializers merge by default. To remove omitted samples through
`divisions.update()` or an agent's `update()`, pass `replace_orchestration_samples=True`
or `replace_invocation_samples=True` respectively. Removing persisted samples or
function parameters requires the corresponding delete grant as well as write.
