#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: apply-v4-plus.py PATH_TO_APP")
root = Path(sys.argv[1]).resolve()

def patch(rel, old, new):
    p = root / rel
    s = p.read_text(encoding="utf-8")
    if new in s:
        return
    if old not in s:
        raise RuntimeError(f"v4 Plus patch drifted: {rel}")
    p.write_text(s.replace(old, new, 1), encoding="utf-8")

# GitHub Pages is hosted below /shpd-seed-seeker-plus/. Upstream absolute
# atlas URLs are correct for Firebase root hosting but 404 on GitHub Pages.
patch(
    "web/src/lib/sprites.ts",
    'const SHEET_URL = "/third_party/shattered-pixel-dungeon/items.png";',
    'const SHEET_URL = `${import.meta.env.BASE_URL}third_party/shattered-pixel-dungeon/items.png`;'
)
patch(
    "web/src/lib/sprites.ts",
    'const ICON_SHEET_URL = "/third_party/shattered-pixel-dungeon/item_icons.png";',
    'const ICON_SHEET_URL = `${import.meta.env.BASE_URL}third_party/shattered-pixel-dungeon/item_icons.png`;'
)
print("Applied v4 Plus GitHub Pages sprite paths")
