"""Layout preview of game's dialogue, read only right now, but a text editor will be added in the future that will show this as well so you cam
   see how it will look in the game.
"""
from pathlib import Path
import re
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPixmap,QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QScrollArea,QWidget,QGridLayout
from .events import text_fragment

FONT=Path(__file__).with_name('data')/'dialogue_font_80_ff.bin'

def glyph_name(code):
    if 0x80<=code<=0x89:return f'Small digit {code-0x80}'
    if code==0x8a:return 'LV label'
    if 0x8b<=code<=0x8e:return 'Status / meter component'
    if code==0x8f:return 'Circular status symbol'
    if 0xde<=code<=0xf6:return 'UI label component'
    if 0xf7<=code<=0xfe:return 'Window / border component'
    return text_fragment(bytes([code]))

def glyph_image(code,scale=3):
    data=FONT.read_bytes();a=(code-0x80)*16
    im=QImage(8,8,QImage.Format.Format_RGB32)
    colors=[QColor('#101c45'),QColor('#101c45'),QColor('#c4d0e5'),QColor('#ffffff')]
    for y in range(8):
        for x in range(8):
            k=((data[a+y*2]>>(7-x))&1)|(((data[a+y*2+1]>>(7-x))&1)<<1)
            im.setPixelColor(x,y,colors[k])
    return im.scaled(8*scale,8*scale,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)

def glyph_codes(text):
    mapping={text_fragment(bytes([i])):i for i in range(0x90,0xde)};mapping[' ']=0xff
    keys=sorted(mapping,key=len,reverse=True);result=[];i=0
    while i<len(text):
        if text[i]=='\n':result.append(None);i+=1;continue
        marker=re.match(r'\[([0-9A-F]{2})\]',text[i:])
        if marker:
            code=int(marker[1],16)
            if code>=0x80:result.append(code);i+=4;continue
        found=next((key for key in keys if text.startswith(key,i)),None)
        result.append(mapping[found] if found else 0xcf);i+=len(found) if found else 1
    return result

class DialoguePreview(QDialog):
    def __init__(self,parent,text):
        super().__init__(parent);self.setWindowTitle('Dialogue preview — read-only');self.resize(800,360)
        box=QVBoxLayout(self);note=QLabel('Verified game glyphs in an illustrative text box. Wrapping, page splits and colors here are preview choices; runtime names stay symbolic.');note.setWordWrap(True);box.addWidget(note)
        self.display=QLabel();self.display.setAlignment(Qt.AlignmentFlag.AlignCenter);box.addWidget(self.display,1)
        self.pages=[];line=[];lines=[]
        for code in glyph_codes(text):
            if code is None or len(line)==28:
                lines.append(line);line=[]
                if len(lines)==4:self.pages.append(lines);lines=[]
            if code is not None:line.append(code)
        if line:lines.append(line)
        if lines:self.pages.append(lines)
        if not self.pages:self.pages=[[]]
        bar=QHBoxLayout();box.addLayout(bar);self.page=QComboBox();self.page.addItems([f'Preview page {i+1} / {len(self.pages)}' for i in range(len(self.pages))]);bar.addWidget(self.page)
        close=QPushButton('Close');close.clicked.connect(self.close);bar.addWidget(close);self.page.currentIndexChanged.connect(self.render);self.render(0)

    def render(self,index):
        from PySide6.QtGui import QPainter,QPen
        im=QImage(240,64,QImage.Format.Format_RGB32);im.fill(QColor('#101c45'));p=QPainter(im)
        p.setPen(QPen(QColor('#d7dfef'),1));p.drawRect(1,1,237,61)
        for y,line in enumerate(self.pages[index]):
            for x,code in enumerate(line):p.drawImage(8+x*8,8+y*12,glyph_image(code,1))
        p.end();self.display.setPixmap(QPixmap.fromImage(im.scaled(720,192)))

class GlyphViewer(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Game glyph reference — read-only');self.resize(790,620)
        box=QVBoxLayout(self);note=QLabel('Text codes $80–FF, verified from the paused Foresta capture. Graphic components remain separate from prose; hover a tile for its code and description.');note.setWordWrap(True);box.addWidget(note)
        scroll=QScrollArea();scroll.setWidgetResizable(True);box.addWidget(scroll);content=QWidget();grid=QGridLayout(content);scroll.setWidget(content)
        for i in range(128):
            code=i+0x80;tile=QWidget();layout=QVBoxLayout(tile);pic=QLabel();pic.setPixmap(QPixmap.fromImage(glyph_image(code)));layout.addWidget(pic);layout.addWidget(QLabel(f'${code:02X}'));tile.setToolTip(glyph_name(code));grid.addWidget(tile,i//16,i%16)
        close=QPushButton('Close');close.clicked.connect(self.close);box.addWidget(close)
