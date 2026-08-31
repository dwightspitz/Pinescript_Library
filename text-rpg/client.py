#!/usr/bin/env python3
"""Minimal Emberfall client — works anywhere Python does.

Usage: python3 client.py [host] [port]

Netcat (``nc localhost 4000``) or telnet work just as well; this exists
mainly for platforms without either.
"""

from __future__ import annotations

import socket
import sys
import threading


def receive_loop(sock: socket.socket) -> None:
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            sys.stdout.write(data.decode("utf-8", "replace"))
            sys.stdout.flush()
    except OSError:
        pass
    print("\n[Disconnected from server]")
    sys.exit(0)


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    sock = socket.create_connection((host, port))
    threading.Thread(target=receive_loop, args=(sock,), daemon=True).start()
    try:
        for line in sys.stdin:
            sock.sendall(line.encode("utf-8"))
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
