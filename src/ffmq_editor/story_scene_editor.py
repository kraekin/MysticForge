"""Map-based editor for the verified Kaeli axe scene."""
from copy import deepcopy
from PySide6.QtCore import Qt,Signal,QPointF
from PySide6.QtGui import QPainter,QColor,QPen,QPixmap
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QScrollArea,QMessageBox,QCheckBox
from . import story_scenes as scene
from .render import qimage
from .expanded_content_editor import commit

class RouteCanvas(QWidget):
 clicked=Signal(int,int)
 def __init__(self,dialog,image):
  super().__init__();self.dialog=dialog;self.image=QPixmap.fromImage(qimage(image));self.setMinimumSize(550,520);self.setMouseTracking(True)
 def bounds(self):return (0,0,24,24) if not self.dialog.full.isChecked() else (0,0,self.image.width()//16,self.image.height()//16)
 def transform(self):
  x,y,w,h=self.bounds();scale=min(self.width()/(w*16),self.height()/(h*16));return scale,(self.width()-w*16*scale)/2,(self.height()-h*16*scale)/2
 def paintEvent(self,event):
  p=QPainter(self);p.fillRect(self.rect(),QColor('#182128'));scale,ox,oy=self.transform();x,y,w,h=self.bounds();p.translate(ox,oy);p.scale(scale,scale);p.drawPixmap(0,0,self.image.copy(x*16,y*16,w*16,h*16))
  r=self.dialog.record;start=scene.xy(self.dialog.project.objects(scene.AREA)[1]);pickup=(r['axe'][0],r['axe'][1]+1)
  for key,origin,color in (('approach',start,'#7bff80'),('return',pickup,'#ffc060'),('mother',scene.xy(self.dialog.project.objects(scene.AREA)[0]),'#df9aff')):
   pts=[origin]+[tuple(v) for v in r[key]];p.setPen(QPen(QColor(color),2))
   for a,b in zip(pts,pts[1:]):p.drawLine(QPointF(a[0]*16+8,a[1]*16+8),QPointF(b[0]*16+8,b[1]*16+8))
   for n,(xx,yy) in enumerate(pts[1:],1):
    p.drawEllipse(QPointF(xx*16+8,yy*16+8),3,3)
    if self.dialog.key()==key:p.drawText(xx*16+10,yy*16+7,str(n))
  for label,(xx,yy),color in (('K',start,'#7bff80'),('A',r['axe'],'#76dcff'),('R',scene.END,'#ffc060'),('M',scene.xy(self.dialog.project.objects(scene.AREA)[0]),'#df9aff')):
   p.setPen(QPen(QColor(color),2));p.fillRect(xx*16+2,yy*16+2,12,12,QColor('#182128'));p.drawRect(xx*16,yy*16,16,16);p.drawText(xx*16+4,yy*16+12,label)
  p.end()
 def mousePressEvent(self,event):
  if event.button()!=Qt.MouseButton.LeftButton:return
  scale,ox,oy=self.transform();x=int((event.position().x()-ox)//(16*scale));y=int((event.position().y()-oy)//(16*scale));_,_,w,h=self.bounds()
  if 0<=x<w and 0<=y<h:self.clicked.emit(x,y)

class SceneEditor(QDialog):
 def __init__(self,w):
  super().__init__(w);self.window=w;self.project=w.project;self.record=deepcopy(w.project.story_scene or scene.defaults(w.project));self.record.setdefault('mother',deepcopy(scene.MOTHER_ROUTE))
  self.setWindowTitle('Kaeli’s axe scene — movement');self.resize(1080,760)
  root=QVBoxLayout(self);title=QLabel('Plan Kaeli and her mother’s routes');title.setStyleSheet('font-size:21px;font-weight:bold');root.addWidget(title)
  note=QLabel('This edits the original Foresta scene. Dialogue and joining the party stay intact. Green: Kaeli approaches. Orange: Kaeli returns. Purple: her mother walks after the axe is collected. Markers: K = Kaeli, M = mother, A = axe, R = return point. Routes are explicit tile steps; check walls, furniture and the hero’s position in game.');note.setWordWrap(True);root.addWidget(note)
  row=QHBoxLayout();root.addLayout(row,1);side=QVBoxLayout()
  self.full=QCheckBox('Show whole shared map')
  image=w.renderer.area(w.project,scene.AREA,set(w.project.base_rom.initial_flags),sprites=False)[0]
  self.canvas=RouteCanvas(self,image);row.addWidget(self.canvas,3);row.addLayout(side,2)
  self.mode=QComboBox();self.mode.addItems(['Place axe','Draw approach route','Draw return route','Draw mother’s route']);side.addWidget(self.mode)
  hint=QLabel('Place axe: click its new wall tile. This starts an L-shaped approach and return.\n\nTo draw around obstacles, choose a route, click Start route over, then click consecutive corners. Finish at target connects the last point to its required endpoint.');hint.setWordWrap(True);side.addWidget(hint)
  reset=QPushButton('Start route over');side.addWidget(reset);reset.clicked.connect(self.clear_route)
  undo=QPushButton('Remove last waypoint');side.addWidget(undo);undo.clicked.connect(self.remove_point)
  finish=QPushButton('Finish at target');side.addWidget(finish);finish.clicked.connect(self.finish)
  self.status=QLabel();self.status.setWordWrap(True);side.addWidget(self.status);side.addWidget(self.full);side.addStretch()
  warning=QLabel('First release: Kaeli and her mother must retain their original starting setup. The axe must remain the same object. Only this movement sequence is replaced; this is not a general cutscene editor.');warning.setWordWrap(True);side.addWidget(warning)
  buttons=QHBoxLayout();root.addLayout(buttons);restore=QPushButton('Restore original scene');buttons.addWidget(restore);restore.clicked.connect(self.restore_scene)
  self.apply_button=QPushButton('Apply scene changes');buttons.addWidget(self.apply_button);self.apply_button.clicked.connect(self.apply_scene);close=QPushButton('Close');buttons.addWidget(close);close.clicked.connect(self.close)
  self.mode.currentIndexChanged.connect(self.canvas.update);self.canvas.clicked.connect(self.pick);self.full.toggled.connect(self.canvas.update);self.refresh()
 def key(self):return 'approach' if self.mode.currentIndex()==1 else 'return' if self.mode.currentIndex()==2 else 'mother' if self.mode.currentIndex()==3 else None
 def origin(self,key):
  if key=='mother':return scene.xy(self.project.objects(scene.AREA)[0])
  return scene.xy(self.project.objects(scene.AREA)[1]) if key=='approach' else (self.record['axe'][0],self.record['axe'][1]+1)
 def target(self,key):
  if key=='mother':return scene.MOTHER_END
  return (self.record['axe'][0],self.record['axe'][1]+1) if key=='approach' else scene.END
 def connect(self,key,target):
  pts=self.record[key];old=pts[-1] if pts else self.origin(key)
  if old[0]!=target[0] and old[1]!=target[1]:pts.append([target[0],old[1]])
  if list(target)!=(pts[-1] if pts else list(old)):pts.append(list(target))
  if not pts:pts.append(list(target))
 def pick(self,x,y):
  key=self.key()
  if key is None:
   self.record['axe']=[x,y]
   for k in ('approach','return'):self.record[k]=[];self.connect(k,self.target(k))
  else:
   old=self.record[key][-1] if self.record[key] else self.origin(key)
   if old[0]!=x and old[1]!=y:self.status.setText('Click a corner on the same row or column as the last waypoint.');return
   self.record[key].append([x,y])
  self.refresh()
 def clear_route(self):
  key=self.key()
  if key:self.record[key]=[];self.refresh()
 def remove_point(self):
  key=self.key()
  if key and self.record[key]:self.record[key].pop();self.refresh()
 def finish(self):
  key=self.key()
  if key:self.connect(key,self.target(key));self.refresh()
 def refresh(self):
  from .expansion_editor import snapshot,restore
  p=self.project;before=snapshot(p)
  try:
   scene.apply(p,self.record);parts=scene.validate(p);self.status.setText(f"Axe: {tuple(self.record['axe'])}\nPickup: {self.target('approach')}\nReturn: {scene.END}\nMother finishes: {scene.MOTHER_END}\n{sum(map(len,parts))} / 256 route bytes.\nRoutes ready to apply. Test both hero approach directions in game.");self.apply_button.setEnabled(True)
  except (ValueError,IndexError) as e:self.status.setText(str(e));self.apply_button.setEnabled(False)
  finally:restore(p,before)
  self.canvas.update()
 def apply_scene(self):
  if self.window.project is not self.project:self.window.error('The project changed; reopen the scene editor.');return
  if commit(self.window,lambda:scene.apply(self.project,self.record),'Edit Kaeli axe scene'):
   if getattr(self,'embedded',False):self.refresh()
   else:self.accept()
 def restore_scene(self):
  from .object_editor import field_changes
  def reset():
   self.project.story_scene=None
   for key,(_,value) in field_changes(self.project,scene.AREA,5,{'X':10,'Y':11}).items():self.project.set(key,value)
  if commit(self.window,reset,'Restore Kaeli axe scene'):
   if getattr(self,'embedded',False):self.record=scene.defaults(self.project);self.refresh()
   else:self.accept()

def open_scene(w):
 if not w.project.expanded:
  from .expansion_editor import show_expansion
  show_expansion(w);return
 from .scene_editor import open_workspace
 d=open_workspace(w,0x03da2f,scene.AREA);w.story_scene_dialog=d
 if d.route:d.tabs.setCurrentWidget(d.route)
