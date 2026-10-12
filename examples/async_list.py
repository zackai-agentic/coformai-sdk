"""List Divisions asynchronously. Requires agents:read and four COFORM_* variables.

Expected outcome: Division dictionaries across all pages, printed as a list.
"""
import asyncio
from typing import Any
from coformai import AsyncCoform


async def run(client: AsyncCoform) -> list[dict[str, Any]]:
    """Read all available Division pages using a safe pagination iterator."""
    return [division async for division in client.divisions.iter_all()]


async def main() -> None:
    """Resolve credentials from environment and close the client on completion."""
    async with AsyncCoform() as client:
        print(await run(client))


if __name__ == "__main__":
    asyncio.run(main())
