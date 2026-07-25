"""Seeded `/node` container responses for Fake M32."""

from __future__ import annotations

SEEDED_NODES: dict[str, list[str]] = {
    "/": ["/ch", "/bus", "/main", "/headamp", "/routing"],
    "/ch": [f"/ch/{i:02d}" for i in range(1, 33)],
    "/bus": [f"/bus/{i:02d}" for i in range(1, 17)],
    "/main": ["/main/st", "/main/m"],
    "/routing": ["/routing/in", "/routing/out"],
}


def node_children(path: str) -> list[str]:
    return SEEDED_NODES.get(path, [])

