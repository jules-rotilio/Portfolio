"""Listen to SoundTouch WebSocket push events (port 8080, subprotocol 'gabbo').

Usage: python3 ws_listen.py <speaker-ip> [seconds]
"""
import asyncio, sys, datetime
import websockets

async def main(host, seconds):
    async with websockets.connect(f"ws://{host}:8080", subprotocols=["gabbo"]) as ws:
        end = asyncio.get_event_loop().time() + seconds
        while (left := end - asyncio.get_event_loop().time()) > 0:
            try:
                msg = await asyncio.wait_for(ws.recv(), left)
            except asyncio.TimeoutError:
                break
            print(datetime.datetime.now().isoformat(timespec="seconds"), msg, flush=True)

asyncio.run(main(sys.argv[1],
                 float(sys.argv[2]) if len(sys.argv) > 2 else 60))
