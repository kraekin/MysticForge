"""Load saved composed placements (auto-solved or hand-puzzled) for an enemy.

A placement maps grid cells -> (tile_index) using an enemy's ROM tile
block. When a placement exists for an enemy, the editor shows the composed
sprite; otherwise it falls back to the tile list.

Shipped placements live in the package at ``data/battle_sprites/placements``.
Any placements the user produces locally (e.g. with the puzzle web tool) under
``research/cut-sprites/placements`` override the shipped ones, so hand fixes are
picked up without editing the packaged data.
"""
import os, json

_PKG = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PKG))

def _placement_dirs():
    """Shipped data first, then optional local (gitignored) override dirs."""
    return [
        os.path.join(_PKG, "data", "battle_sprites", "placements"),
        os.path.join(_REPO, "etc", "cut-sprites", "placements"),
        os.path.join(_REPO, "research", "cut-sprites", "placements"),
    ]

def load_all():
    """Return {enemy_id: [ {frameName,frameIndex,cols,rows,placement,...}, ... ]}.

    Later directories override earlier ones for the same (name, frameIndex)."""
    merged = {}
    for d in _placement_dirs():
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            try:
                o = json.load(open(os.path.join(d, fn)))
            except (OSError, ValueError):
                continue
            key = (o.get("frameName"), o.get("frameIndex"))
            merged[key] = o
    out = {}
    for o in merged.values():
        out.setdefault(int(o.get("enemy", -1)), []).append(o)
    return out
