from typing import Any, Dict, List

from observe.event.base import Event


class AsyncEvent(Event):
    async def trigger(self, *args: List[Any], **kwargs: Dict[str, Any]) -> list[Any]:
        return await self._trigger(*args, run_async=True, **kwargs)
