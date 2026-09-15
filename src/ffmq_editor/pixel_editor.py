"""Undoable 8×8 terrain pixel editing. ROM animation programs remain unchanged."""
import numpy as np
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QPainter,QColor,QPen,QAction,QKeySequence
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QSpinBox,QTreeWidget,QTreeWidgetItem)
from .pixels import resource_for,pixel_changes,references,decode_3bpp
from .render import color_rgb

class PixelCanvas(QWidget):
    CELL=36
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.draft=None;self.last=None;self.setFixedSize(289,289);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    def paintEvent(self,event):
        p=QPainter(self);data=self.draft if self.draft is not None else self.editor.pixels
        for y in range(8):
            for x in range(8):
                v=int(data[y,x]);c=self.editor.colors[v] if v else ((78,86,97) if (x+y)%2 else (45,52,64))
                p.fillRect(x*36,y*36,36,36,QColor(*c))
        p.setPen(QPen(QColor('#18212c'),1))
        for i in range(9):p.drawLine(i*36,0,i*36,288);p.drawLine(0,i*36,288,i*36)
    def cell(self,event):
        x,y=int(event.position().x())//36,int(event.position().y())//36
        return (x,y) if 0<=x<8 and 0<=y<8 else None
    def mousePressEvent(self,event):
        point=self.cell(event)
        if point is None or self.editor.resource is None:return
        x,y=point;mode=self.editor.tool.currentText()
        if event.button()==Qt.MouseButton.RightButton or mode=='Pick color':self.editor.choose_color(int(self.editor.pixels[y,x]));return
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.setFocus();self.draft=self.editor.pixels.copy();self.last=point
        color=0 if mode=='Eraser' else self.editor.color
        if mode=='Fill':
            old=int(self.draft[y,x]);pending=[point];visited=set()
            while pending:
                x,y=pending.pop()
                if (x,y) in visited or not 0<=x<8 or not 0<=y<8 or self.draft[y,x]!=old:continue
                visited.add((x,y));self.draft[y,x]=color;pending.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
            self.finish('Fill graphic pixels');return
        self.draft[y,x]=color;self.update()
    def draw_to(self,point):
        if self.draft is None or point is None:return
        x,y=self.last;tx,ty=point;n=max(abs(tx-x),abs(ty-y),1);color=0 if self.editor.tool.currentText()=='Eraser' else self.editor.color
        for i in range(n+1):self.draft[round(y+(ty-y)*i/n),round(x+(tx-x)*i/n)]=color
        self.last=point;self.update()
    def mouseMoveEvent(self,event):self.draw_to(self.cell(event))
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.draft is not None:self.draw_to(self.cell(event));self.finish('Paint graphic pixels')
    def finish(self,label):
        data=self.draft;self.draft=None;self.last=None
        if data is not None:self.editor.commit(data,label)
        self.update()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.cancel()
        else:super().keyPressEvent(event)
    def cancel(self):self.draft=None;self.last=None;self.update()

class PixelWindow(QMainWindow):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.loading=False;self.resource=None;self.color=1;self.clipboard=None;self.pixels=np.zeros((8,8),dtype=np.uint8);self.colors=[(0,0,0)]*8
        self.setWindowTitle('MysticForge — Terrain pixel editor');self.resize(1000,710)
        root=QWidget();self.setCentralWidget(root);box=QVBoxLayout(root)
        top=QHBoxLayout();top.addWidget(QLabel('Preview map'));self.area=QComboBox()
        for a in w.rom.areas:self.area.addItem(f'{a.name} · area ${a.id:02X}',a.id)
        top.addWidget(self.area,1);top.addWidget(QLabel('Graphic slot'));self.slot=QSpinBox();self.slot.setRange(0,255);self.slot.setDisplayIntegerBase(16);self.slot.setPrefix('$');top.addWidget(self.slot);box.addLayout(top)
        self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        tools=QHBoxLayout();self.tool=QComboBox();self.tool.addItems(['Pencil','Eraser','Fill','Pick color']);tools.addWidget(self.tool)
        for label,fn in [('Undo',w.stack.undo),('Redo',w.stack.redo)]:
            b=QPushButton(label);b.clicked.connect(fn);tools.addWidget(b)
        tools.addStretch();box.addLayout(tools)
        middle=QHBoxLayout();self.canvas=PixelCanvas(self);middle.addWidget(self.canvas,0,Qt.AlignmentFlag.AlignTop)
        side=QVBoxLayout();self.palette=QComboBox();self.palette.addItem('Graphic default palette',-1)
        for i in range(8):self.palette.addItem(f'Preview palette {i}',i)
        side.addWidget(self.palette);self.swatches=[];colors=QHBoxLayout()
        for i in range(8):
            b=QPushButton(str(i));b.setCheckable(True);b.setMinimumSize(40,40);b.clicked.connect(lambda _,i=i:self.choose_color(i));colors.addWidget(b);self.swatches.append(b)
        side.addLayout(colors);self.color_label=QLabel();side.addWidget(self.color_label)
        note=QLabel('Color 0 is transparent (checkerboard). Right-click picks a color. Drag to paint; each stroke is one undo step. Escape cancels the current stroke.\n\nPalette selection changes this preview only; palette colors and assignments are edited in the existing palette/metatile controls.');note.setWordWrap(True);side.addWidget(note)
        self.edit_buttons=[]
        for label,fn in [('Copy pixels',self.copy),('Paste pixels',self.paste),('Flip horizontally',lambda:self.commit(self.pixels[:,::-1].copy(),'Flip graphic horizontally')),('Flip vertically',lambda:self.commit(self.pixels[::-1,:].copy(),'Flip graphic vertically')),('Restore original pixels',self.restore)]:
            b=QPushButton(label);b.clicked.connect(fn);side.addWidget(b);self.edit_buttons.append(b)
        middle.addLayout(side,1);box.addLayout(middle)
        self.animation_note=QLabel();self.animation_note.setWordWrap(True);box.addWidget(self.animation_note)
        box.addWidget(QLabel('Shared graphic uses · double-click to inspect that map'))
        self.uses=QTreeWidget();self.uses.setHeaderLabels(['Map / graphic slots','Metatile components / animation']);self.uses.itemDoubleClicked.connect(self.visit);box.addWidget(self.uses,1)
        self.feedback=QLabel('Pixel edits apply immediately to your project; export writes a ROM copy.');self.feedback.setWordWrap(True);box.addWidget(self.feedback)
        for text,key,fn in [('Undo',QKeySequence.StandardKey.Undo,self.undo),('Redo',QKeySequence.StandardKey.Redo,w.stack.redo)]:
            action=QAction(text,self);action.setShortcut(QKeySequence(key));action.triggered.connect(fn);self.addAction(action)
        self.area.currentIndexChanged.connect(self.refresh);self.slot.valueChanged.connect(self.refresh);self.palette.currentIndexChanged.connect(self.refresh)
    def undo(self):
        if self.canvas.draft is not None:self.canvas.cancel()
        else:self.w.stack.undo()
    def choose_color(self,color):
        self.color=color
        for i,b in enumerate(self.swatches):b.setChecked(i==color)
        self.color_label.setText('Selected: transparent / erase' if color==0 else f'Selected color {color}')
    def refresh(self,*_):
        if self.loading:return
        self.loading=True
        try:
            self.canvas.cancel();w=self.w;a=w.rom.areas[self.area.currentData()];slot=self.slot.value();self.resource=resource_for(w.rom,a.id,slot)
            _,defaults=w.renderer.graphics(a.attributes_id);pal=self.palette.currentData();pal=int(defaults[slot]) if pal<0 else pal
            state=w.project.state(a.id);self.colors=[color_rgb(v) for v in w.project.palette(state.palette)[pal*8:pal*8+8]]
            self.pixels=decode_3bpp(w.project.fixed('terrain_graphic',self.resource)) if self.resource is not None else np.zeros((8,8),dtype=np.uint8)
            self.info.setText(f'Graphic slot ${slot:02X} → shared library tile ${self.resource:03X} · 8 × 8 pixels · 24 bytes' if self.resource is not None else 'This slot is cleared by the game loader. It has no editable stored graphic.')
            self.canvas.setEnabled(self.resource is not None)
            for b in self.edit_buttons:b.setEnabled(self.resource is not None)
            for i,b in enumerate(self.swatches):
                c=self.colors[i];foreground='#111' if sum(c)>380 else '#fff';background='#4e5661' if i==0 else '#%02x%02x%02x'%c
                b.setStyleSheet(f'QPushButton {{ background: {background}; color: {foreground}; }} QPushButton:checked {{ border: 3px solid #ffc96b; }}');b.setToolTip('Transparent' if i==0 else f'Color index {i}')
            self.choose_color(self.color);self.uses.clear();animated=[]
            if self.resource is not None:
                for area_id,slots,uses,notes in references(w.project,self.resource,w.renderer.animation):
                    label=w.rom.areas[area_id].name+f' · ${area_id:02X} · slots '+', '.join(f'${s:02X}' for s in slots)
                    detail=', '.join(f'${t:02X}/{("TL","TR","BL","BR")[q]}' for t,q in uses) or 'Loaded; no direct metatile references'
                    if notes:detail+=' · '+'; '.join(notes);animated.append(area_id)
                    item=QTreeWidgetItem([label,detail]);item.setData(0,Qt.ItemDataRole.UserRole,area_id);item.setToolTip(1,detail);self.uses.addTopLevelItem(item)
            self.animation_note.setText('Animation uses this graphic in areas '+', '.join(f'${a:02X}' for a in animated)+'. You are editing stored base pixels, not the animation program. Frames may replace or scroll this artwork.' if animated else 'Static base graphic. Shared uses include all loaded aliases, even when not currently visible on a map.')
            self.uses.setColumnWidth(0,360);self.canvas.update()
        finally:self.loading=False
    def commit(self,pixels,label):
        if self.resource is None:return
        changes=pixel_changes(self.w.project,self.resource,pixels);self.w.commit_changes(changes,label);self.canvas.update();self.feedback.setText(f'{len(changes)} byte change(s) · shared by {self.uses.topLevelItemCount()} configurations.')
    def copy(self):self.clipboard=self.pixels.copy();self.feedback.setText('Copied 8 × 8 color indices; destination palette determines their colors.')
    def paste(self):
        if self.clipboard is not None:self.commit(self.clipboard.copy(),'Paste graphic pixels')
        else:self.feedback.setText('Copy pixels from a graphic first.')
    def restore(self):
        if self.resource is not None:self.commit(decode_3bpp(bytes(self.w.project.original(('terrain_graphic',self.resource,i)) for i in range(24))),'Restore graphic pixels')
    def visit(self,item,*_):self.w.select_area(item.data(0,Qt.ItemDataRole.UserRole));self.w.raise_()
    def closeEvent(self,event):self.canvas.cancel();event.accept()

def open_pixels(w,area_id,slot,palette=-1):
    w.end_stroke();w.play.setChecked(False)
    if not hasattr(w,'pixel_window'):w.pixel_window=PixelWindow(w)
    p=w.pixel_window;p.loading=True;p.area.setCurrentIndex(area_id);p.slot.setValue(slot);p.palette.setCurrentIndex(palette+1);p.loading=False;p.refresh();p.show();p.raise_();p.activateWindow()
