"""Windows local server with a filesystem stop signal and graceful ASGI shutdown."""
import asyncio
import os
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
SIGNAL = ROOT / 'data' / f'stop-{os.getpid()}'


async def run():
    SIGNAL.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL.unlink(missing_ok=True)
    (ROOT / "data" / "runtime-pid.txt").write_text(str(os.getpid()))
    server = uvicorn.Server(uvicorn.Config('main:app', host='127.0.0.1', port=8000, timeout_graceful_shutdown=10))

    async def watch():
        while not server.should_exit:
            if SIGNAL.exists():
                SIGNAL.unlink(missing_ok=True)
                server.should_exit = True
                return
            await asyncio.sleep(.5)

    watcher = asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(run())
