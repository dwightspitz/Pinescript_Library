#!/usr/bin/env python3
"""Emberfall server — asyncio TCP, zero dependencies.

Run:      python3 server.py [--host 0.0.0.0] [--port 4000]
Connect:  python3 client.py            (or: nc localhost 4000 / telnet)

Every connection gets a Player; lines are fed to the shared Game engine,
which handles character creation, commands, combat, and chat. A small
background task ticks the world for monster respawns and autosaves.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from rpg.game import Disconnect, Game

TICK_SECONDS = 5
AUTOSAVE_TICKS = 12  # roughly once a minute


async def handle_connection(game: Game, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter) -> None:
    def send(message: str) -> None:
        if not writer.is_closing():
            writer.write((message + "\r\n").encode("utf-8", "replace"))

    player = game.connect(send)
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip("\r\n")
            # Strip telnet negotiation bytes some clients send on connect.
            line = "".join(ch for ch in line if ch.isprintable())
            try:
                game.handle_line(player, line)
            except Disconnect:
                break
            await writer.drain()
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        game.disconnect(player)
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError):
            pass


async def world_ticker(game: Game) -> None:
    ticks = 0
    while True:
        await asyncio.sleep(TICK_SECONDS)
        game.tick()
        ticks += 1
        if ticks % AUTOSAVE_TICKS == 0:
            game.save_all()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Emberfall RPG server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=4000)
    parser.add_argument(
        "--save", default=os.path.join(os.path.dirname(__file__), "characters.json"),
        help="path to the character save file",
    )
    args = parser.parse_args()

    game = Game(save_path=args.save)
    server = await asyncio.start_server(
        lambda r, w: handle_connection(game, r, w), args.host, args.port,
    )
    addr = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"Emberfall is live on {addr} — connect with: python3 client.py")
    asyncio.ensure_future(world_ticker(game))
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down.")
