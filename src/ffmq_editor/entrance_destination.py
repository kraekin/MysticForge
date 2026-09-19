"""Choose an entrance arrival by clicking a named destination map."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QPushButton
from .render import qimage

class ArrivalCanvas(QWidget):
    clicked=Signal(int,int)
    def __init__(self):
        super().__init__();self.pixmap=QPixmap();self.point=(0,0);self.setMinimumSize(480,360)
    def transform(self):
        if self.pixmap.isNull():return 1,0,0
        s=min(self.width()/self.pixmap.width(),self.height()/self.pixmap.height())
        return s,(self.width()-self.pixmap.width()*s)/2,(self.height()-self.pixmap.height()*s)/2
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#182128'))
        s,x,y=self.transform();p.translate(x,y);p.scale(s,s);p.drawPixmap(0,0,self.pixmap)
        p.setPen(QPen(QColor('black'),3));p.drawRect(self.point[0]*16,self.point[1]*16,16,16)
        p.setPen(QPen(QColor('#ffff00'),1));p.drawRect(self.point[0]*16,self.point[1]*16,16,16);p.end()
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        s,ox,oy=self.transform();x=int((event.position().x()-ox)//(16*s));y=int((event.position().y()-oy)//(16*s))
        if 0<=x<self.pixmap.width()//16 and 0<=y<self.pixmap.height()//16:self.clicked.emit(x,y)

class DestinationDialog(QDialog):
    def __init__(self,w,raw,apply,title='Change entrance destination',note=''):
        super().__init__(w);self.setWindowTitle(title);self.resize(850,760);self.window=w;self.apply_callback=apply
        box=QVBoxLayout(self);label=QLabel(note or 'Choose a map setup, then click the square where the player should arrive. Check the return entrance separately.');label.setWordWrap(True);box.addWidget(label)
        self.target=QComboBox();self.target.setEditable(True);self.target.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        from .workspace_ui import version_name
        for area in w.rom.areas:self.target.addItem(f'{area.name} / {version_name(w,area.id)} · ${area.id:02X}',area.id)
        box.addWidget(self.target);self.canvas=ArrivalCanvas();box.addWidget(self.canvas,1)
        row=QHBoxLayout();box.addLayout(row);self.x=QSpinBox();self.y=QSpinBox();self.facing=QComboBox()
        self.facing.addItems(['Up','Right','Down','Left'])
        for name,widget in [('Arrival X',self.x),('Arrival Y',self.y),('Facing',self.facing)]:row.addWidget(QLabel(name));row.addWidget(widget)
        hint=QLabel('Yellow square = arrival. This preview does not simulate collision or story scripts.');box.addWidget(hint)
        buttons=QHBoxLayout();box.addLayout(buttons);self.apply_button=QPushButton('Use this destination');buttons.addWidget(self.apply_button);cancel=QPushButton('Cancel');buttons.addWidget(cancel)
        cancel.clicked.connect(self.reject);self.apply_button.clicked.connect(self.apply)
        self.canvas.clicked.connect(self.pick);self.x.valueChanged.connect(self.mark);self.y.valueChanged.connect(self.mark)
        self.target.currentIndexChanged.connect(self.render_map)
        self.target.setCurrentIndex(self.target.findData(raw[-3]));self.render_map();self.x.setValue(raw[-1]&63);self.y.setValue(raw[-2]);self.facing.setCurrentIndex(raw[-1]>>6)
    def render_map(self):
        area=self.target.currentData()
        if area is None:return
        attrs=self.window.rom.attributes[self.window.rom.areas[area].attributes_id]
        self.x.setMaximum(attrs.width-1);self.y.setMaximum(attrs.height-1)
        image=self.window.renderer.area(self.window.project,area,self.window.project.flags)[0]
        self.canvas.pixmap=QPixmap.fromImage(qimage(image));self.mark()
    def mark(self,*_):self.canvas.point=(self.x.value(),self.y.value());self.canvas.update()
    def pick(self,x,y):self.x.setValue(x);self.y.setValue(y)
    def apply(self):
        area=self.target.currentData()
        if area is None:return
        raw=bytes((area,self.y.value(),self.x.value()|(self.facing.currentIndex()<<6)))
        if self.apply_callback(raw):self.accept()
