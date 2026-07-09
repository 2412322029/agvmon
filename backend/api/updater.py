"""
Update API routes for AGVmon.

Endpoints:
    GET  /api/update/check     — check for newer version
    GET  /api/update/download  — SSE stream to download update ZIP
    POST /api/update/apply     — extract + prepare + trigger restart
    GET  /api/update/status    — current update state
"""

import asyncio
import json
import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

update_router = APIRouter(tags=["update"])


@update_router.get("/update/check")
async def check_update():
    """Check if a newer version is available on the update server."""
    from util.updater import get_updater

    updater = get_updater()
    result = await updater.check()
    return result


@update_router.get("/update/download")
async def download_update():
    """Stream the update ZIP download via SSE with progress events."""
    from util.updater import get_updater

    updater = get_updater()

    async def event_stream():
        async for event in updater.download():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@update_router.post("/update/apply")
async def apply_update():
    """Extract the downloaded update and trigger restart."""
    from util.updater import get_updater

    updater = get_updater()
    result = updater.apply()

    # Schedule shutdown so the HTTP response is sent first
    if result.get("status") == "applying":

        def _exit():
            os._exit(0)

        loop = asyncio.get_event_loop()
        loop.call_later(1, _exit)

    return result


@update_router.get("/update/status")
async def update_status():
    """Get current update state."""
    from util.updater import get_updater

    updater = get_updater()
    return {
        "status": updater.status,
        "message": updater.status_message,
    }
