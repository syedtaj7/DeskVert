"""A tiny writer for Microsoft compound files (version 3), to build Outlook .msg test files.

Follows the format the way Outlook does: streams under 4096 bytes live in the mini stream, bigger
ones in ordinary sectors; storages hold their children as a (simple) tree.
"""

from __future__ import annotations

import struct

FREE, END, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF
SS, MSS, CUTOFF = 512, 64, 4096


def build(tree: dict) -> bytes:
    """tree: {name: bytes (a stream) | dict (a storage)} -> the compound file's bytes."""
    entries = [{"name": "Root Entry", "kind": 5, "kids": [], "data": b""}]

    def add(node: dict, parent: int):
        for name, val in node.items():
            i = len(entries)
            if isinstance(val, dict):
                entries.append({"name": name, "kind": 1, "kids": [], "data": b""})
                entries[parent]["kids"].append(i)
                add(val, i)
            else:
                entries.append({"name": name, "kind": 2, "kids": [], "data": val})
                entries[parent]["kids"].append(i)

    add(tree, 0)
    # the mini stream: small streams packed in 64-byte mini sectors
    mini, minifat = b"", []
    for e in entries:
        if e["kind"] == 2 and len(e["data"]) < CUTOFF:
            n = max(1, -(-len(e["data"]) // MSS)) if e["data"] else 0
            e["start"] = len(minifat) if n else END
            for k in range(n):
                minifat.append(len(minifat) + 1 if k < n - 1 else END)
            mini += e["data"].ljust(n * MSS, b"\0")
    big = [e for e in entries if e["kind"] == 2 and len(e["data"]) >= CUTOFF]
    dir_bytes_len = len(entries) * 128
    n_dir = -(-dir_bytes_len // SS)
    n_minifat = -(-len(minifat) * 4 // SS) if minifat else 0
    n_mini = -(-len(mini) // SS) if mini else 0
    n_big = [-(-len(e["data"]) // SS) for e in big]
    data_sectors = n_dir + n_minifat + n_mini + sum(n_big)
    n_fat = 1
    while n_fat * (SS // 4) < data_sectors + n_fat:
        n_fat += 1
    fat = [FATSECT] * n_fat
    sec = n_fat

    def chain(n: int) -> int:
        nonlocal sec
        if n == 0:
            return END
        start = sec
        for k in range(n):
            fat.append(sec + 1 if k < n - 1 else END)
            sec += 1
        return start

    first_dir = chain(n_dir)
    first_minifat = chain(n_minifat) if n_minifat else END
    entries[0]["start"] = chain(n_mini) if n_mini else END
    entries[0]["size"] = len(mini)
    for e, n in zip(big, n_big):
        e["start"] = chain(n)
    fat += [FREE] * (n_fat * (SS // 4) - len(fat))

    def dir_entry(i: int, left: int, right: int, child: int) -> bytes:
        e = entries[i]
        name = e["name"].encode("utf-16-le")[:62] + b"\0\0"
        size = e.get("size", len(e["data"]))
        start = e.get("start", END if e["kind"] != 1 else 0)
        return (name.ljust(64, b"\0") + struct.pack("<HBB", len(name), e["kind"], 1)
                + struct.pack("<III", left, right, child) + b"\0" * 16 + b"\0" * 4 + b"\0" * 16
                + struct.pack("<IQ", start if e["kind"] != 1 else 0, size if e["kind"] != 1 else 0))

    links = {i: (NOSTREAM, NOSTREAM, NOSTREAM) for i in range(len(entries))}
    for i, e in enumerate(entries):
        kids = e["kids"]
        if kids:  # children as a chain to the right: a valid (unbalanced) tree
            links[i] = (links[i][0], links[i][1], kids[0])
            for a, b in zip(kids, kids[1:] + [NOSTREAM]):
                links[a] = (NOSTREAM, b, links[a][2])
    dirs = b"".join(dir_entry(i, *links[i]) for i in range(len(entries))).ljust(n_dir * SS, b"\0")
    header = bytearray(512)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 0x18, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 0x28, 0, n_fat, first_dir, 0, CUTOFF, first_minifat, n_minifat, END, 0)
    difat = list(range(n_fat)) + [FREE] * (109 - n_fat)
    struct.pack_into("<109I", header, 0x4C, *difat)
    body = struct.pack(f"<{len(fat)}I", *fat)
    body += dirs
    if n_minifat:
        body += struct.pack(f"<{len(minifat)}I", *minifat).ljust(n_minifat * SS, b"\xff")
    body += mini.ljust(n_mini * SS, b"\0")
    for e, n in zip(big, n_big):
        body += e["data"].ljust(n * SS, b"\0")
    return bytes(header) + body


def text_prop(prop: int, value: str) -> tuple[str, bytes]:
    return f"__substg1.0_{prop:04X}001F", value.encode("utf-16-le")


def bin_prop(prop: int, value: bytes) -> tuple[str, bytes]:
    return f"__substg1.0_{prop:04X}0102", value
