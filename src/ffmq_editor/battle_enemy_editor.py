"""In-battle enemy editor with composed + tile views.

Verified layout: an 83-entry pointer table at $098460 -> each enemy's contiguous
3bpp (24-byte) tile block in banks $09-$0B.

- Composed view: when a placement exists (shipped under data/battle_sprites/, or
  a local override; score >= 0.98), the enemy is shown as ONE image assembled
  from its tiles; clicking a region edits the underlying tile. The tile's own
  palette (derived from the reference art) is used for the edit canvas.
- Tile view: always available (the raw tile list). Enemies without a placement
  default to this.
- PNG export/import lets you edit a whole frame externally.

All edits are sparse ``battle_graphic`` edits keyed by tile file offset: they
persist in the project, flow through undo/redo, and are written on export.
"""
import os
import numpy as np
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QIcon, QImage
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QListWidget, QListWidgetItem, QRadioButton, QCheckBox,
)
from .pixel_editor import PixelCanvas
from .pixels import encode_3bpp
from .render import decode_3bpp, qimage
from .resources import (
    battle_enemy_entries, battle_owned_ends, span, FormatError,
)
from .battle_placements import load_all as load_placements

THUMB = 56
COMPOSED_MIN_SCORE = 0.98


_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_DIR = os.path.dirname(os.path.dirname(_PKG_DIR))


def _cut_dirs():
    """Where reference art / frames.json may live.

    frames.json + placements ship in the package (data/battle_sprites). The
    reference PNGs are NOT committed (copyrighted); they are picked up from the
    package dir, or from a local scratch dir (etc/cut-sprites or
    research/cut-sprites) if the user has them there. Missing art degrades to a
    fallback palette; the composed shape still renders from placements + ROM."""
    return [os.path.join(_PKG_DIR, "data", "battle_sprites"),
            os.path.join(_REPO_DIR, "etc", "cut-sprites"),
            os.path.join(_REPO_DIR, "research", "cut-sprites")]


def _cut_dir(base_rom_path):
    return _cut_dirs()[0]


def _find_cut_file(name):
    for d in _cut_dirs():
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def _load_frames_json(base_rom_path):
    import json
    p = _find_cut_file("frames.json")
    if p:
        try:
            return json.load(open(p))
        except (OSError, ValueError):
            return None
    return None


def _valid_tile(t):
    try:
        span("battle_graphic", t); return True
    except FormatError:
        return False


class ComposedImage(QWidget):
    """Paints the composed frame; maps a click to the underlying tile offset.
    Optionally overlays a light tile grid and marks non-drawable cells."""
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.rgba = None
        self.scale = 6
        self._img = None
    def set_rgba(self, rgba):
        self.rgba = rgba
        if rgba is not None and rgba.size:
            self._img = qimage(rgba)
            self.setMinimumSize(rgba.shape[1]*self.scale, rgba.shape[0]*self.scale)
            self.setFixedSize(rgba.shape[1]*self.scale, rgba.shape[0]*self.scale)
        else:
            self._img = None
            self.setMinimumSize(1, 1); self.setFixedSize(1, 1)
        self.updateGeometry(); self.update()
    def sizeHint(self):
        if self._img is not None:
            return QSize(self._img.width()*self.scale, self._img.height()*self.scale)
        return QSize(1, 1)
    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QPen
        p = QPainter(self)
        if self._img is None:
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(self.rect(), self._img)
        cols = getattr(self.editor, "_composed_cols", 0)
        if not cols:
            return
        rows = self._img.height() // 8
        cw = self.width() / (cols*8); ch = self.height() / (rows*8)
        # dark overlay on cells with no backing tile (not drawable)
        if getattr(self.editor, "show_locked", False):
            drawable = set(self.editor._composed or {})
            lock = QColor(20, 24, 32, 150)
            for ri in range(rows):
                for ci in range(cols):
                    if (ri*cols + ci) not in drawable:
                        p.fillRect(int(ci*8*cw), int(ri*8*ch), int(8*cw), int(8*ch), lock)
        # light tile grid
        if getattr(self.editor, "show_grid", False):
            pen = QPen(QColor(255, 255, 255, 45)); pen.setCosmetic(True); pen.setWidth(1)
            p.setPen(pen)
            for ci in range(1, cols):
                x = int(ci*8*cw); p.drawLine(x, 0, x, self.height())
            for ri in range(1, rows):
                y = int(ri*8*ch); p.drawLine(0, y, self.width(), y)
    def mousePressEvent(self, event):
        if self.rgba is None:
            return
        s = self.scale
        px = int(event.position().x())//s; py = int(event.position().y())//s
        self.editor.composed_clicked(px, py)


class BattleEnemyWindow(QMainWindow):
    def __init__(self, w):
        super().__init__(w)
        self.w = w
        self.loading = False
        self.resource = None
        self.clipboard = None
        self.color = 1
        self.pixels = np.zeros((8, 8), dtype=np.uint8)
        self.colors = [(0, 0, 0)] * 8
        self.entries = battle_enemy_entries(w.project.base_rom.data)
        self.ends = battle_owned_ends(self.entries)
        self.placements = load_placements()
        self.frames_json = _load_frames_json(str(w.project.base_rom.path))
        self._pal_cache = {}
        self.names = self._load_names()
        # composed layout for the current selection: cell -> (tile_offset, palette)
        self._composed = None
        self._composed_cols = 0
        self._composed_scale = 6
        self.show_grid = True
        self.show_locked = True
        self.setWindowTitle("MysticForge — Battle enemy graphics editor")
        self.resize(1120, 800)

        root = QWidget(); self.setCentralWidget(root); box = QVBoxLayout(root)
        note = QLabel(
            "In-battle enemy sprites (verified 3bpp art from the $098460 table). "
            "Composed = one assembled image (for enemies the solver placed well); Tiles = the raw "
            "tile list. Editing either changes the same underlying art and is written on export."
        )
        note.setWordWrap(True); box.addWidget(note)

        top = QHBoxLayout()
        top.addWidget(QLabel("Enemy"))
        self.enemy = QComboBox()
        for i, off, fl in self.entries:
            n = self._tile_count(off)
            if n == 0:
                continue  # skip junk table entries (no art)
            nm = self.names.get(i) or f"Enemy {i:02X}"
            self.enemy.addItem(f"{nm}  (id {i:02X}, {n} tiles)", i)
        top.addWidget(self.enemy, 1)
        top.addWidget(QLabel("Frame"))
        self.frame = QComboBox(); top.addWidget(self.frame)
        top.addWidget(QLabel("Palette"))
        self.palette = QComboBox()
        self.palette.addItem("Auto (cut art)", -1)
        for p in range(8): self.palette.addItem(f"OBJ {p}", p)
        self.palette.setCurrentIndex(0)
        self.palette.currentIndexChanged.connect(self.reload)
        top.addWidget(self.palette)
        box.addLayout(top)

        mode = QHBoxLayout()
        self.rb_composed = QRadioButton("Composed"); self.rb_tiles = QRadioButton("Tiles")
        self.rb_composed.clicked.connect(self.reload); self.rb_tiles.clicked.connect(self.reload)
        mode.addWidget(self.rb_composed); mode.addWidget(self.rb_tiles)
        self.chk_grid = QCheckBox("Tile grid"); self.chk_grid.setChecked(True)
        self.chk_locked = QCheckBox("Mark non-drawable"); self.chk_locked.setChecked(True)
        self.chk_grid.toggled.connect(lambda v: (setattr(self, "show_grid", v), self.comp.update()))
        self.chk_locked.toggled.connect(lambda v: (setattr(self, "show_locked", v), self.comp.update()))
        mode.addSpacing(12); mode.addWidget(self.chk_grid); mode.addWidget(self.chk_locked)
        mode.addStretch()
        box.addLayout(mode)

        self.info = QLabel(); self.info.setWordWrap(True); box.addWidget(self.info)

        middle = QHBoxLayout()
        from PySide6.QtWidgets import QStackedWidget, QScrollArea
        self.view_stack = QStackedWidget(); middle.addWidget(self.view_stack, 1)
        # composed view
        self.comp = ComposedImage(self)
        self.comp_area = QScrollArea(); self.comp_area.setWidget(self.comp); self.comp_area.setWidgetResizable(False)
        self.comp_idx = self.view_stack.addWidget(self.comp_area)
        # tile view
        self.tiles = QListWidget()
        self.tiles.setViewMode(QListWidget.ViewMode.IconMode)
        self.tiles.setIconSize(QSize(THUMB, THUMB)); self.tiles.setGridSize(QSize(THUMB+16, THUMB+16))
        self.tiles.setResizeMode(QListWidget.ResizeMode.Adjust); self.tiles.setMovement(QListWidget.Movement.Static)
        self.tiles.setWordWrap(True); self.tiles.itemSelectionChanged.connect(self._select_from_list)
        self.tiles_idx = self.view_stack.addWidget(self.tiles)

        side = QVBoxLayout()
        self.canvas = PixelCanvas(self); self.canvas.on_paint = self._live_update
        side.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignTop)
        self.swatches = []; colors = QHBoxLayout()
        for i in range(8):
            b = QPushButton(str(i)); b.setCheckable(True); b.setMinimumSize(40, 40)
            b.clicked.connect(lambda _, i=i: self.choose_color(i)); colors.addWidget(b); self.swatches.append(b)
        side.addLayout(colors)
        self.color_label = QLabel(); side.addWidget(self.color_label)
        hint = QLabel("Color 0 is transparent. Right-click picks a color. Drag to paint; each stroke is one undo step. Escape cancels.")
        hint.setWordWrap(True); side.addWidget(hint)
        self.edit_buttons = []
        for label, fn in [("Copy tile", self.copy), ("Paste tile", self.paste),
                          ("Flip H", lambda: self.commit(self.pixels[:, ::-1].copy(), "Flip battle graphic horizontally")),
                          ("Flip V", lambda: self.commit(self.pixels[::-1, :].copy(), "Flip battle graphic vertically")),
                          ("Restore tile", self.restore)]:
            b = QPushButton(label); b.clicked.connect(fn); side.addWidget(b); self.edit_buttons.append(b)
        side.addStretch(); middle.addLayout(side, 1)
        box.addLayout(middle)

        tools = QHBoxLayout()
        self.tool = QComboBox(); self.tool.addItems(["Pencil", "Eraser", "Fill", "Pick color"]); tools.addWidget(self.tool)
        for label, fn in [("Undo", self.undo), ("Redo", self.w.stack.redo)]:
            b = QPushButton(label); b.clicked.connect(fn); tools.addWidget(b)
        tools.addStretch()
        for label, fn in [("Export PNG…", self.export_png), ("Import PNG…", self.import_png)]:
            b = QPushButton(label); b.clicked.connect(fn); tools.addWidget(b)
        box.addLayout(tools)
        self.feedback = QLabel("Edits apply immediately; export writes a ROM copy."); self.feedback.setWordWrap(True); box.addWidget(self.feedback)

        self.enemy.currentIndexChanged.connect(self._populate_frames)
        self.frame.currentIndexChanged.connect(self.reload)
        self._populate_frames()

    # -- data helpers -------------------------------------------------------
    def _offsets(self, off):
        end = self.ends.get(off); out = []
        if not end: return out
        t = off
        while t + 24 <= end:
            if _valid_tile(t): out.append(t)
            t += 24
        return out

    def _tile_count(self, off):
        return len(self._offsets(off))

    def _load_names(self):
        names = {}
        try:
            from .database import name as dec_name
        except Exception:
            return names
        data = self.w.project.base_rom.data
        for i in range(81):
            try:
                off, size = span("monster_name", i)
                nm = dec_name(data[off:off+size]).strip()
                if nm:
                    names[i] = nm
            except (FormatError, Exception):
                pass
        return names

    def _placements_for(self, eid):
        return sorted(self.placements.get(eid, []), key=lambda p: p.get("frameIndex", 0))

    def _populate_frames(self, *_):
        eid = self.enemy.currentData()
        self.frame.blockSignals(True); self.frame.clear()
        for p in self._placements_for(eid):
            label = p.get("frameName", "frame")
            self.frame.addItem(f"{label}#{p.get('frameIndex',0)}", 0)
        self.frame.addItem("(tiles only)", -1)
        # default mode: composed if best placement is good
        def good_placement(p):
            # A placement with no score is a manual (web-tool) save -> trusted.
            sc = p.get("score")
            return bool(p.get("placement")) and (sc is None or sc >= COMPOSED_MIN_SCORE)
        good = [p for p in self._placements_for(eid) if good_placement(p)]
        self._use_composed = bool(good)
        self.rb_composed.setEnabled(bool(good)); self.rb_tiles.setChecked(not good)
        if good: self.rb_composed.setChecked(True)
        # default to the first GOOD frame (skip a bad frame 0)
        plist = self._placements_for(eid)
        first_good = next((i for i in range(self.frame.count())
                           if i < len(plist) and good_placement(plist[i])), 0)
        self.frame.setCurrentIndex(first_good)
        self.frame.blockSignals(False)
        self.reload()

    # -- palette / colors ---------------------------------------------------
    def _obj_palette(self, idx):
        return [tuple(int(c) for c in rgb) for rgb in self.w.renderer.sprites.colors([idx])[0]]

    def _frame_box(self, name, index):
        if not self.frames_json:
            return None
        for m in self.frames_json.get("images", []):
            if m.get("name") == name:
                for fr in m["frames"]:
                    if fr["index"] == index:
                        return fr
        return None

    def _derive_palette(self, eid, placement):
        """Map tile color-indices -> real RGB using the cut frame + placement."""
        if not placement:
            return None
        key = (eid, placement.get("frameName"), placement.get("frameIndex"))
        if key in self._pal_cache:
            return self._pal_cache[key]
        box = self._frame_box(placement.get("frameName"), placement.get("frameIndex"))
        if not box:
            return None
        path = _find_cut_file(placement["frameName"] + ".png")
        if not path:
            return None
        img = QImage(path)
        if img.isNull():
            return None
        base = self.entries[eid][1]
        cols = placement.get("cols", 1)
        from collections import Counter
        votes = {v: Counter() for v in range(8)}
        for pl in placement.get("placement", []):
            off = base + pl["tile"] * 24
            if not _valid_tile(off):
                continue
            px = decode_3bpp(self.w.project.fixed("battle_graphic", off))
            ri, ci = divmod(pl["cell"], cols)
            for y in range(8):
                for x in range(8):
                    v = int(px[y, x])
                    if v == 0:
                        continue
                    fx = box["x"] + ci*8 + x; fy = box["y"] + ri*8 + y
                    if not (0 <= fx < img.width() and 0 <= fy < img.height()):
                        continue
                    col = img.pixelColor(fx, fy)
                    if col.alpha() == 0:
                        continue
                    votes[v][(col.red(), col.green(), col.blue())] += 1
        pal = [(0, 0, 0)] * 8
        for v in range(1, 8):
            if votes[v]:
                pal[v] = votes[v].most_common(1)[0][0]
        self._pal_cache[key] = pal
        return pal

    def _palette_colors(self):
        idx = self.palette.currentData()
        if idx == -1:  # auto: derive from cut art for the current placement
            eid = self.enemy.currentData()
            plist = self._placements_for(eid)
            fi = self.frame.currentIndex()
            p = plist[fi] if 0 <= fi < len(plist) else None
            if p and p.get("score", 0) >= COMPOSED_MIN_SCORE:
                pal = self._derive_palette(eid, p)
                if pal:
                    return pal
            return self._obj_palette(1)
        return self._obj_palette(idx)

    def choose_color(self, color):
        self.color = color
        for i, b in enumerate(self.swatches): b.setChecked(i == color)
        self.color_label.setText("transparent / erase" if color == 0 else f"color {color}")

    def _style_swatches(self):
        for i, b in enumerate(self.swatches):
            c = self.colors[i]; fg = "#111" if sum(c) > 380 else "#fff"
            bg = "#4e5661" if i == 0 else "#%02x%02x%02x" % c
            b.setStyleSheet(f"QPushButton {{ background: {bg}; color: {fg}; }} QPushButton:checked {{ border: 3px solid #ffc96b; }}")

    # -- views --------------------------------------------------------------
    def reload(self, *_):
        if self.loading: return
        self.loading = True
        try:
            self.canvas.cancel()
            # Clear any stale selection so switching enemies can't edit the
            # previous monster's tile.
            self._clear_selection()
            self.colors = self._palette_colors(); self._style_swatches(); self.choose_color(self.color)
            eid = self.enemy.currentData()
            base = self.entries[eid][1]
            use_composed = self.rb_composed.isChecked()
            plist = self._placements_for(eid)
            fi = self.frame.currentIndex()
            p = plist[fi] if (0 <= fi < len(plist)) else None
            if use_composed and p and p.get("placement"):
                self._show_composed(base, p)
            else:
                self._show_tiles(base)
            self._auto_select()
        finally:
            self.loading = False

    def _clear_selection(self):
        self.resource = None
        self._sel_pal = None
        self.pixels = np.zeros((8, 8), dtype=np.uint8)
        for b in self.edit_buttons:
            b.setEnabled(False)
        self.canvas.update()

    def _auto_select(self):
        """Select the first tile of the current view so the canvas isn't empty."""
        if self.rb_composed.isChecked():
            if self._composed:
                cell = min(self._composed)
                off, pal = self._composed[cell]
                self.select_tile(off, pal)
        elif self.tiles.count():
            self.tiles.setCurrentItem(self.tiles.item(0))

    def _show_tiles(self, base):
        self.view_stack.setCurrentIndex(self.tiles_idx)
        self.tiles.blockSignals(True); self.tiles.clear()
        for off in self._offsets(base):
            it = QListWidgetItem(self._tile_icon(off), f"${off & 0xffff:04X}")
            it.setData(Qt.ItemDataRole.UserRole, off); self.tiles.addItem(it)
        self.tiles.blockSignals(False)
        if self.tiles.count(): self.tiles.setCurrentItem(self.tiles.item(0))
        else: self._select_from_list()
        nm = self.names.get(self.enemy.currentData()) or f"Enemy {self.enemy.currentData():02X}"
        self.info.setText(f"Tiles view · {nm} · {self.tiles.count()} tiles.")

    def _cut_image(self, name, index):
        """Load the cut frame sub-image (QImage) + its box, cached."""
        key = (name, index)
        if key in getattr(self, "_cut_cache", {}):
            return self._cut_cache[key]
        box = self._frame_box(name, index)
        if not box:
            return None
        path = _find_cut_file(name + ".png")
        if not path:
            return None
        full = QImage(path)
        if full.isNull():
            return None
        sub = full.copy(box["x"], box["y"], box["width"], box["height"])
        self._cut_cache = getattr(self, "_cut_cache", {})
        self._cut_cache[key] = sub
        return sub

    def _cell_votes(self, sub, off, ri, ci, ns=None):
        """Per-cell index->colour votes, sampled from the ORIGINAL (base-ROM)
        tile against the cut image (stable across edits/imports). `ns` is a
        stable cache namespace (frameName, frameIndex) — never id(sub), which
        can be reused after GC and cross-contaminate palettes between enemies."""
        from collections import Counter
        cache = getattr(self, "_cellvotes_cache", None)
        if cache is None:
            cache = self._cellvotes_cache = {}
        key = (ns, off, ri, ci)
        if key in cache:
            return cache[key]
        data = self.w.project.base_rom.data
        px = decode_3bpp(data[off:off+24])
        votes = {}
        for y in range(8):
            for x in range(8):
                v = int(px[y, x])
                if not v:
                    continue
                fx, fy = ci*8+x, ri*8+y
                if not (0 <= fx < sub.width() and 0 <= fy < sub.height()):
                    continue
                col = sub.pixelColor(fx, fy)
                if col.alpha() == 0:
                    continue
                votes.setdefault(v, Counter())[(col.red(), col.green(), col.blue())] += 1
        cache[key] = votes
        return votes

    @staticmethod
    def _global_palette(all_votes):
        """index -> most common colour across all cells (the frame's palette).
        Returns a dict of only the indices that actually appear somewhere."""
        from collections import Counter
        merged = {}
        for votes in all_votes:
            for v, cnt in votes.items():
                merged.setdefault(v, Counter()).update(cnt)
        return {v: cnt.most_common(1)[0][0] for v, cnt in merged.items()}

    @staticmethod
    def _compose_palette(votes, global_map):
        """Cell palette = its own votes, else the frame-global colour for that
        index, else a distinct sentinel. Tracks assigned indices explicitly so a
        legitimate black (0,0,0) is never mistaken for an unassigned slot."""
        pal = [(0, 0, 0)] * 8
        assigned = [False] * 8
        for v in range(1, 8):
            if votes.get(v):
                pal[v] = votes[v].most_common(1)[0][0]; assigned[v] = True
            elif v in global_map:
                pal[v] = global_map[v]; assigned[v] = True
        used = {pal[v] for v in range(1, 8) if assigned[v]}
        sentinels = [(255, 0, 255), (0, 255, 255), (255, 255, 0), (255, 128, 0),
                     (0, 128, 255), (128, 0, 255), (0, 255, 128)]
        si = 0
        for v in range(1, 8):
            if not assigned[v]:
                while si < len(sentinels) and sentinels[si] in used:
                    si += 1
                pal[v] = sentinels[si] if si < len(sentinels) else (0, 0, v)
                used.add(pal[v])
        return pal

    def _composed_layout(self, base, p):
        """Return (cells, cols, rows) where cells[cell] = (offset, palette)."""
        cols = p.get("cols", 1)
        sub = self._cut_image(p.get("frameName"), p.get("frameIndex", 0))
        ns = (p.get("frameName"), p.get("frameIndex", 0))
        raw = []
        for pl in p.get("placement", []):
            off = base + pl["tile"]*24
            if not _valid_tile(off):
                continue
            ri, ci = divmod(pl["cell"], cols)
            votes = self._cell_votes(sub, off, ri, ci, ns) if sub is not None else {}
            raw.append((pl["cell"], off, votes))
        global_pal = self._global_palette([r[2] for r in raw]) if sub is not None else self.colors
        cells = {}
        for cell, off, votes in raw:
            pal = self._compose_palette(votes, global_pal) if sub is not None else self.colors
            cells[cell] = (off, pal)
        rows = max(((c // cols) for c in cells), default=0) + 1
        return cells, cols, rows

    def _composed_rgba(self, cells, cols, rows):
        rgba = np.zeros((rows*8, cols*8, 4), np.uint8)
        for cell, (off, pal) in cells.items():
            ri, ci = divmod(cell, cols); px = decode_3bpp(self.w.project.fixed("battle_graphic", off))
            for y in range(8):
                for x in range(8):
                    v = int(px[y, x])
                    if v: rgba[ri*8+y, ci*8+x] = (*pal[v], 255)
        return rgba

    def _current_placement(self):
        eid = self.enemy.currentData()
        plist = self._placements_for(eid)
        fi = self.frame.currentIndex()
        return plist[fi] if 0 <= fi < len(plist) else None

    def _show_composed(self, base, p):
        self.view_stack.setCurrentIndex(self.comp_idx)
        cells, cols, rows = self._composed_layout(base, p)
        self._composed = cells            # cell -> (offset, palette)
        self._composed_cols = cols
        rgba = self._composed_rgba(cells, cols, rows)
        self._comp_rgba = rgba
        self._comp_cols, self._comp_rows = cols, rows
        self.comp.set_rgba(rgba)
        nm = self.names.get(self.enemy.currentData()) or f"Enemy {self.enemy.currentData():02X}"
        self.info.setText(f"Composed view · {nm} · {p.get('frameName','frame')}#{p.get('frameIndex',0)} (score {p.get('score','manual')}) · click a region to edit that tile (its own palette is used).")

    def _live_update(self, draft):
        """While painting, patch the edited tile's region(s) into the composed
        image so the large view updates live (before the stroke is committed)."""
        if not self.rb_composed.isChecked() or self.resource is None:
            return
        rgba = getattr(self, "_comp_rgba", None)
        if rgba is None:
            return
        cols = self._comp_cols
        updated = False
        for cell, (off, pal) in self._composed.items():
            if off != self.resource:
                continue
            ri, ci = divmod(cell, cols)
            for y in range(8):
                for x in range(8):
                    v = int(draft[y, x])
                    if v:
                        rgba[ri*8+y, ci*8+x] = (*pal[v], 255)
                    else:
                        rgba[ri*8+y, ci*8+x] = (0, 0, 0, 0)
            updated = True
        if updated:
            self.comp.set_rgba(rgba.copy())

    def composed_clicked(self, px, py):
        if not self._composed: return
        cols = self._composed_cols
        ci = px//8; ri = py//8; cell = ri*cols + ci
        entry = self._composed.get(cell)
        if entry:
            off, pal = entry
            self.select_tile(off, pal)

    def _tile_rgba(self, resource):
        pixels = decode_3bpp(self.w.project.fixed("battle_graphic", resource))
        rgba = np.zeros((8, 8, 4), np.uint8)
        for v in range(8):
            m = pixels == v
            if m.any(): rgba[m, :3] = self.colors[v]; rgba[m, 3] = 0 if v == 0 else 255
        return rgba

    def _tile_icon(self, resource):
        return QIcon(QPixmap.fromImage(qimage(self._tile_rgba(resource))).scaled(
            THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))

    def _select_from_list(self, *_):
        items = self.tiles.selectedItems()
        if items: self.select_tile(items[0].data(Qt.ItemDataRole.UserRole))
        else:
            self.resource = None; self.info.setText("No editable tiles for this enemy.")
            for b in self.edit_buttons: b.setEnabled(False)

    def select_tile(self, resource, pal=None):
        self.resource = resource
        # Use this tile's own palette for the edit canvas + swatches when known
        # (tiles can have different palettes, e.g. dark-king's face is green).
        if pal is not None:
            self._sel_pal = list(pal)
            self.colors = list(pal)
            self._style_swatches(); self.choose_color(self.color)
        self.pixels = decode_3bpp(self.w.project.fixed("battle_graphic", resource))
        for b in self.edit_buttons: b.setEnabled(True)
        self.canvas.update()

    # -- editing ------------------------------------------------------------
    def commit(self, pixels, label):
        if self.resource is None: return
        raw = encode_3bpp(pixels); old = self.w.project.fixed("battle_graphic", self.resource)
        changes = {("battle_graphic", self.resource, i): (a, b) for i, (a, b) in enumerate(zip(old, raw)) if a != b}
        if not changes: return
        self.w.commit_changes(changes, label)
        self.feedback.setText(f"{len(changes)} byte change(s) on tile ${self.resource & 0xffff:04X}.")

    def refresh(self):
        if self.loading or not self.isVisible(): return
        self.colors = self._palette_colors(); self._style_swatches()
        # keep the clicked tile's own palette for the swatches/canvas
        if getattr(self, "_sel_pal", None) and self.rb_composed.isChecked():
            self.colors = list(self._sel_pal); self._style_swatches()
        if self.rb_composed.isChecked():
            # Rebuild the composed image directly (reload() would early-return
            # because refresh() is mid-flight, which is what caused edits to
            # appear reverted in composed mode).
            eid = self.enemy.currentData(); base = self.entries[eid][1]
            plist = self._placements_for(eid); fi = self.frame.currentIndex()
            p = plist[fi] if 0 <= fi < len(plist) else None
            if p and p.get("placement"):
                self._show_composed(base, p)
        else:
            for i in range(self.tiles.count()):
                it = self.tiles.item(i); it.setIcon(self._tile_icon(it.data(Qt.ItemDataRole.UserRole)))
        # Keep the pixel canvas in sync with the committed edit in BOTH modes.
        if self.resource is not None:
            self.pixels = decode_3bpp(self.w.project.fixed("battle_graphic", self.resource))
            self.canvas.update()

    # -- PNG export / import -----------------------------------------------
    def _current_layout(self):
        """(cells, cols, rows) for the current view; cells[cell]=(offset,palette)."""
        eid = self.enemy.currentData(); base = self.entries[eid][1]
        p = self._current_placement()
        if self.rb_composed.isChecked() and p and p.get("placement"):
            return self._composed_layout(base, p)
        offs = self._offsets(base)
        cols = 8
        cells = {i: (off, self.colors) for i, off in enumerate(offs)}
        rows = (len(offs) + cols - 1) // cols
        return cells, cols, rows

    @staticmethod
    def _qimage_to_rgba(img):
        from PySide6.QtGui import QImage
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        bpl = img.bytesPerLine()
        buf = bytes(img.constBits())[: h * bpl]
        arr = np.frombuffer(buf, np.uint8).reshape((h, bpl))[:, :w*4].reshape((h, w, 4)).copy()
        return arr

    def export_png(self):
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtGui import QImage
        cells, cols, rows = self._current_layout()
        if not cells:
            self.feedback.setText("Nothing to export."); return
        rgba = self._composed_rgba(cells, cols, rows)
        nm = self.names.get(self.enemy.currentData()) or f"enemy_{self.enemy.currentData():02X}"
        p = self._current_placement()
        suffix = f"_{p.get('frameIndex',0)}" if (p and self.rb_composed.isChecked()) else ""
        default = f"{nm}{suffix}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export composed sprite to PNG", default, "PNG (*.png)")
        if not path:
            return
        qimg = self._rgba_to_indexed_qimage(rgba)
        if qimg.save(path, "PNG"):
            self.feedback.setText(f"Exported {cols*8}×{rows*8} indexed PNG: {path}")
        else:
            self.feedback.setText(f"Export failed to save: {path}")

    @staticmethod
    def _rgba_to_indexed_qimage(rgba):
        """Build an indexed (colour-type 3) PNG image: index 0 = transparent."""
        from PySide6.QtGui import QImage, qRgba
        h, w = rgba.shape[:2]
        palette = [qRgba(0, 0, 0, 0)]          # index 0 = transparent
        index_of = {(0, 0, 0, 0): 0}
        idx = np.zeros((h, w), np.uint8)
        for y in range(h):
            for x in range(w):
                key = (int(rgba[y, x, 0]), int(rgba[y, x, 1]), int(rgba[y, x, 2]), int(rgba[y, x, 3]))
                if key not in index_of:
                    if len(palette) >= 256:
                        break
                    index_of[key] = len(palette); palette.append(qRgba(*key))
                idx[y, x] = index_of.get(key, 0)
        if len(palette) > 256 or any(idx[y, x] == 0 and rgba[y, x, 3] != 0 for y in range(h) for x in range(w)):
            # too many colours or a colour couldn't be indexed: fall back to RGBA
            return QImage(rgba.data, w, h, w*4, QImage.Format.Format_RGBA8888).copy()
        img = QImage(w, h, QImage.Format.Format_Indexed8)
        img.setColorTable(palette)
        for y in range(h):
            for x in range(w):
                img.setPixel(x, y, int(idx[y, x]))
        return img

    def import_png(self):
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtGui import QImage
        cells, cols, rows = self._current_layout()
        if not cells:
            self.feedback.setText("Nothing to import into."); return
        path, _ = QFileDialog.getOpenFileName(self, "Import composed sprite from PNG", "", "PNG (*.png)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self.feedback.setText("Could not read PNG."); return
        arr = self._qimage_to_rgba(img.convertToFormat(QImage.Format.Format_RGBA8888))
        ih, iw = arr.shape[:2]
        changes = {}
        # Group cells by tile offset (a tile may back several cells via reuse).
        by_off = {}
        for cell, (off, pal) in cells.items():
            by_off.setdefault(off, []).append((cell, pal))

        def region_native(off, cell, pal):
            ri, ci = divmod(cell, cols)
            cur = decode_3bpp(self.w.project.fixed("battle_graphic", off))  # current tile (fallback)
            native = np.zeros((8, 8), np.uint8)
            for y in range(8):
                for x in range(8):
                    sy, sx = ri*8+y, ci*8+x
                    a = int(arr[sy, sx, 3]) if (0 <= sy < ih and 0 <= sx < iw) else 0
                    if a == 0:
                        v = 0
                    else:
                        r, g, b = (int(arr[sy, sx, 0]), int(arr[sy, sx, 1]), int(arr[sy, sx, 2]))
                        v = min(range(1, 8), key=lambda q: (pal[q][0]-r)**2+(pal[q][1]-g)**2+(pal[q][2]-b)**2)
                        # if the edited colour isn't representable by this tile's
                        # palette, keep the current index instead of snapping wrong.
                        if (pal[v][0]-r)**2+(pal[v][1]-g)**2+(pal[v][2]-b)**2 > 48*48*3:
                            v = int(cur[y, x])
                    native[y, x] = v
            return native

        for off, insts in by_off.items():
            original = decode_3bpp(self.w.project.base_rom.data[off:off+24])
            # choose the instance whose region differs most from the original tile
            best_native = None; best_diff = -1
            for cell, pal in insts:
                native = region_native(off, cell, pal)
                d = int((native != original).sum())
                if d > best_diff:
                    best_diff = d; best_native = native
            new = encode_3bpp(best_native)
            old = self.w.project.fixed("battle_graphic", off)
            for i, (a, bv) in enumerate(zip(old, new)):
                if a != bv:
                    changes[("battle_graphic", off, i)] = (a, bv)
        if changes:
            self.w.commit_changes(changes, "Import composed sprite from PNG")
            self.feedback.setText(f"Imported PNG: {len(changes)} byte change(s) across {len(cells)} tiles.")
            self.reload()
        else:
            self.feedback.setText("Imported PNG: no changes (pixels matched existing tiles).")

    def copy(self): self.clipboard = self.pixels.copy(); self.feedback.setText("Copied tile color indices.")
    def paste(self):
        if self.clipboard is not None: self.commit(self.clipboard.copy(), "Paste battle graphic pixels")
        else: self.feedback.setText("Copy a tile first.")
    def restore(self):
        if self.resource is None: return
        orig = decode_3bpp(bytes(self.w.project.original(("battle_graphic", self.resource, i)) for i in range(24)))
        self.commit(orig, "Restore battle graphic pixels")
    def undo(self):
        if self.canvas.draft is not None: self.canvas.cancel()
        else: self.w.stack.undo()
    def closeEvent(self, event): self.canvas.cancel(); event.accept()


def open_battle_enemies(w):
    w.end_stroke()
    if hasattr(w, "play"): w.play.setChecked(False)
    if not hasattr(w, "battle_window"):
        w.battle_window = BattleEnemyWindow(w)
    e = w.battle_window
    # Re-read placements + cut data so web-tool saves (and re-solves) show up
    # even if the window was opened before those files were written.
    e.placements = load_placements()
    e.frames_json = _load_frames_json(str(w.project.base_rom.path))
    e._pal_cache = {}; e._cut_cache = {}; e._cellvotes_cache = {}
    # Rebuild the enemy combo (placement availability may have changed).
    cur = e.enemy.currentData()
    e.enemy.blockSignals(True); e.enemy.clear()
    for i, off, fl in e.entries:
        n = e._tile_count(off)
        if n == 0:
            continue
        nm = e.names.get(i) or f"Enemy {i:02X}"
        e.enemy.addItem(f"{nm}  (id {i:02X}, {n} tiles)", i)
    e.enemy.blockSignals(False)
    idx = next((k for k in range(e.enemy.count()) if e.enemy.itemData(k) == cur), 0)
    e.enemy.setCurrentIndex(idx)
    e.colors = e._palette_colors(); e._style_swatches()
    e._populate_frames(); e.reload(); e.show(); e.raise_(); e.activateWindow()
