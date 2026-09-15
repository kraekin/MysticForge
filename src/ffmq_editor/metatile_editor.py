"""Shared metatile composition editing; all controls commit undoable project edits."""
import numpy as np
from PySide6.QtCore import Qt,QSize,Signal
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


class ComponentButton(QPushButton):
    doubleClicked=Signal()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.doubleClicked.emit();event.accept()
        else:super().mouseDoubleClickEvent(event)

class MetatileWindow(QMainWindow):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.loading=False;self.tile=0;self.quadrant=0;self.clipboard=None
        self.setWindowTitle('MysticForge — Metatile editor');self.resize(1120,800)
        root=QWidget();self.setCentralWidget(root);box=QVBoxLayout(root)
        row=QHBoxLayout();row.addWidget(QLabel('Preview configuration'));self.context=QComboBox();row.addWidget(self.context,1)
        from .workspace_ui import version_name
        for a in w.rom.areas:self.context.addItem(f'{a.name} / {version_name(w,a.id)}',a.id)
        for label,fn in [('Undo',w.stack.undo),('Redo',w.stack.redo)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        box.addLayout(row);self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        from .expanded_content_editor import private_metatiles
        self.private_button=QPushButton('Make this configuration’s metatile set independent…');self.private_button.clicked.connect(lambda:private_metatiles(w,self.area_id));box.addWidget(self.private_button)
        split=QSplitter();box.addWidget(split,1)
        self.metatiles=self.tile_list(48,64);split.addWidget(self.metatiles)
        middle=QWidget();mid=QVBoxLayout(middle);self.heading=QLabel();self.heading.setObjectName('heading');mid.addWidget(self.heading)
        self.preview=QLabel();self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);mid.addWidget(self.preview)
        group=QGroupBox('Select a component, then choose a graphic on the right');grid=QGridLayout(group);self.components=[];self.flips=[]
        for q,label in enumerate(('Top left','Top right','Bottom left','Bottom right')):
            container=QWidget();column=QVBoxLayout(container);button=ComponentButton(label);button.doubleClicked.connect(lambda q=q:self.edit_component_pixels(q));button.setToolTip("Double-click to edit this component’s source pixels");button.setCheckable(True);button.setStyleSheet("QPushButton:checked { border: 2px solid #8fe8ff; background: #284d60; }");button.setIconSize(QSize(48,48));button.clicked.connect(lambda _,q=q:self.select_quadrant(q));column.addWidget(button)
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
        self.graphics=self.tile_list(32,49);rb.addWidget(self.graphics);pixel_button=QPushButton('Edit selected graphic pixels…');pixel_button.clicked.connect(self.edit_pixels);rb.addWidget(pixel_button);split.addWidget(right);split.setSizes([220,620,280])
        self.context.currentIndexChanged.connect(self.refresh);self.metatiles.currentRowChanged.connect(self.select_tile);self.graphics.itemClicked.connect(self.assign);self.graphics.itemActivated.connect(self.assign)
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
        scrolls=[(view,view.horizontalScrollBar().value(),view.verticalScrollBar().value()) for view in (self.metatiles,self.graphics,self.references)]
        try:
            w=self.w;area=w.rom.areas[self.area_id];attr=w.rom.attributes[area.attributes_id];self.tileset=w.project.tileset(self.area_id)
            self.private_button.setEnabled(self.tileset<16)
            self.private_button.setText('Metatile set is independent' if self.tileset>=16 else 'Make this configuration’s metatile set independent…')
            self.pixels,self.defaults=w.renderer.project_graphics(w.project,area.attributes_id)
            state=w.project.state(self.area_id);self.colors=np.array([color_rgb(v) for v in w.project.palette(state.palette)],dtype=np.uint8).reshape(8,8,3)
            self.info.setText(f'Shared metatile set ${self.tileset:02X} · palette ${state.palette:02X}. Preview shows stored definitions before story remaps, with static source graphics. Different configurations can load different artwork for the same component IDs.')
            # Keep item identities stable: refresh can run inside mousePressEvent.
            if not self.metatiles.count():
                for i in range(128):self.metatiles.addItem(QListWidgetItem(f'{i:02X}'))
            for i in range(128):self.metatiles.item(i).setIcon(QIcon(self.pixmap(self.image(i),48)))
            self.metatiles.setCurrentRow(self.tile)
            if not self.graphics.count():
                for i in range(256):
                    item=QListWidgetItem(f'{i:02X}');item.setData(Qt.ItemDataRole.UserRole,i);self.graphics.addItem(item)
            _,bits=composition(w.project,self.tileset,self.tile)
            for i in range(256):
                pal=(bits>>4)&7 if bits&128 else int(self.defaults[i]);self.graphics.item(i).setIcon(QIcon(self.pixmap(self.graphic_image(i,pal),32)))
            self.references.clear()
            from .workspace_ui import version_name
            self.context.blockSignals(True)
            try:
                for a in w.rom.areas:self.context.setItemText(a.id,f'{a.name} / {version_name(w,a.id)}')
            finally:self.context.blockSignals(False)
            for a in w.rom.areas:
                if w.project.tileset(a.id)==self.tileset:
                    item=QListWidgetItem(f'{a.name} / {version_name(w,a.id)}');item.setData(Qt.ItemDataRole.UserRole,a.id);self.references.addItem(item)
            self.load_controls()
        finally:
            for view,x,y in scrolls:
                view.doItemsLayout();view.horizontalScrollBar().setValue(x);view.verticalScrollBar().setValue(y)
            self.loading=False
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
    def edit_component_pixels(self,q):
        from .pixel_editor import open_pixels
        graphics,_=composition(self.w.project,self.tileset,self.tile)
        open_pixels(self.w,self.area_id,graphics[q],self.palette.currentData())
    def edit_pixels(self):
        from .pixel_editor import open_pixels
        item=self.graphics.currentItem()
        if item is not None:open_pixels(self.w,self.area_id,item.data(Qt.ItemDataRole.UserRole),self.palette.currentData())
    def visit(self,item):self.w.select_area(item.data(Qt.ItemDataRole.UserRole));self.w.raise_()


def open_metatiles(w):
    w.end_stroke();w.play.setChecked(False)
    if not hasattr(w,'metatile_window'):w.metatile_window=MetatileWindow(w)
    else:
        w.metatile_window.tile=w.brush;w.metatile_window.context.setCurrentIndex(w.area_id);w.metatile_window.refresh()
    w.metatile_window.show();w.metatile_window.raise_();w.metatile_window.activateWindow()
    w.metatile_window.metatiles.doItemsLayout()
    w.metatile_window.metatiles.scrollToItem(w.metatile_window.metatiles.item(w.metatile_window.tile))
