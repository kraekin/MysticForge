"""Shared metatile composition editing; all controls commit undoable project edits."""
import numpy as np
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QComboBox,QCheckBox,QListWidget,QListWidgetItem,QSplitter,QGroupBox)
from .render import color_rgb


def composition(project,tileset,tile):
    return bytes(project.get(('metatile_graphics',tileset,tile*4+q)) for q in range(4)),project.get(('metatile_attributes',tileset,tile))


def composition_changes(project,tileset,tile,graphics,bits):
    if len(graphics)!=4 or any(type(v) is not int or not 0<=v<=255 for v in graphics) or type(bits) is not int or not 0<=bits<=255:
        raise ValueError('Invalid metatile composition')
    values={('metatile_graphics',tileset,tile*4+q):v for q,v in enumerate(graphics)}
    values[('metatile_attributes',tileset,tile)]=bits
    return {k:(project.get(k),v) for k,v in values.items() if project.get(k)!=v}


class MetatileWindow(QMainWindow):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.loading=False;self.tile=0;self.quadrant=0;self.clipboard=None
        self.setWindowTitle('Metatile editor');self.resize(1120,800)
        root=QWidget();self.setCentralWidget(root);box=QVBoxLayout(root)
        row=QHBoxLayout();row.addWidget(QLabel('Preview configuration'));self.context=QComboBox();row.addWidget(self.context,1)
        from .workspace_ui import version_name
        for a in w.rom.areas:self.context.addItem(f'{a.name} / {version_name(w,a.id)}',a.id)
        for label,fn in [('Undo',w.stack.undo),('Redo',w.stack.redo)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        box.addLayout(row);self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        split=QSplitter();box.addWidget(split,1)
        self.metatiles=self.tile_list(48,64);split.addWidget(self.metatiles)
        middle=QWidget();mid=QVBoxLayout(middle);self.heading=QLabel();self.heading.setObjectName('heading');mid.addWidget(self.heading)
        self.preview=QLabel();self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);mid.addWidget(self.preview)
        group=QGroupBox('Select a component, then choose a graphic on the right');grid=QGridLayout(group);self.components=[];self.flips=[]
        for q,label in enumerate(('Top left','Top right','Bottom left','Bottom right')):
            container=QWidget();column=QVBoxLayout(container);button=QPushButton(label);button.setCheckable(True);button.setStyleSheet("QPushButton:checked { border: 2px solid #8fe8ff; background: #284d60; }");button.setIconSize(QSize(48,48));button.clicked.connect(lambda _,q=q:self.select_quadrant(q));column.addWidget(button)
            flip=QCheckBox('Flip horizontally');flip.toggled.connect(lambda checked,q=q:self.edit_flip(q,checked));column.addWidget(flip);grid.addWidget(container,q//2,q%2);self.components.append(button);self.flips.append(flip)
        mid.addWidget(group)
        self.palette=QComboBox();self.palette.addItem('Use each graphic’s default palette',-1)
        for i in range(8):self.palette.addItem(f'Override all components: palette {i}',i)
        self.palette.currentIndexChanged.connect(self.edit_palette);mid.addWidget(self.palette)
        row=QHBoxLayout()
        for label,fn in [('Copy appearance',self.copy),('Paste appearance',self.paste),('Restore original appearance',self.restore)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        mid.addLayout(row)
        note=QLabel('Edits apply immediately and can be undone. Appearance edits preserve collision and entrance properties. Vertical flip is not stored by this format; Upper map pass is edited on map cells.');note.setWordWrap(True);mid.addWidget(note)
        mid.addWidget(QLabel('Configurations sharing this metatile set (double-click to view map)'))
        self.references=QListWidget();self.references.itemDoubleClicked.connect(self.visit);mid.addWidget(self.references,1)
        self.feedback=QLabel();self.feedback.setWordWrap(True);mid.addWidget(self.feedback);split.addWidget(middle)
        right=QWidget();rb=QVBoxLayout(right);rb.addWidget(QLabel('8×8 source graphics · select to assign'))
        self.graphics=self.tile_list(32,49);rb.addWidget(self.graphics);split.addWidget(right);split.setSizes([220,620,280])
        self.context.currentIndexChanged.connect(self.refresh);self.metatiles.currentRowChanged.connect(self.select_tile);self.graphics.itemClicked.connect(self.assign)
        self.context.setCurrentIndex(w.area_id);self.tile=w.brush;self.refresh()
    @staticmethod
    def tile_list(icon,cell):
        result=QListWidget();result.setViewMode(QListWidget.ViewMode.IconMode);result.setIconSize(QSize(icon,icon));result.setGridSize(QSize(cell,cell+19));result.setResizeMode(QListWidget.ResizeMode.Adjust);result.setMovement(QListWidget.Movement.Static);return result
    @property
    def area_id(self):return self.context.currentData()
    def pixmap(self,rgba,scale):
        from .app import qimage
        return QPixmap.fromImage(qimage(rgba)).scaled(scale,scale,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
    def graphic_image(self,tile,palette,flip=False):
        pixels=self.pixels[tile][:,::-1] if flip else self.pixels[tile]
        rgba=np.zeros((8,8,4),dtype=np.uint8);rgba[:,:,:3]=self.colors[palette][pixels];rgba[:,:,3]=np.where(pixels==0,0,255);return rgba
    def image(self,tile):
        graphics,bits=composition(self.w.project,self.tileset,tile);result=np.zeros((16,16,4),dtype=np.uint8)
        for q,t in enumerate(graphics):
            palette=(bits>>4)&7 if bits&128 else int(self.defaults[t]);y,x=(q//2)*8,(q%2)*8
            result[y:y+8,x:x+8]=self.graphic_image(t,palette,bool(bits&(1<<q)))
        return result
    def refresh(self,*_):
        if self.loading:return
        self.loading=True
        try:
            w=self.w;area=w.rom.areas[self.area_id];attr=w.rom.attributes[area.attributes_id];self.tileset=attr.tileset
            self.pixels,self.defaults=w.renderer.graphics(area.attributes_id)
            state=w.project.state(self.area_id);self.colors=np.array([color_rgb(v) for v in w.project.palette(state.palette)],dtype=np.uint8).reshape(8,8,3)
            self.info.setText(f'Shared metatile set ${self.tileset:02X} · palette ${state.palette:02X}. Preview shows stored definitions before story remaps, with static source graphics. Different configurations can load different artwork for the same component IDs.')
            self.metatiles.clear()
            for i in range(128):self.metatiles.addItem(QListWidgetItem(QIcon(self.pixmap(self.image(i),48)),f'{i:02X}'))
            self.metatiles.setCurrentRow(self.tile)
            self.graphics.clear();_,bits=composition(w.project,self.tileset,self.tile)
            for i in range(256):
                pal=(bits>>4)&7 if bits&128 else int(self.defaults[i]);item=QListWidgetItem(QIcon(self.pixmap(self.graphic_image(i,pal),32)),f'{i:02X}');item.setData(Qt.ItemDataRole.UserRole,i);self.graphics.addItem(item)
            self.references.clear()
            from .workspace_ui import version_name
            for a in w.rom.areas:
                if w.rom.attributes[a.attributes_id].tileset==self.tileset:
                    item=QListWidgetItem(f'{a.name} / {version_name(w,a.id)}');item.setData(Qt.ItemDataRole.UserRole,a.id);self.references.addItem(item)
            self.load_controls()
        finally:self.loading=False
    def load_controls(self):
        graphics,bits=composition(self.w.project,self.tileset,self.tile)
        self.heading.setText(f'Metatile ${self.tile:02X}');self.preview.setPixmap(self.pixmap(self.image(self.tile),160))
        for q,t in enumerate(graphics):
            self.components[q].setChecked(q==self.quadrant);self.components[q].setText(f'{("Top left","Top right","Bottom left","Bottom right")[q]} · ${t:02X}')
            pal=(bits>>4)&7 if bits&128 else int(self.defaults[t]);self.components[q].setIcon(QIcon(self.pixmap(self.graphic_image(t,pal,bool(bits&(1<<q))),48)));self.flips[q].setChecked(bool(bits&(1<<q)))
        self.palette.setCurrentIndex(((bits>>4)&7)+1 if bits&128 else 0);self.graphics.setCurrentRow(graphics[self.quadrant])
    def select_tile(self,tile):
        if not self.loading and tile>=0:self.tile=tile;self.refresh()
    def select_quadrant(self,q):
        self.quadrant=q;self.loading=True;self.load_controls();self.loading=False
    def commit(self,graphics,bits,label):
        diff=composition_changes(self.w.project,self.tileset,self.tile,list(graphics),bits)
        self.w.commit_changes(diff,label);self.feedback.setText(f'{len(diff)} byte change(s). Shared by {self.references.count()} configurations.')
    def assign(self,item):
        graphics,bits=composition(self.w.project,self.tileset,self.tile);graphics=list(graphics);graphics[self.quadrant]=item.data(Qt.ItemDataRole.UserRole);self.commit(graphics,bits,'Change metatile component')
    def edit_flip(self,q,checked):
        if self.loading:return
        graphics,bits=composition(self.w.project,self.tileset,self.tile);self.commit(graphics,(bits&~(1<<q))|((1<<q) if checked else 0),'Flip metatile component')
    def edit_palette(self,*_):
        if self.loading:return
        graphics,bits=composition(self.w.project,self.tileset,self.tile);pal=self.palette.currentData();bits=(bits&127) if pal<0 else (bits&15)|128|(pal<<4);self.commit(graphics,bits,'Change metatile palette')
    def copy(self):
        self.clipboard=(*composition(self.w.project,self.tileset,self.tile),self.tileset);self.feedback.setText('Appearance copied. Gameplay properties are not included.')
    def paste(self):
        if self.clipboard is None:self.feedback.setText('Copy a metatile appearance first.');return
        graphics,bits,source=self.clipboard
        if source!=self.tileset:self.feedback.setText('Choose a metatile in the copied set; other sets can load unrelated graphics.');return
        self.commit(graphics,bits,'Paste metatile appearance')
    def restore(self):
        p=self.w.project;graphics=[p.original(('metatile_graphics',self.tileset,self.tile*4+q)) for q in range(4)];bits=p.original(('metatile_attributes',self.tileset,self.tile));self.commit(graphics,bits,'Restore metatile appearance')
    def visit(self,item):self.w.select_area(item.data(Qt.ItemDataRole.UserRole));self.w.raise_()


def open_metatiles(w):
    w.end_stroke();w.play.setChecked(False)
    if not hasattr(w,'metatile_window'):w.metatile_window=MetatileWindow(w)
    else:
        w.metatile_window.tile=w.brush;w.metatile_window.context.setCurrentIndex(w.area_id);w.metatile_window.refresh()
    w.metatile_window.show();w.metatile_window.raise_();w.metatile_window.activateWindow()
