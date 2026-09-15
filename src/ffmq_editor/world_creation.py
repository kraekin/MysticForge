"""Create a connected overworld location without changing existing IDs."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QComboBox,QSpinBox,QPushButton
from .world import DIRECTIONS,position
from .world_expansion import nodes,add_node,node_label
from .expanded_content_editor import commit

def open_new_location(w,source,direction):
 if not w.project.expanded:
  from .expansion_editor import show_expansion
  show_expansion(w);return
 d=QDialog(w);d.setWindowTitle('Add overworld location');d.resize(610,440);box=QVBoxLayout(d)
 note=QLabel('Add a spot along an unused direction, with a matching return route. Choose an existing location or a newly created map as the destination. Both directions use the required flag. Use the Artwork toolbar button to place the landmark sprite pieces. Ship routes and scripted entries are not created here.');note.setWordWrap(True);box.addWidget(note)
 form=QFormLayout();box.addLayout(form);start=QComboBox()
 for n in nodes(w.project):start.addItem(f'{node_label(w.project,n)} · {position(w.project,n)}',n)
 start.setCurrentIndex(start.findData(source));form.addRow('Connect from',start)
 way=QComboBox();way.addItems(DIRECTIONS);way.setCurrentIndex(direction);form.addRow('Unused direction',way)
 distance=QSpinBox();distance.setRange(1,31);distance.setValue(2);form.addRow('Distance in tiles',distance)
 entry=QComboBox()
 for n in range(22,56):
  raw=w.project.fixed('world_action',n)
  if raw[1] not in (0,1,2,4,5):continue
  target=w.connections.destination(raw[1],raw[0])
  if target:entry.addItem(f'{w.rom.areas[target[0]].name} · node ${n:02X}',n)
 for n in sorted(w.project.newmaps):entry.addItem(f'{w.rom.areas[n].name} · NEW area ${n:02X}',n)
 entry.setCurrentIndex(max(0,entry.findData(23)));form.addRow('Destination',entry)
 flag=QSpinBox();flag.setRange(1,255);flag.setDisplayIntegerBase(16);flag.setPrefix('$');flag.setValue(6);form.addRow('Required story flag',flag)
 hint=QLabel('New maps currently reuse Foresta’s in-game location name. Default $06 is set initially and may change with progression. Choose the flag that should unlock this path. The destination’s exit must return to the overworld without forcing a different node.');hint.setWordWrap(True);box.addWidget(hint)
 create=QPushButton('Create spot and two-way route');box.addWidget(create)
 def apply():
  def operation():add_node(w.project,start.currentData(),way.currentIndex(),distance.value(),23 if entry.currentData() in w.project.newmaps else entry.currentData(),entry.currentData(),flag.value())
  if commit(w,operation,'Add overworld location and routes'):d.accept();w.world_editor.node.setValue(max(nodes(w.project)))
 create.clicked.connect(apply);w.new_world_dialog=d;d.setModal(True);d.show()
