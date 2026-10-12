"""Create a Division and task agent atomically. Requires agents:write.

Set the four COFORM_* configuration variables. Expected outcome: the server's
graph save response with resolved temporary IDs. This creates saved resources.
"""
from typing import Any
from coformai import Coform, GraphMutationBuilder


def run(client: Coform) -> Any:
    """Save a minimal automation draft; configure a model before deployment."""
    builder = GraphMutationBuilder.new_root("division", {
        "division_name": "SDK Example", "division_type": "automation",
        "supported_languages": ["en"],
    })
    agent = builder.create_entity("swift_agent", {
        "name": "Reporter", "task_name": "Report", "task_instructions": "Summarize inputs.",
        "supported_languages": ["en"],
    })
    builder.attach_relation("division_agents", builder.root, agent)
    client.graph.validate(builder)
    return client.graph.commit(builder)


if __name__ == "__main__":
    with Coform() as client:
        print(run(client))
