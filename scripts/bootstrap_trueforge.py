"""Register EDITH's local MCP connector and four profiles in TrueForge."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.trueforge_service import get_trueforge_service


async def main() -> None:
    result = await get_trueforge_service().bootstrap()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
