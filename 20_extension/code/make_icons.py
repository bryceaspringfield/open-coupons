#!/usr/bin/env python3
"""Draws the toolbar icon (a white percent sign on a green rounded square) at 16, 32, 48, and 128 px, with no image library."""
import struct, sys, zlib

GREEN, WHITE = (31, 111, 67), (255, 255, 255)


def pixel(x, y, n):
    u, v = (x + 0.5) / n, (y + 0.5) / n
    r = 0.2  # corner radius as a share of the side
    cx, cy = min(max(u, r), 1 - r), min(max(v, r), 1 - r)
    if (u - cx) ** 2 + (v - cy) ** 2 > r * r:
        return (0, 0, 0, 0)
    ring = lambda ox, oy: 0.06 ** 2 <= (u - ox) ** 2 + (v - oy) ** 2 <= 0.14 ** 2
    slash = abs((u - 0.5) + (v - 0.5)) < 0.075 and 0.18 < u < 0.82
    return (*WHITE, 255) if ring(0.32, 0.32) or ring(0.68, 0.68) or slash else (*GREEN, 255)


def png(n):
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y, n)) for x in range(n)) for y in range(n))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


for n in (16, 32, 48, 128):
    open(f"{sys.argv[1]}/icon{n}.png", "wb").write(png(n))
