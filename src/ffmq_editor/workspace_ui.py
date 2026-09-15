"""Task-oriented workspace controls; ROM/project behavior stays in its models."""
from PySide6.QtCore import Qt,QSize,QRectF,QPointF
from PySide6.QtGui import QAction,QActionGroup,QIcon,QPixmap,QPainter,QPen,QColor,QPolygonF
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QStackedWidget,QDialog,QPushButton

def tool_icon(kind):
    pix=QPixmap(24,24);pix.fill(Qt.GlobalColor.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(QColor('#b7dfed'),2))
    if kind=='Pencil':
        p.drawPolygon(QPolygonF([QPointF(4,20),QPointF(6,13),QPointF(17,2),QPointF(22,7),QPointF(11,18)]));p.drawLine(6,13,11,18)
    elif kind in ('Select','Move selection'):
        p.setPen(QPen(QColor('#b7dfed'),2,Qt.PenStyle.DashLine));p.drawRect(3,3,18,18)
        if kind=='Move selection':p.drawLine(7,12,17,12);p.drawLine(12,7,12,17)
    elif kind=='Fill':
        p.drawPolygon(QPolygonF([QPointF(3,12),QPointF(11,3),QPointF(20,12),QPointF(11,20)]));p.drawLine(3,12,20,12)
    elif kind=='Stamp':p.drawRect(3,16,18,5);p.drawRect(8,4,8,12)
    elif kind=='Objects':p.drawEllipse(8,2,8,8);p.drawRoundedRect(QRectF(5,12,14,10),3,3)
    elif kind=='Entrances':p.drawRect(5,2,13,20);p.drawLine(1,12,14,12);p.drawLine(10,8,14,12);p.drawLine(10,16,14,12)
    elif kind=='Overworld routes':
        p.drawLine(5,6,18,6);p.drawLine(18,6,18,18);p.drawEllipse(2,3,6,6);p.drawEllipse(15,15,6,6)
    elif kind=='Eyedropper':p.drawLine(5,19,18,6);p.drawLine(14,4,21,11);p.drawEllipse(2,18,4,4)
    else:
        p.drawLine(3,12,21,12);p.drawLine(12,3,12,21)
        p.drawLine(3,12,7,8);p.drawLine(21,12,17,16)
    p.end();return QIcon(pix)

def add_tool_buttons(w,bar):
    w.tool_actions={};group=QActionGroup(w);group.setExclusive(True)
    tools=[('Pencil','Pencil','Paint individual terrain cells','P'),('Fill','Fill','Fill connected matching terrain','F'),
           ('Select','Select','Select a rectangle to copy or save as a stamp','S'),('Stamp','Stamp','Place the copied terrain pattern','T'),
           ('Move selection','Move','Move selected terrain','M'),('Eyedropper','Pick','Pick a tile and map pass from the canvas','I'),
           ('Pan','Pan','Drag to pan the map','H'),('Objects','Objects','Select or move NPCs, chests and encounters','O'),
           ('Entrances','Entrances','Select an entrance marker and inspect its destination','E'),
           ('Overworld routes','Routes','Select overworld route nodes; switches to the overworld','R')]
    for name,label,tip,key in tools:
        if name in ('Objects','Pan'):bar.addSeparator()
        action=QAction(tool_icon(name),label,w);action.setCheckable(True);action.setShortcut(key)
        action.setToolTip(f'{tip} ({key})');action.triggered.connect(lambda checked=False,n=name:w.tool.setCurrentText(n))
        group.addAction(action);bar.addAction(action);w.tool_actions[name]=action
    w.tool_actions['Pencil'].setChecked(True)
    w.tool.currentTextChanged.connect(lambda name:[a.setChecked(n==name) for n,a in w.tool_actions.items()])
    bar.setIconSize(QSize(22,22));bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

def view_controls(w,layers):
    for checkbox in (w.backgrounds,w.sprite_art,w.hidden_sprites,w.show_connections,w.object_overlay,w.collision,w.play):
        action=QAction(checkbox.text(),w);action.setCheckable(True);action.setChecked(checkbox.isChecked());action.setToolTip(checkbox.toolTip())
        action.toggled.connect(checkbox.setChecked);checkbox.toggled.connect(action.setChecked);w.view_menu.addAction(action)
    w.view_menu.addSeparator()
    w.view_options=QDialog(w);w.view_options.setWindowTitle('Animation preview');box=QVBoxLayout(w.view_options)
    note=QLabel('Preview frames do not execute gameplay or modify the ROM.');note.setWordWrap(True);box.addWidget(note)
    box.addWidget(QLabel('Frame (60 Hz timeline)'));box.addWidget(w.frame)
    reset=QPushButton('Reset to initial frame');reset.clicked.connect(lambda:w.frame.setValue(0));box.addWidget(reset)
    w.action(w.view_menu,'Animation frame…',w.view_options.show)
    w.action(w.view_menu,'Map details…',lambda:w.show_map_details())

def version_name(w,area_id):
    if area_id==24:return 'Frozen · Aquaria'
    if area_id==25:return 'Thawed · Aquaria'
    area=w.rom.areas[area_id];members=w.rom.shared_areas(area.layout_id)
    return f'Configuration {members.index(area_id)+1} · {len(w.project.objects(area_id))} objects · area ${area_id:02X}'

class PanelHandle:
    """Keep source-inspector navigation compatible with the contextual stack."""
    def __init__(self,w,name):self.w,self.name=w,name
    def show(self):self.w.show_panel(self.name)
    def raise_(self):self.show()

def organize_panels(w):
    root=QWidget();box=QVBoxLayout(root);w.panel_selector=QComboBox();box.addWidget(w.panel_selector)
    w.panel_stack=QStackedWidget();box.addWidget(w.panel_stack,1)
    specs=[('Tiles','tile_dock'),('Objects','object_dock'),('Entrances','connection_dock'),('Routes','world_dock'),('Tile behavior','property_dock'),('Rewards & encounters','content_dock')]
    for name,attribute in specs:
        dock=getattr(w,attribute);widget=dock.widget();widget.setParent(None);w.removeDockWidget(dock);dock.hide();dock.deleteLater()
        w.panel_stack.addWidget(widget);w.panel_selector.addItem(name);setattr(w,attribute,PanelHandle(w,name))
    w.inspector_dock=w.dock('Tool controls',root,Qt.DockWidgetArea.RightDockWidgetArea)
    def show_panel(name):
        w.panel_selector.blockSignals(True);w.panel_selector.setCurrentText(name);w.panel_selector.blockSignals(False)
        w.panel_stack.setCurrentIndex(w.panel_selector.currentIndex());w.inspector_dock.show();w.inspector_dock.raise_()
    w.show_panel=show_panel
    def selected(index):
        w.panel_stack.setCurrentIndex(index)
        name=w.panel_selector.currentText()
        tool={'Tiles':'Pencil','Objects':'Objects','Entrances':'Entrances','Routes':'Overworld routes','Tile behavior':'Tile behavior'}.get(name)
        if tool:w.tool.setCurrentText(tool)
    w.panel_selector.currentIndexChanged.connect(selected)
    old=w.state_dock;widget=old.widget();widget.setParent(None);w.removeDockWidget(old);old.hide();old.deleteLater()
    w.state_dock=QDialog(w);w.state_dock.setWindowTitle('Map details · preview flags & source');w.state_dock.resize(900,520)
    QVBoxLayout(w.state_dock).addWidget(widget)
    w.resizeDocks([w.inspector_dock],[340],Qt.Orientation.Horizontal)
