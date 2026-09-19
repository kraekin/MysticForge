"""Readable movement controls; unverified scene steps remain visible and locked."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QListWidget,QLabel,QSpinBox,QComboBox
from .scene_commands import pairs,family,options
from .field_actions import field_action
class SceneCommandWidget(QWidget):
 changed=Signal()
 def __init__(self):
  super().__init__();self.loading=False;self.raw=[];self.original=b'';self.offsets=[]
  box=QVBoxLayout(self);self.list=QListWidget();box.addWidget(self.list,1)
  self.note=QLabel();self.note.setWordWrap(True);box.addWidget(self.note)
  row=QHBoxLayout();box.addLayout(row);self.direction=QComboBox();self.direction.addItems(['Up','Right','Down','Left']);self.count=QSpinBox();self.count.setRange(1,15)
  self.option_label=QLabel('Direction');row.addWidget(self.option_label);row.addWidget(self.direction);row.addWidget(QLabel('Tiles'));row.addWidget(self.count)
  self.list.currentRowChanged.connect(self.select);self.direction.currentIndexChanged.connect(self.edit);self.count.valueChanged.connect(self.edit)
 def title(self,i):
  value,action=self.raw[i:i+2];f=family(self.original[i+1],self.original[i])
  text=field_action(action,value) if action<0x80 else f'Call shared scene routine ${(action<<8)|value:04X}'
  return text+('' if f else ' — preserved')
 def load(self,original,value):
  self.loading=True;self.original=original;self.raw=list(value);self.offsets=pairs(original);self.list.clear()
  for i in self.offsets:self.list.addItem(self.title(i))
  self.loading=False;self.list.setCurrentRow(next((n for n,i in enumerate(self.offsets) if family(original[i+1],original[i]) and family(original[i+1],original[i])[0]=='walk'),next((n for n,i in enumerate(self.offsets) if family(original[i+1],original[i])),0)))
 def select(self,row):
  if self.loading:return
  self.loading=True;f=None
  if 0<=row<len(self.offsets):
   i=self.offsets[row];value,action=self.raw[i:i+2];f=family(self.original[i+1],self.original[i])
   if f:
    self.direction.clear()
    for ident,label in options(f,self.original[i]):self.direction.addItem(label,ident)
    self.option_label.setText('Audio' if f[0]=='audio' else 'Direction')
    self.direction.setCurrentIndex(self.direction.findData(value if f[0]=='audio' else action-f[1] if f[0]=='walk' else value>>4));self.count.setValue(max(1,value>>4))
  self.direction.setEnabled(bool(f));self.count.setEnabled(bool(f and f[0]=='walk'))
  self.note.setText('Choose an audio ID observed in original field events. Sequence order stays fixed.' if f and f[0]=='audio' else 'Edit direction and distance. Actor slots and sequence order stay fixed. Movement is relative to the actor’s runtime position; check the path and later scene positions in game.' if f else 'This step is preserved. Its parameters, call target or pose cannot be safely changed here yet.')
  self.loading=False
 def edit(self,*_):
  if self.loading or self.list.currentRow()<0:return
  i=self.offsets[self.list.currentRow()];f=family(self.original[i+1],self.original[i])
  if not f:return
  kind,base=f
  if kind=='audio':
   self.raw[i]=self.direction.currentData();self.list.currentItem().setText(self.title(i));self.changed.emit();return
  self.raw[i]=(self.count.value() if kind=='walk' else self.direction.currentIndex())*16+(self.original[i]&15)
  self.raw[i+1]=base+self.direction.currentIndex() if kind=='walk' else base
  self.list.currentItem().setText(self.title(i));self.changed.emit()
