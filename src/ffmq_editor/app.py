"""
   MysticForge 0.2-09-2026 • FFMQ Editor • Early Alpha -- Use at your own risk, not everything is complete, and some stuff is still read only.
   I have tested everything I could so far, but have not gone through the game completely to verify that everything works as intended. 
   As such, there may be bugs, issues, or game breaking shit that happens. 

   I know some people are going to hate it, but AI was used to assist in the development of this software. Without it this wouldn't exist.
   Ive always been surprised by the lack of tools for this game, and now that AI seems to be quite good at SNES assembly, reverse engineering,
   and can compare the code against the rom. I figured why not try it out to see what happens. Sure I could have dont a lot of this myself,
   but that would have taken months or longer due to work and life. 


   Thanks to https://github.com/wildham0/FFMQRando/ for some information used in development

   Also thanks to https://github.com/TheAnsarya/ffmq-info This helped a ton, especially the assembly code, although some stuff was wrong
   or mislabeled or such, AI was able to figure out what was wrong, and compared what was correct against the 1.0 rom.

   Finally, this does target the USA 1.0 version of the rom. The editor does have an option to fix the life spell bug that was fixed in 1.1.
   Support for 1.1 may be added at a future date, but for now, especially since you can patch the bug with this editor now, its not a priority.

   No license is provided, but you can do whatever you want with this software. Modify it, sell it, claim it as your own. I really don't care lol. 
   Just don't blame me if it breaks your rom or your save file or whatever. I will try to fix bugs and update the editor until it is fully complete
   but I do not make any guarantees.


   The event and script stuff is not complete, and is currently read only for reference. Editing will come in the future.

   Some stuff might be worded weird or named strangely or whatever due to AI, I do plan on going through soon and cleaning
   up the wording, and menu items and other stuff soon. 

"""
from .event_flags import flag_label
from pathlib import Path
import json
import sys
import traceback
import time
from collections import deque

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRectF
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QFontDatabase, QIcon, QKeySequence, QPainter, QPen, QPixmap, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QCheckBox, QGraphicsView, QGraphicsScene, QSplitter, QToolBar,
    QTableWidget, QTableWidgetItem, QColorDialog, QDialog, QPushButton, QStackedWidget, QAbstractItemView, QTreeWidget, QTreeWidgetItem, QSpinBox,
)
from .rom import Rom, FormatError
from .project import Project
from .render import Renderer, qimage, color_rgb
from .object_editor import ObjectEditor,field_changes
from .selection import Selection,Stamp
from .connections import Connections
from .connection_editor import ConnectionPanel
from .property_editor import PropertyEditor
from .resources import terrain_passage
from .world_editor import WorldEditor
from .content_editor import ContentEditor
from .world import points as route_points,available as route_available,position as node_position

from .paths import user_directory, recovery_directory
ROOT = Path(__file__).resolve().parents[2]

class EditCommand(QUndoCommand):
    def __init__(self, window, changes, label, applied=False):
        super().__init__(label)
        self.window, self.changes, self.applied = window, changes, applied

    def undo(self):
        for key, (old, _) in self.changes.items():
            self.window.project.set(key, old)
        self.window.refresh()

    def redo(self):
        if not self.applied:
            for key, (_, new) in self.changes.items():
                self.window.project.set(key, new)
        self.applied = False
        self.window.refresh()

class Canvas(QGraphicsView):
    cellPressed = Signal(int,int,bool)
    cellMoved = Signal(int,int)
    strokeFinished = Signal()
    hovered = Signal(int,int)

    def __init__(self, editable=True):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.picture = self.scene().addPixmap(QPixmap())
        self.setBackgroundBrush(QColor("#13181e"))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.editable, self.drawing = editable, False
        self.grid, self.objects, self.properties = False, (), None
        self.cells, self.map_width, self.patch_rect = b"", 0, None
        self.show_properties = False
        self.selection_rect=None
        self.connections=();self.arrival=None
        self.traversal_overlay=0
        self.world_paths=();self.world_nodes=();self.art_preview=None;self.object_preview=None
        self._pan_position = None
        self.pan_mode = not editable

    def set_image(self, rgba, section=None):
        bounds=section or QRectF(0,0,rgba.shape[1],rgba.shape[0])
        x,y,width,height=map(int,(bounds.x(),bounds.y(),bounds.width(),bounds.height()))
        self.picture.setPixmap(QPixmap.fromImage(qimage(rgba[y:y+height,x:x+width].copy())))
        self.picture.setPos(x,y)
        self.setSceneRect(bounds)
        self.viewport().update()

    def coords(self,event):
        point = self.mapToScene(event.position().toPoint())
        if not self.sceneRect().contains(point):return -1,-1
        return int(point.x()//16), int(point.y()//16)

    def mousePressEvent(self,event):
        if event.button() == Qt.MouseButton.MiddleButton or (self.pan_mode and event.button()==Qt.MouseButton.LeftButton):
            self._pan_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.editable and event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):
            self.drawing = event.button() == Qt.MouseButton.LeftButton
            self.cellPressed.emit(*self.coords(event), event.button()==Qt.MouseButton.RightButton)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._pan_position is not None:
            delta = event.position()-self._pan_position
            self._pan_position = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-int(delta.y()))
            return
        x,y = self.coords(event)
        self.hovered.emit(x,y)
        if self.drawing:
            self.cellMoved.emit(x,y)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self._pan_position is not None:
            self._pan_position = None
            self.unsetCursor()
        if self.drawing:
            self.drawing = False
            self.cellMoved.emit(*self.coords(event))
            self.strokeFinished.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self,event):
        self.art_preview=None
        self.object_preview=None
        self.viewport().update()
        super().leaveEvent(event)

    def wheelEvent(self,event):
        factor = 1.25 if event.angleDelta().y()>0 else 0.8
        current = self.transform().m11()
        if 0.2 <= current*factor <= 12:
            self.scale(factor,factor)
        event.accept()

    def drawForeground(self,painter,rect):
        painter.save();painter.setClipRect(self.sceneRect())
        if self.object_preview:
            x,y,pix=self.object_preview;painter.save();painter.setOpacity(0.7);painter.drawPixmap((x-1)*16,(y-1)*16,pix);painter.restore()
        if self.art_preview:
            x,y,pix=self.art_preview;painter.save();painter.setOpacity(0.7);painter.drawPixmap(x*16,y*16,16,16,pix);painter.restore()
        pen = QPen(QColor(0,0,0)); pen.setCosmetic(True)
        painter.setPen(pen)
        if self.grid:
            for x in range(max(0,int(rect.left())//16)*16,int(min(rect.right(),self.sceneRect().right()))+1,16):
                painter.drawLine(x,0,x,int(self.sceneRect().height()))
            for y in range(max(0,int(rect.top())//16)*16,int(min(rect.bottom(),self.sceneRect().height()))+1,16):
                painter.drawLine(0,y,int(self.sceneRect().right()),y)
        if self.show_properties and self.properties is not None:
            for y in range(max(0,int(rect.top())//16),min(int(rect.bottom())//16+1,int(self.sceneRect().height())//16)):
                for x in range(max(0,int(rect.left())//16),min(int(rect.right())//16+1,self.map_width)):
                    cell = self.cells[y*self.map_width+x]
                    value = int(self.properties[cell&127,0]) & 7
                    if value == 7:
                        painter.fillRect(x*16,y*16,16,16,QColor(255,60,85,95))
        painter.setPen(QPen(QColor("#58ddf0"),1))
        if self.traversal_overlay and self.properties is not None:
            for y in range(max(0,int(rect.top())//16),min(int(rect.bottom())//16+1,int(self.sceneRect().height())//16)):
                for x in range(max(0,int(rect.left())//16),min(int(rect.right())//16+1,self.map_width)):
                    value=int(self.properties[self.cells[y*self.map_width+x]&127,0])
                    if self.traversal_overlay==1:
                        colors=("#62ccad","#75a9ff","#dfba64","#d395e8","#7dd7e4","#ea9e78","#a6b86c","#f45b70")
                        color=QColor(colors[value&7]);color.setAlpha(100)
                    else:color=QColor(50,210,120,95) if terrain_passage(value,self.traversal_overlay-2) else QColor(245,65,80,110)
                    if self.traversal_overlay!=1 and (value&0xf0 or int(self.properties[self.cells[y*self.map_width+x]&127,1])!=0) and terrain_passage(value,self.traversal_overlay-2):color=QColor(240,175,40,110)
                    painter.fillRect(x*16,y*16,16,16,color)
                    if self.traversal_overlay==1:painter.drawText(x*16+4,y*16+12,str(value&7))
        for i,obj in enumerate(self.objects):
            x,y = (obj[3]&63)*16,(obj[2]&63)*16
            painter.drawRect(x+1,y+1,14,14)
            painter.drawText(x+2,y+12,f"{i:X}")
        if self.patch_rect:
            pen = QPen(QColor("#ffda73"),2); pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(self.patch_rect)
        if self.selection_rect:
            pen=QPen(QColor("#71edff"),2);pen.setCosmetic(True);painter.setPen(pen)
            painter.drawRect(self.selection_rect)
        painter.setPen(QPen(QColor("#ff84df"),1))
        for index,entry in enumerate(self.connections):
            x,y=entry.x*16,entry.y*16
            painter.drawRect(x+1,y+1,14,14);painter.drawText(x+1,y+12,f"E{index:X}")
        if self.arrival:
            x,y=self.arrival
            painter.setPen(QPen(QColor("#65f5b3"),2));painter.drawEllipse(x*16,y*16,16,16)
        for points,enabled,selected in self.world_paths:
            pen=QPen(QColor("#5deaff" if selected else "#69ef9c" if enabled else "#8a8f98"),3 if selected else 1);pen.setCosmetic(True);painter.setPen(pen)
            for (ax,ay),(bx,by) in zip(points,points[1:]):
                if abs(ax-bx)<=1 and abs(ay-by)<=1:painter.drawLine(ax*16+8,ay*16+8,bx*16+8,by*16+8)
        painter.setPen(QColor("#ffde86"))
        for node,x,y in self.world_nodes:
            painter.drawEllipse(x*16+3,y*16+3,10,10);painter.drawText(x*16+9,y*16+4,f"{node:02X}")

        painter.restore()

class MainWindow(QMainWindow):
    def __init__(self,rom):
        super().__init__()
        self.rom, self.project, self.renderer = rom, Project(rom), Renderer(rom)
        self.stack = QUndoStack(self)
        self.area_id, self.brush, self.stroke = 0, 0, {}
        self._refreshing = False
        self.selection=Selection(self)
        self.connections=Connections(rom);self.arrival=None
        self.resize(1450,950)
        self.setMinimumSize(1000,650)
        self._menus()
        self._workspace()
        self._sidebar()
        self._inspector()
        self.object_editor=ObjectEditor(self)
        self.object_dock=self.dock("Object editor",self.object_editor,Qt.DockWidgetArea.RightDockWidgetArea)
        self.property_editor=PropertyEditor(self)
        self.property_dock=self.dock("Tile behavior",self.property_editor,Qt.DockWidgetArea.RightDockWidgetArea)
        self.world_editor=WorldEditor(self)
        self.world_dock=self.dock("Overworld routes",self.world_editor,Qt.DockWidgetArea.RightDockWidgetArea)
        self.content_editor=ContentEditor(self)
        self.content_dock=self.dock("Rewards & encounters",self.content_editor,Qt.DockWidgetArea.RightDockWidgetArea)
        self.connection_panel=ConnectionPanel(self)
        self.connection_dock=self.dock("Entrances and exits",self.connection_panel,Qt.DockWidgetArea.BottomDockWidgetArea)
        self.resizeDocks([self.area_dock],[240],Qt.Orientation.Horizontal)
        from .workspace_ui import organize_panels
        organize_panels(self)
        self.stack.cleanChanged.connect(self.update_title)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(16)
        self.render_timer.timeout.connect(self.refresh_map)
        self.animation_timer=QTimer(self);self.animation_timer.setInterval(100)
        self.animation_timer.timeout.connect(self.advance_frame)
        self._advancing=False
        self.refresh()
        self.update_title()
        self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def action(self,menu,label,callback,shortcut=None):
        action = QAction(label,self)
        if shortcut: action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _menus(self):
        file = self.menuBar().addMenu("&File")
        self.action(file,"New project",self.new_project,QKeySequence.StandardKey.New)
        self.action(file,"Open project…",self.open_project,QKeySequence.StandardKey.Open)
        self.action(file,"Recover autosave…",self.recover_autosave)
        self.action(file,"Save project",self.save_project,QKeySequence.StandardKey.Save)
        self.action(file,"Save project as…",lambda:self.save_project(True),QKeySequence.StandardKey.SaveAs)
        file.addSeparator()
        self.action(file,"Export ROM copy…",self.export_rom,"Ctrl+E")
        from .patch_editor import show_patch_export
        self.action(file,"Export patch…",lambda:show_patch_export(self))
        from .expansion_editor import show_expansion
        self.action(file,"ROM expansion…",lambda:show_expansion(self))
        self.action(file,"Export current view as PNG…",self.export_png)
        database_menu=self.menuBar().addMenu("&Database")
        from .database_editor import open_database
        self.action(database_menu,"Open game database…",lambda:open_database(self),"Ctrl+D")
        edit = self.menuBar().addMenu("&Edit")
        from .metatile_editor import open_metatiles
        self.action(edit,"Metatile editor…",lambda:open_metatiles(self))
        from .rom_fixes import show_fixes
        self.action(edit,"Optional ROM fixes…",lambda:show_fixes(self))
        undo = self.stack.createUndoAction(self,"Undo"); undo.setShortcut(QKeySequence.StandardKey.Undo); edit.addAction(undo)
        redo = self.stack.createRedoAction(self,"Redo"); redo.setShortcut(QKeySequence.StandardKey.Redo); edit.addAction(redo)
        edit.addSeparator()
        self.action(edit,"Copy terrain selection",self.copy_selection,QKeySequence.StandardKey.Copy)
        self.action(edit,"Cut terrain selection",lambda:self.copy_selection(True),QKeySequence.StandardKey.Cut)
        self.action(edit,"Paste / stamp",lambda:self.tool.setCurrentText("Stamp"),QKeySequence.StandardKey.Paste)
        self.action(edit,"Move selection",lambda:self.tool.setCurrentText("Move selection"))
        self.action(edit,"Save selection as stamp…",self.save_stamp)
        self.action(edit,"Load stamp…",self.load_stamp)
        self.action(edit,"Deselect",self.deselect,"Escape")
        events_menu=self.menuBar().addMenu("E&vents")
        from .event_browser import show_browser
        self.action(events_menu,"Browse events & references…",lambda:show_browser(self),"Ctrl+Shift+E")
        help_menu = self.menuBar().addMenu("&Help")
        from .diagnostics import show as show_diagnostics
        self.action(help_menu,"Diagnostics…",lambda:show_diagnostics(self))
        from .branding import about
        self.action(help_menu,"About MysticForge…",lambda:about(self))
        bar = QToolBar("Tools");bar.setMovable(False);self.addToolBar(bar)
        bar.addAction(undo);bar.addAction(redo);bar.addSeparator()
        self.tool = QComboBox(self);self.tool.hide()
        self.tool.addItems(["Pencil","Fill","Eyedropper","Pan","Objects","Select","Stamp","Move selection","Tile behavior","Overworld routes","Rewards & encounters","Entrances","Artwork"])
        from .workspace_ui import add_tool_buttons
        add_tool_buttons(self,bar)
        self.tool.currentTextChanged.connect(lambda text:setattr(self.canvas,"pan_mode",text=="Pan"))
        self.tool.currentTextChanged.connect(self.tool_changed)
        self.layer_bit = QCheckBox("Upper map pass");self.layer_bit.setToolTip("Bit 7 of the logical map cell; separate from SNES hardware priority.");self.layer_bit.hide()
        bar.addSeparator()
        self.grid = QCheckBox("Grid");bar.addWidget(self.grid)
        self.grid.toggled.connect(self.toggle_grid)
        self.object_overlay = QCheckBox("All object positions",self);self.object_overlay.hide()
        self.object_overlay.setToolTip("Raw positions of all area records, including objects hidden by game flags.")
        self.object_overlay.toggled.connect(lambda:self.refresh_map())
        self.collision = QCheckBox("Blocked walking tiles",self);self.collision.hide()
        self.collision.setToolTip("Highlights terrain class 7, which blocks ordinary walking. Does not simulate objects, jumping, tools or scripted movement.")
        self.collision.toggled.connect(lambda:self.refresh_map())
        self.action(bar,"Fit",self.fit_views)
        self.action(bar,"1:1",lambda:self.canvas.resetTransform())
        layers=QToolBar("Rendering");layers.setMovable(False);self.addToolBarBreak();self.addToolBar(layers)
        self.backgrounds=QCheckBox("Backgrounds");self.backgrounds.setChecked(True);layers.addWidget(self.backgrounds)
        self.sprite_art=QCheckBox("Sprites");self.sprite_art.setChecked(True);layers.addWidget(self.sprite_art)
        self.hidden_sprites=QCheckBox("Include hidden objects");layers.addWidget(self.hidden_sprites)
        self.hidden_sprites.setToolTip("Include objects whose game flag is currently off. Preview uses initial poses and positions; saved enemy/chest state and scripted movement are not simulated.")
        for check in (self.backgrounds,self.sprite_art,self.hidden_sprites):check.toggled.connect(lambda:self.refresh_map())
        self.show_connections=QCheckBox("Entrances / exits");layers.addWidget(self.show_connections)
        self.show_connections.toggled.connect(self.connections_toggled)
        layers.addSeparator()
        self.play=QCheckBox("Play animation");layers.addWidget(self.play);self.play.toggled.connect(self.play_changed)
        layers.addWidget(QLabel("  Frame "))
        self.frame=QSpinBox();self.frame.setRange(0,36000);layers.addWidget(self.frame)
        self.frame.setToolTip("Show animations in the editor.")
        self.frame.valueChanged.connect(self.frame_changed)
        self.action(layers,"Reset",lambda:self.frame.setValue(0))
        layers.hide()
        self.view_menu=self.menuBar().addMenu("&View")
        help_action=next((a for a in self.menuBar().actions() if a.text().replace("&","")=="Help"),None)
        if help_action:self.menuBar().insertMenu(help_action,self.view_menu)
        from .workspace_ui import view_controls
        view_controls(self,layers)


    def _workspace(self):
        root = QWidget();layout = QVBoxLayout(root);layout.setContentsMargins(12,10,12,8)
        self.heading = QLabel();self.heading.setObjectName("heading");layout.addWidget(self.heading)
        version_row=QHBoxLayout();self.version_label=QLabel('Map setup');version_row.addWidget(self.version_label)
        self.version=QComboBox(self);self.version.hide()
        from .setup_selector import SetupButtons,show_details,focus_objects
        self.setup_buttons=SetupButtons(self);version_row.addWidget(self.setup_buttons,1)
        self.version.currentIndexChanged.connect(self.version_selected)
        self.map_details_button=QPushButton('Map details…');self.map_details_button.clicked.connect(lambda:self.show_map_details());version_row.addWidget(self.map_details_button);layout.addLayout(version_row)
        self.version_hint=QLabel();self.version_hint.setWordWrap(True);layout.addWidget(self.version_hint)
        setup_tools=QHBoxLayout();layout.addLayout(setup_tools)
        setup_details=QPushButton("Entrances, differences & setup name…");setup_details.clicked.connect(lambda:show_details(self));setup_tools.addWidget(setup_details)
        focus=QPushButton("Focus on setup objects");focus.clicked.connect(lambda:focus_objects(self));setup_tools.addWidget(focus)
        setup_tools.addStretch()
        row = QHBoxLayout();row.addWidget(QLabel("Story preview"))
        self.preset = QComboBox();self.preset.setToolTip("Changes the visual preview flags only. This is separate from selecting a map configuration and does not change ROM story progression.");self.preset.addItems(["Initial","Earth restored","Water restored","Fire restored","All restored","Custom"])
        row.addWidget(self.preset);self.preset.currentTextChanged.connect(self.preset_changed)
        self.compare = QCheckBox("Compare with initial state");row.addWidget(self.compare);self.compare.toggled.connect(self.compare_changed)
        row.addStretch();layout.addLayout(row)
        self.full_aquaria=QCheckBox("Show full Aquaria layout")
        self.full_aquaria.setToolTip("Show both stored town sections. Editing coordinates remain the original ROM coordinates.")
        self.full_aquaria.toggled.connect(lambda _: (self.refresh_map(),self.fit_views()))
        layout.addWidget(self.full_aquaria)
        self.terrain_choices=QWidget();row=QHBoxLayout(self.terrain_choices);row.setContentsMargins(0,0,0,0)
        row.addWidget(QLabel("Edit terrain"));self.target=QComboBox(self);self.target.hide()
        from .setup_selector import TerrainButtons
        self.terrain_buttons=TerrainButtons(self);row.addWidget(self.terrain_buttons,1)
        self.target.currentIndexChanged.connect(lambda:self.refresh_map());layout.addWidget(self.terrain_choices)
        self.shared = QLabel();self.shared.setWordWrap(True);layout.addWidget(self.shared)
        self.shared_links=QPushButton("Shared terrain uses…");self.shared_links.setFlat(True);layout.addWidget(self.shared_links)
        from .terrain_links import show_terrain_uses
        self.shared_links.clicked.connect(lambda:show_terrain_uses(self))
        from .expansion_editor import copy_terrain
        self.copy_terrain_button=QPushButton('Make terrain independent…');self.copy_terrain_button.clicked.connect(lambda:copy_terrain(self));layout.addWidget(self.copy_terrain_button)
        self.storage_budget=QPushButton('Map storage · calculating…');self.storage_budget.setFlat(True);self.storage_budget.clicked.connect(self.show_storage_details);layout.addWidget(self.storage_budget)
        self.storage_budget.setToolTip('Compression depends on tile patterns, not walkable area. Overflowing maps are automatically repacked with neighboring layouts inside verified storage. The shared budget includes optimal recompression of all layouts in that pool. No ROM expansion or unverified free space is used.')
        self.budget_timer=QTimer(self);self.budget_timer.setSingleShot(True);self.budget_timer.setInterval(250);self.budget_timer.timeout.connect(self.update_storage_budget)
        self.target.currentIndexChanged.connect(lambda:self.budget_timer.start())
        self.split = QSplitter()
        self.before_holder = QWidget();before_layout=QVBoxLayout(self.before_holder);before_layout.setContentsMargins(0,0,3,0)
        before_layout.addWidget(QLabel("Initial state • same project edits"));self.before = Canvas(False);before_layout.addWidget(self.before)
        self.split.addWidget(self.before_holder);self.before_holder.hide()
        self.canvas = Canvas();self.split.addWidget(self.canvas);layout.addWidget(self.split,1)
        self.canvas.cellPressed.connect(self.begin_stroke);self.canvas.cellMoved.connect(self.drag_stroke);self.canvas.strokeFinished.connect(self.end_stroke)
        self.canvas.hovered.connect(self.hover)
        self.notice=QLabel("ROM terrain, backgrounds and sprites • animation preview; scripted movement and saved enemy/chest state are not simulated")
        self.notice.setWordWrap(True);self.notice.hide();layout.addWidget(self.notice)
        self.setCentralWidget(root)

    def dock(self,title,widget,side):
        dock=QDockWidget(title,self);dock.setWidget(widget);self.addDockWidget(side,dock);return dock

    def _sidebar(self):
        root=QWidget();box=QVBoxLayout(root)
        self.search=QLineEdit();self.search.setPlaceholderText("Find map or area hex ID…");box.addWidget(self.search)
        hint=QLabel("Choose a map, then a named setup above the canvas.");hint.setWordWrap(True);box.addWidget(hint)
        self.areas=QTreeWidget();self.areas.setHeaderHidden(True);self.areas.setRootIsDecorated(False);box.addWidget(self.areas)
        self.area_items={};self.map_items={};self.last_area={}
        from .workspace_ui import ordered_map_areas
        for a in ordered_map_areas(self.rom):
            if a.layout_id not in self.map_items:
                item=QTreeWidgetItem([a.name]);item.setData(0,Qt.ItemDataRole.UserRole,a.id)
                self.areas.addTopLevelItem(item);self.map_items[a.layout_id]=item;self.last_area[a.layout_id]=a.id
            self.area_items[a.id]=self.map_items[a.layout_id]
        self.areas.setCurrentItem(self.areas.topLevelItem(0))
        self.areas.currentItemChanged.connect(self.area_selected)
        self.search.textChanged.connect(self.filter_areas)
        from .new_map_editor import open_new_map
        add=QPushButton('New map…');add.clicked.connect(lambda:open_new_map(self));box.addWidget(add)
        self.area_dock=self.dock('Maps',root,Qt.DockWidgetArea.LeftDockWidgetArea)

    def filter_areas(self,text):
        query=text.strip().lower().removeprefix('$')
        from .workspace_ui import version_name
        for layout,item in self.map_items.items():
            names=[version_name(self,a) for a in self.rom.shared_areas(layout)]
            ids=[f'{a:02x}' for a in self.rom.shared_areas(layout)]
            match=query in item.text(0).lower() or query in ids or any(query in name.lower() for name in names)
            item.setHidden(not match)

    def select_area(self,area_id):
        self.search.clear();self.end_stroke();self.selection.reset()
        layout=self.rom.areas[area_id].layout_id;self.last_area[layout]=area_id
        self.areas.blockSignals(True);self.areas.setCurrentItem(self.area_items[area_id]);self.areas.blockSignals(False)
        self.area_id=area_id;self.project.area_id=area_id
        self.refresh();self.fit_views()

    def version_selected(self,index):
        if self._refreshing or index<0:return
        area=self.version.itemData(index)
        if area is not None and area!=self.area_id:self.select_area(area)

    def show_map_details(self):
        self.state_dock.show();self.state_dock.raise_();self.state_dock.activateWindow()

    def show_storage_details(self):
        self.update_storage_budget()
        QMessageBox.information(self,'Map storage',getattr(self,'storage_detail','Calculating…'))

    def _inspector(self):
        root=QWidget();box=QVBoxLayout(root)
        self.tile_label=QLabel("Metatiles");box.addWidget(self.tile_label)
        self.tiles=QListWidget();self.tiles.setViewMode(QListWidget.ViewMode.IconMode)
        self.tiles.setIconSize(QSize(32,32));self.tiles.setGridSize(QSize(43,53));self.tiles.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.tiles.setMovement(QListWidget.Movement.Static);self.tiles.setMinimumWidth(210);box.addWidget(self.tiles,1)
        from .metatile_editor import open_metatiles
        edit_metatile=QPushButton("Edit selected metatile…");edit_metatile.clicked.connect(lambda:open_metatiles(self));box.addWidget(edit_metatile)
        self.tiles.currentRowChanged.connect(lambda row:setattr(self,"brush",max(0,row)))
        box.addWidget(self.layer_bit);self.layer_bit.show()
        self.paint_triggers=QCheckBox("Paint entrance triggers");self.paint_triggers.setToolTip("Allow terrain painting and stamps to create working entrance tiles. Coordinate lookup records and destinations are not created automatically.");box.addWidget(self.paint_triggers)
        palette_toggle=QCheckBox("Edit palette colors");box.addWidget(palette_toggle)
        self.palette_table=QTableWidget(8,8);self.palette_table.setFixedHeight(183)
        self.palette_table.horizontalHeader().hide();self.palette_table.verticalHeader().hide()
        self.palette_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i in range(8):self.palette_table.setColumnWidth(i,25);self.palette_table.setRowHeight(i,20)
        self.palette_table.cellDoubleClicked.connect(self.edit_color);box.addWidget(self.palette_table);self.palette_table.hide();palette_toggle.toggled.connect(self.palette_table.setVisible)
        self.tile_dock=self.dock("Tiles & colors",root,Qt.DockWidgetArea.RightDockWidgetArea)
        root=QWidget();box=QVBoxLayout(root)
        box.addWidget(QLabel("Preview flags · changes here do not modify ROM progression"))
        self.flag_row=QHBoxLayout();self.flag_checks={}
        for flag,label in [(1,"Earth"),(2,"Water"),(3,"Fire"),(5,"Wind")]:
            check=QCheckBox(f"{label} (${flag:02X})");self.flag_checks[flag]=check;self.flag_row.addWidget(check)
            check.toggled.connect(lambda enabled,f=flag:self.toggle_flag(f,enabled))
        box.addLayout(self.flag_row)
        self.actions_table=QTableWidget(0,4);self.actions_table.setHorizontalHeaderLabels(["Flag","Action","Resource","Preview"])
        self.actions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.actions_table.itemChanged.connect(self.action_flag_changed)
        self.actions_table.horizontalHeader().setStretchLastSection(True);box.addWidget(self.actions_table)
        self.details=QLabel();self.details.setWordWrap(True);box.addWidget(self.details)
        self.state_dock=self.dock("State & source",root,Qt.DockWidgetArea.BottomDockWidgetArea);self.state_dock.setMinimumHeight(150)

    def error(self,error):
        QMessageBox.warning(self,"MysticForge",str(error))

    def area_selected(self,current,previous=None):
        if not current:return
        self.end_stroke()
        self.selection.reset()
        layout=self.rom.areas[current.data(0,Qt.ItemDataRole.UserRole)].layout_id
        self.area_id=self.last_area[layout];self.project.area_id=self.area_id
        self.refresh();self.fit_views()

    def tool_changed(self,name):
        if name in ("Artwork","Overworld routes") and self.rom.areas[self.area_id].layout_id!=0:
            self.tool.setCurrentText("Pencil");return
        self.canvas.art_preview=None
        self.canvas.object_preview=None
        if name=='Objects' and self.rom.areas[self.area_id].layout_id and not self.project.objects(self.area_id):self.object_editor.mode.setCurrentIndex(1)
        if name=="Artwork":
            from .landmark_editor import open_landmarks
            open_landmarks(self)
        if name!="Entrances" and hasattr(self,"connection_panel"):self.connection_panel.move_button.setChecked(False)
        if name=="Overworld routes":
            self.world_dock.show();self.world_dock.raise_()
        if name=="Rewards & encounters":self.content_dock.show();self.content_dock.raise_()
        if name=="Tile behavior":self.property_dock.show();self.property_dock.raise_()
        self.end_stroke()
        if name not in ("Select","Move selection","Stamp"):self.selection.reset()
        if hasattr(self,'panel_stack'):
            panel={'Artwork':'Artwork','Objects':'Objects','Entrances':'Entrances','Overworld routes':'Routes','Tile behavior':'Tile behavior','Rewards & encounters':'Rewards & encounters'}.get(name,'Tiles')
            self.show_panel(panel)
        self.show_connections.setChecked(name=='Entrances')
        if name!='Entrances':
            self.arrival=None;self._drag_entrance=None;self.canvas.arrival=None
        if name=="Objects":self.object_dock.show();self.object_dock.raise_()
        if hasattr(self,"render_timer"):self.refresh_map()

    def connections_toggled(self,enabled):
        if enabled and self.tool.currentText()=="Entrances":self.connection_dock.show();self.connection_dock.raise_()
        self.refresh_map()

    def commit_changes(self,changes,label):
        self.end_stroke()
        if changes:self.stack.push(EditCommand(self,changes,label))

    def deselect(self):
        self.canvas.object_preview=None
        if hasattr(self,'object_editor') and self.tool.currentText()=='Objects':self.object_editor.mode.setCurrentIndex(0)
        self.canvas.art_preview=None
        if hasattr(self,"landmark_editor"):
            self.landmark_editor.drag_index=None
            if self.tool.currentText()=="Artwork":self.landmark_editor.mode.setCurrentIndex(1)
        self.selection.reset();self.refresh_map()

    def copy_selection(self,cut=False):
        try:
            self.selection.stamp=self.selection.capture()
            if cut:self.commit_changes(self.selection.clear_changes(),"Cut terrain selection")
            self.statusBar().showMessage("Terrain copied. Choose Stamp or Ctrl+V and click to paste. Cut/move fills the source with the current brush.")
        except ValueError as error:self.error(error)

    def save_stamp(self):
        try:
            stamp=self.selection.capture()
            name,_=QFileDialog.getSaveFileName(self,"Save terrain stamp",str(user_directory()/"My stamp.ffmqstamp.json"),"Terrain stamp (*.ffmqstamp.json)")
            if name:stamp.save(name)
        except (OSError,ValueError) as error:self.error(error)

    def load_stamp(self):
        name,_=QFileDialog.getOpenFileName(self,"Load terrain stamp",str(user_directory()),"Terrain stamp (*.json)")
        if not name:return
        try:
            self.selection.stamp=Stamp.load(name);self.tool.setCurrentText("Stamp")
            self.statusBar().showMessage("Click the map to place the loaded stamp.")
        except (OSError,ValueError,TypeError) as error:self.error(error)

    def preset_changed(self,name):
        if self._refreshing or name=="Custom":return
        self.end_stroke();self.project.set_preset(name);self.select_aquaria_variant();self.refresh()

    def select_aquaria_variant(self):
        # UI convenience between the existing frozen/thawed area records.
        # This does not modify game transitions or claim to emulate event scripts.
        if self.area_id in (24,25):
            target=25 if 2 in self.project.flags else 24
            self.select_area(target)

    def toggle_flag(self,flag,enabled):
        if self._refreshing:return
        self.end_stroke()
        if enabled:self.project.flags.add(flag)
        else:self.project.flags.discard(flag)
        self.preset.setCurrentText("Custom");self.select_aquaria_variant();self.refresh()

    def action_flag_changed(self,item):
        if item.column()!=0 or self._refreshing:return
        self.toggle_flag(item.data(Qt.ItemDataRole.UserRole),item.checkState()==Qt.CheckState.Checked)

    def compare_changed(self,enabled):
        self.before_holder.setVisible(enabled);self.refresh_map();QTimer.singleShot(0,self.fit_views)

    def toggle_grid(self,enabled):
        for canvas in (self.canvas,self.before):canvas.grid=enabled;canvas.viewport().update()

    def fit_views(self):
        if self.compare.isChecked():
            width=max(1,self.split.width()//2)
            self.split.setSizes([width,width])
        for canvas in (self.canvas,self.before):canvas.fitInView(canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def refresh(self):
        if self.rom is not self.project.rom:
            self.rom=self.project.rom;self.renderer=Renderer(self.rom);self.connections=Connections(self.rom)
            self.areas.blockSignals(True);self.areas.clear();self.area_items={};self.map_items={};self.last_area={}
            from .workspace_ui import ordered_map_areas
            for a in ordered_map_areas(self.rom):
                if a.layout_id not in self.map_items:
                    item=QTreeWidgetItem([a.name]);item.setData(0,Qt.ItemDataRole.UserRole,a.id)
                    self.areas.addTopLevelItem(item);self.map_items[a.layout_id]=item;self.last_area[a.layout_id]=a.id
                self.area_items[a.id]=self.map_items[a.layout_id]
            if self.area_id>=len(self.rom.areas):self.area_id=0;self.project.area_id=0
            self.areas.setCurrentItem(self.area_items[self.area_id]);self.areas.blockSignals(False)
        if hasattr(self,"database_window"):self.database_window.project_changed()
        if hasattr(self,"metatile_window"):self.metatile_window.refresh()
        if hasattr(self,"pixel_window"):self.pixel_window.refresh()
        if self._refreshing:return
        self._refreshing=True
        try:
            area=self.rom.areas[self.area_id];attrs=self.rom.attributes[area.attributes_id]
            is_world=area.layout_id==0
            for tool in ('Artwork','Overworld routes'):
                self.tool_actions[tool].setEnabled(is_world)
                self.tool.model().item(self.tool.findText(tool)).setEnabled(is_world)
            for panel in ('Artwork','Routes'):
                index=self.panel_selector.findText(panel)
                if index>=0:self.panel_selector.model().item(index).setEnabled(is_world)
            if not is_world and self.tool.currentText() in ('Artwork','Overworld routes'):self.tool.setCurrentText('Pencil')
            self.heading.setText(area.name)
            from .workspace_ui import version_name
            members=self.rom.shared_areas(area.layout_id)
            self.version.blockSignals(True);self.version.clear()
            for a in members:self.version.addItem(version_name(self,a),a)
            self.version.setCurrentIndex(members.index(self.area_id));self.version.blockSignals(False)
            self.version.hide();self.version_label.setVisible(len(members)>1)
            self.setup_buttons.update_setups(members);self.setup_buttons.setVisible(len(members)>1)
            from .map_setups import info
            setup=info(self.project,self.area_id)
            shares=[i for i in members if i!=self.area_id and self.project.layout_id(i)==self.project.layout_id(self.area_id)]
            self.version_hint.setText(setup['meaning']+f" {len(self.project.objects(self.area_id))} object records. "+(f"Terrain shared with {len(shares)} other setup(s)." if shares else "No other setup shares this base terrain."))
            self.version_hint.setVisible(True)
            for flag,check in self.flag_checks.items():check.setChecked(flag in self.project.flags)
            selected=self.target.currentData()
            layout_id=self.project.layout_id(self.area_id)
            self.target.clear();self.target.addItem("Independent base terrain" if layout_id>=44 else "Base terrain",("layout",layout_id))
            self.copy_terrain_button.setEnabled(layout_id<44)
            self.copy_terrain_button.setText('Terrain is independent' if layout_id>=44 else 'Make terrain independent…')
            self.copy_terrain_button.setToolTip('Copy base cells only. Shared area-record aliases move together; state changes, graphics and entrances remain shared.')
            actions=self.rom.area_actions[self.area_id]
            self.actions_table.setRowCount(len(actions))
            for row,action in enumerate(actions):
                enabled=action.flag in self.project.flags
                check=QTableWidgetItem(flag_label(action.flag));check.setData(Qt.ItemDataRole.UserRole,action.flag)
                check.setFlags(check.flags()|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
                self.actions_table.setItem(row,0,check)
                names={0x22:"Map change",0x23:"Metatile replacement",0x24:"Palette",0x28:"NPC group"}
                for column,text in enumerate((names.get(action.opcode,f"Action ${action.opcode:02X}"),f"${action.value:02X}","Active" if enabled else "Inactive"),1):
                    self.actions_table.setItem(row,column,QTableWidgetItem(text))
                if action.opcode==0x22:
                    self.target.addItem(f"State map change ${action.value:02X} · flag ${action.flag:02X}"+("" if enabled else " · inactive"),("change",action.value))
            if selected is not None:
                index=self.target.findData(selected)
                if index>=0:self.target.setCurrentIndex(index)
            self.terrain_buttons.update_targets();self.terrain_choices.setVisible(self.target.count()>1)
            self.full_aquaria.setVisible(self.area_id in (24,25))
            rgba,atlas,props,state=self.renderer.area(self.project,self.area_id)
            self._state=state
            brush=self.brush
            self.tiles.blockSignals(True)
            self.tiles.clear()
            for index in range(128):
                item=QListWidgetItem(QIcon(QPixmap.fromImage(qimage(atlas[index]))),f"{index:02X}")
                item.setToolTip(f"Metatile ${index:02X} · properties {props[index,0]:02X} {props[index,1]:02X}")
                self.tiles.addItem(item)
            self.tiles.setCurrentRow(brush)
            self.tiles.blockSignals(False)
            self.brush=brush
            self.tile_label.setText(f"Metatiles · set ${self.project.tileset(self.area_id):02X} · palette ${state.palette:02X}")
            for index,value in enumerate(self.project.palette(state.palette)):
                item=QTableWidgetItem();item.setBackground(QColor(*color_rgb(value)));item.setToolTip(f"Color ${index:02X} · BGR15 ${value:04X}")
                self.palette_table.setItem(index//8,index%8,item)
            self.details.setText(f"Layout ${layout_id:02X} · {attrs.width} × {attrs.height} metatiles · area record file ${area.offset:06X} · {len(self.project.objects(self.area_id))}/{self.project.object_capacity(self.area_id)} object slots\n"+"; ".join(state.warnings))
            self.object_editor.refresh()
            self.property_editor.refresh()
            self.world_editor.refresh();self.content_editor.refresh()
        finally:self._refreshing=False
        self.refresh_map();self.update_title();self.budget_timer.start()

    def update_storage_budget(self):
        from .layout_storage import plan_layouts
        try:
            plan=plan_layouts(self.project,strict=False)
            resource=self.project.layout_id(self.area_id)
            if self.project.expanded:
                pool=plan.pools[0]
                self.storage_detail=f'1 MiB expanded ROM export. Layout ${resource:02X}: {plan.sizes[resource]:,} compressed bytes.\nNew storage used: {pool.used:,} / {pool.capacity:,} bytes, including tables, bank padding and reserved content banks.\nIndependent terrain slots: {len(self.project.layout_copies)} / 20.\nOriginal files remain unchanged. BPS supports expanded export; IPS does not.\nPrivate metatile sets: {len(self.project.content["sets"])} / 16. Shared new destination slots: {len(self.project.content["entrances"])+len(self.project.newmaps)} / 39 (doors and map entries). New maps: {len(self.project.newmaps)} / 8. Private sprite sets: {len(self.project.sprite_sets)}.\nNew overworld locations: {len(self.project.world["nodes"])} / 7. Expanded routes: up to 128 segments each.\nExtra objects: up to 16 stored records on smaller field maps. Original larger lists keep their capacity. State patches and source graphics retain their existing limits.'
                self.storage_budget.setText(f'Expanded storage: {pool.free:,} bytes available · details…');self.storage_budget.setToolTip(self.storage_detail);self.storage_budget.setStyleSheet('color:#b6dfc3;text-align:left');return
            original=self.rom.layouts[resource]
            pool=next(p for p in plan.pools if resource in p.ids)
            blocked=[p for p in plan.pools if p.free<0]
            target=self.target.currentData()
            prefix='State patch uses fixed storage. ' if target and target[0]=='change' else ''
            text=f'{prefix}Layout ${resource:02X}: {plan.sizes[resource]:,} compressed bytes (original slot {original.end-original.start:,}) · Shared pool: {pool.used:,} / {pool.capacity:,}'
            if blocked:
                text+=' · Export blocked: '+', '.join(f'pool ${p.ids[0]:02X}–${p.ids[-1]:02X} is {-p.free:,} bytes over' for p in blocked)
                color='#ff9e9e'
            else:
                text+=f' · {pool.free:,} bytes available after repacking'
                if pool.repack:text+=' · Export will repack this pool'
                color='#ffcf85' if pool.repack or pool.free<128 else '#b6dfc3'
            self.storage_detail=text+'\n\nCompression depends on tile patterns, not walkable area. Repacking shares verified storage with other maps; no ROM expansion is used.'
            compact=('Map storage: export blocked — details…' if blocked else f'Map storage: {pool.free:,} bytes available'+(' · will repack' if pool.repack else '')+' · details…')
            self.storage_budget.setText(compact);self.storage_budget.setToolTip(self.storage_detail);self.storage_budget.setStyleSheet(f'color:{color};text-align:left')
        except ValueError as error:
            self.storage_budget.setText('Map storage check unavailable: '+str(error));self.storage_budget.setStyleSheet('color:#ff9e9e')

    def render_area(self,area_id,flags=None):
        return self.renderer.area(self.project,area_id,flags,backgrounds=self.backgrounds.isChecked(),
                                  sprites=self.sprite_art.isChecked(),show_hidden=self.hidden_sprites.isChecked(),frame=self.frame.value())

    def play_changed(self,enabled):
        self._play_start=time.monotonic();self._play_frame=self.frame.value()
        if enabled:self.animation_timer.start()
        else:self.animation_timer.stop()

    def frame_changed(self):
        if not self._advancing:
            self._play_start=time.monotonic();self._play_frame=self.frame.value()
        self.refresh_map()

    def advance_frame(self):
        self._advancing=True
        try:
            frame=min(self.frame.maximum(),self._play_frame+int((time.monotonic()-self._play_start)*60))
            self.frame.setValue(frame)
            if frame==self.frame.maximum():self.play.setChecked(False)
        finally:self._advancing=False

    def aquaria_section(self,area_id):
        if area_id not in (24,25) or self.full_aquaria.isChecked():return None
        return QRectF(0 if area_id==24 else 512,0,512,512)

    def refresh_map(self):
        if self._refreshing:return
        rgba,atlas,props,state=self.render_area(self.area_id)
        self._state=state;self.canvas.set_image(rgba,self.aquaria_section(self.area_id))
        self.terrain_buttons.update_targets()
        self._terrain_sources=self.renderer.terrain_sources(self.area_id,atlas,state,self.backgrounds.isChecked())
        area=self.rom.areas[self.area_id];attrs=self.rom.attributes[area.attributes_id]
        self.canvas.objects=self.project.objects(self.area_id) if self.object_overlay.isChecked() or self.tool.currentText()=="Objects" else ()
        self.notice.setText("Terrain copies share their source cells: editing either visible copy can change both." if self.backgrounds.isChecked() and self.renderer.has_shifted_overlay(self.area_id) else "ROM terrain, backgrounds and sprites • animation preview; scripted movement and saved enemy/chest state are not simulated")
        self.connections.project=self.project
        entries=self.connections.for_area(self.area_id,state,props)
        self.connection_panel.update_entries(entries)
        self.canvas.connections=entries if self.show_connections.isChecked() and self.tool.currentText()=="Entrances" else ()
        self.canvas.arrival=self.arrival[1:] if self.arrival and self.arrival[0]==self.area_id and self.show_connections.isChecked() and self.tool.currentText()=="Entrances" else None
        self.canvas.selection_rect=None
        selected=self.object_editor.selected
        if self.tool.currentText()=="Objects" and 0<=selected<len(self.project.objects(self.area_id)):
            obj=self.project.objects(self.area_id)[selected]
            self.canvas.selection_rect=QRectF((obj[3]&63)*16,(obj[2]&63)*16,16,16)
        elif self.tool.currentText()=="Entrances" and self.connection_panel.entry() is not None:
            entry=self.connection_panel.entry();self.canvas.selection_rect=QRectF(entry.x*16,entry.y*16,16,16)
        elif self.selection.rect:
            x,y,width,height=self.selection.rect
            self.canvas.selection_rect=QRectF(x*16,y*16,width*16,height*16)
        self.canvas.properties=props;self.canvas.cells=bytes(state.cells[int(i)] for i in self._terrain_sources);self.canvas.map_width=attrs.width
        self.canvas.traversal_overlay=self.property_editor.overlay.currentIndex() if self.tool.currentText()=="Tile behavior" else 0
        if self.tool.currentText()=="Tile behavior" and self.canvas.traversal_overlay:
            self.canvas.objects=tuple(o for o in self.project.objects(self.area_id) if o[0] in self.project.flags)
        from .world_expansion import routes as world_routes,nodes as world_nodes,route_data
        self.canvas.world_paths=();self.canvas.world_nodes=()
        if area.layout_id==0 and self.world_editor.overlay.isChecked() and self.tool.currentText()=="Overworld routes":
            selected=self.world_editor.route()
            self.canvas.world_paths=tuple((route_points(self.project,r),route_available(self.project,r),r==selected) for r in world_routes(self.project) if route_data(self.project,r)[0])
            self.canvas.world_nodes=tuple((node,*node_position(self.project,node)) for node in world_nodes(self.project))
        self.canvas.show_properties=self.collision.isChecked()
        self.canvas.patch_rect=None
        target=self.target.currentData()
        if target and target[0]=="change":
            patch=self.rom.changes[target[1]]
            self.shared_links.setText("See configurations using this map change…")
            self.canvas.patch_rect=QRectF(patch.x*16,patch.y*16,patch.width*16,patch.height*16)
            active=any(a.opcode==0x22 and a.value==patch.id for a in state.applied)
            self.shared.setText(f"Editing map change ${patch.id:02X}, shared wherever this change is referenced. "+("Yellow outline marks its rectangle." if active else "Activate its flag to see edits in this preview."))
        else:
            users=self.project.shared_areas(self.project.layout_id(self.area_id))
            self.shared_links.setText(f"See all {len(users)} terrain configuration(s) and state overrides…")
            self.shared.setText(f"Base terrain is shared by {len(users)} map configuration(s). State changes may override some tiles."+
                (" Choose Frozen or Thawed using Map setup." if area.layout_id==3 else ""))
            if self.project.layout_id(self.area_id)>=44:self.shared.setText(f'Independent base terrain · used by {len(users)} configuration(s). Restoration changes, objects, entrances and graphics retain their existing sharing.')
        if self.compare.isChecked():
            before_area=24 if self.area_id==25 else self.area_id
            self.before.set_image(self.render_area(before_area,self.rom.initial_flags)[0],self.aquaria_section(before_area))
        self.canvas.viewport().update()

    def edit_key(self,x,y):
        area=self.rom.areas[self.area_id];attrs=self.rom.attributes[area.attributes_id]
        if not (0<=x<attrs.width and 0<=y<attrs.height):return None
        source=self.terrain_source(x,y);x,y=source%attrs.width,source//attrs.width
        kind,resource=self.target.currentData()
        if kind=="layout":return(kind,resource,y*attrs.width+x)
        patch=self.rom.changes[resource]
        if not (patch.x<=x<patch.x+patch.width and patch.y<=y<patch.y+patch.height):return None
        return(kind,resource,(y-patch.y)*patch.width+x-patch.x)

    def terrain_source(self,x,y):
        attrs=self.rom.attributes[self.rom.areas[self.area_id].attributes_id]
        sources=getattr(self,"_stroke_sources",None)
        if sources is None:sources=self._terrain_sources
        return int(sources[y*attrs.width+x])

    def hover(self,x,y):
        if self.tool.currentText()=='Objects' and self.object_editor.placing():
            self.object_editor.palette.hover(x,y);return
        if self.tool.currentText()=="Artwork" and hasattr(self,"landmark_editor"):
            self.landmark_editor.hover_map(x,y);return
        attrs=self.rom.attributes[self.rom.areas[self.area_id].attributes_id]
        if 0<=x<attrs.width and 0<=y<attrs.height:
            value=self._state.cells[self.terrain_source(x,y)]
            self.statusBar().showMessage(f"X {x:02X} ({x})    Y {y:02X} ({y})    cell ${value:02X}    brush ${self.brush:02X}")

    def begin_stroke(self,x,y,pick=False):
        self.play.setChecked(False)
        self.end_stroke()
        self._stroke_sources=self._terrain_sources.copy()
        self._last_cell=(x,y)
        attrs=self.rom.attributes[self.rom.areas[self.area_id].attributes_id]
        if not (0<=x<attrs.width and 0<=y<attrs.height):return
        if self.tool.currentText()=="Artwork":
            if self.rom.areas[self.area_id].layout_id==0:self.landmark_editor.press_map(x,y,pick)
            return
        if self.tool.currentText()=="Entrances":
            if self.connection_panel.move_button.isChecked():
                selected=self.connection_panel.entry()
                if selected is None or (x,y)!=(selected.x,selected.y):
                    self.connection_panel.move_to(x,y);return
                self.connection_panel.move_button.setChecked(False)
            entries=self.connection_panel.entries
            hits=[i for i,e in enumerate(entries) if (e.x,e.y)==(x,y)]
            if hits:
                self.connection_panel.selecting_on_canvas=True
                try:
                    self.connection_panel.table.selectRow(hits[0]);self.connection_panel.locate()
                finally:self.connection_panel.selecting_on_canvas=False
                self.show_panel('Entrances')
                if not pick:
                    self.connection_panel.move_feedback.setText('Drag to a new tile, then release.')
                    self._drag_entrance=entries[hits[0]];self._entrance_drop=(x,y)
            return
        if self.tool.currentText()=="Rewards & encounters":return
        if self.tool.currentText()=="Overworld routes":
            if self.rom.areas[self.area_id].layout_id==0:
                from .world_expansion import nodes
                nearby=[n for n in nodes(self.project) if max(abs(node_position(self.project,n)[0]-x),abs(node_position(self.project,n)[1]-y))<=1]
                if nearby:self.world_editor.node.setValue(min(nearby,key=lambda n:abs(node_position(self.project,n)[0]-x)+abs(node_position(self.project,n)[1]-y)))
            return
        if self.tool.currentText()=="Tile behavior":
            self.property_editor.click(x,y,pick);return
        if not pick and self.tool.currentText() in ("Select","Stamp","Move selection"):
            try:self.selection.begin(x,y)
            except ValueError as error:self.error(error)
            return
        if self.tool.currentText()=="Objects":
            if self.object_editor.placing() and not pick:
                self._drag_object=-1;self.object_editor.palette.place(x,y);return
            if pick:self.object_editor.mode.setCurrentIndex(0)
            objects=self.project.objects(self.area_id)
            hits=[i for i,obj in enumerate(objects) if (obj[3]&63,obj[2]&63)==(x,y)]
            visible=[i for i in hits if objects[i][0] in self.project.flags]
            selected=self.object_editor.selected
            chosen=selected if selected in hits else (visible or hits or [-1])[-1]
            self.object_editor.list.setCurrentRow(chosen)
            self.object_editor.open_content(chosen)
            self._drag_object=chosen if not pick else -1
            return
        if pick or self.tool.currentText()=="Eyedropper":
            value=self._state.cells[self.terrain_source(x,y)];self.brush=value&127;self.tiles.setCurrentRow(self.brush);self.layer_bit.setChecked(bool(value&128));return
        if self.tool.currentText()=="Fill":
            origin=self.edit_key(x,y)
            if origin is None:return
            old=self.project.get(origin);queue=deque([(x,y)]);seen=set()
            while queue:
                point=queue.popleft()
                if point in seen:continue
                seen.add(point);key=self.edit_key(*point)
                if key is None or self.project.get(key)!=old:continue
                self.paint_cell(*point)
                px,py=point;queue.extend(((px-1,py),(px+1,py),(px,py-1),(px,py+1)))
            self.end_stroke()
        elif self.tool.currentText()=="Pencil":self.paint_cell(x,y)

    def drag_stroke(self,x,y):
        if self.tool.currentText()=="Tile behavior":
            if self.property_editor.mode.currentIndex() in (2,4):
                x0,y0=getattr(self,'_last_cell',(x,y));steps=max(abs(x-x0),abs(y-y0),1)
                for step in range(1,steps+1):self.property_editor.click(round(x0+(x-x0)*step/steps),round(y0+(y-y0)*step/steps),drag=True)
                self._last_cell=(x,y)
            return
        if self.tool.currentText()=="Artwork":
            self.landmark_editor.move_map(x,y);return
        if self.tool.currentText()=="Entrances":
            if getattr(self,"_drag_entrance",None) is not None:
                self._entrance_drop=(x,y)
                self.canvas.arrival=(x,y);self.canvas.viewport().update()
            return
        if self.tool.currentText() in ("Select","Move selection"):
            attrs=self.rom.attributes[self.rom.areas[self.area_id].attributes_id]
            self.selection.drag(max(0,min(x,attrs.width-1)),max(0,min(y,attrs.height-1)));return
        if self.tool.currentText()=="Objects":
            if self.object_editor.placing():return
            index=getattr(self,"_drag_object",-1)
            if index<0:return
            attrs=self.rom.attributes[self.rom.areas[self.area_id].attributes_id]
            if not(0<=x<attrs.width and 0<=y<attrs.height):return
            changes=field_changes(self.project,self.area_id,index,{"X":x,"Y":y})
            for key,(old,new) in changes.items():
                self.stroke[key]=(self.stroke.get(key,(old,new))[0],new);self.project.set(key,new)
            self.refresh_map();return
        if self.tool.currentText()!="Pencil":return
        # Bresenham interpolation avoids gaps when mouse events are coalesced.
        x0,y0=getattr(self,"_last_cell",(x,y))
        dx,dy=abs(x-x0),-abs(y-y0)
        sx,sy=(1 if x0<x else -1),(1 if y0<y else -1)
        error=dx+dy
        while True:
            self.paint_cell(x0,y0)
            if (x0,y0)==(x,y):break
            doubled=2*error
            if doubled>=dy:error+=dy;x0+=sx
            if doubled<=dx:error+=dx;y0+=sy
        self._last_cell=(x,y)

    def paint_cell(self,x,y):
        if self.tool.currentText() not in ("Pencil","Fill"):return
        key=self.edit_key(x,y)
        if key is None:return
        new=self.brush | (128 if self.layer_bit.isChecked() else 0)
        old=self.project.get(key)
        from .terrain_paint import scenery_value
        try:new=scenery_value(self,old,new)
        except ValueError as error:
            self.statusBar().showMessage(str(error));return
        if old==new:return
        previous=self.stroke.get(key,(old,new))[0]
        self.stroke[key]=(previous,new);self.project.set(key,new)
        self.storage_budget.setText('Map storage · updating compressed budget…');self.budget_timer.start()
        if not self.render_timer.isActive():self.render_timer.start()

    def end_stroke(self):
        if hasattr(self,"landmark_editor"):self.landmark_editor.finish_map()
        entry=getattr(self,'_drag_entrance',None)
        self._drag_entrance=None
        if entry is not None:
            drop=self._entrance_drop
            self.canvas.arrival=None
            if drop!=(entry.x,entry.y):
                from .connection_editor import entrance_move_changes
                try:
                    edits=entrance_move_changes(self,entry,*drop)
                    self.commit_changes(edits,'Drag entrance and trigger tile')
                    self.connection_panel.move_feedback.setText(f'Entrance moved to ({drop[0]}, {drop[1]}). Undo restores its previous position.')
                except ValueError as error:
                    self.connection_panel.move_feedback.setText('Entrance not moved: '+str(error))
                    self.statusBar().showMessage(str(error))
            self.refresh_map()
        self.selection.finish()
        self._stroke_sources=None
        if not self.stroke:return
        changes={key:values for key,values in self.stroke.items() if values[0]!=values[1]}
        self.stroke={}
        if changes:self.stack.push(EditCommand(self,changes,"Move object" if next(iter(changes))[0]=="object" else f"Paint {len(changes)} cell(s)",applied=True))

    def edit_color(self,row,column):
        self.end_stroke();key=("palette",self._state.palette,row*8+column);old=self.project.get(key)
        chosen=QColorDialog.getColor(QColor(*color_rgb(old)),self,"Edit shared palette color")
        if not chosen.isValid():return
        channels=(chosen.red(),chosen.green(),chosen.blue())
        value=sum(round(channel*31/255)<<shift for channel,shift in zip(channels,(0,5,10)))
        if value!=old:self.stack.push(EditCommand(self,{key:(old,value)},f"Palette ${key[1]:02X}, color ${key[2]:02X}"))

    def update_title(self):
        name=self.project.path.name if self.project.path else "Untitled project"
        self.setWindowTitle(f"{'* ' if not self.stack.isClean() else ''}{name} — MysticForge · {'1 MiB expanded' if self.project.expanded else '512 KiB'}")

    def save_project(self,save_as=False):
        if not self.confirm_database_edits():return False
        self.end_stroke();path=self.project.path
        if save_as or not path:
            name,_=QFileDialog.getSaveFileName(self,"Save project",str(user_directory()/"My map.ffmq.json"),"FFMQ project (*.ffmq.json)")
            if not name:return False
            path=Path(name)
        try:
            self.project.save(path);self.stack.setClean();self.update_title()
            from .session import remember_project
            remember_project(self.project)
            if getattr(self,'_recovery_project',None) is self.project:
                try:self._recovery_path.unlink(missing_ok=True)
                except OSError:pass
            return True
        except (OSError,ValueError) as error:self.error(error);return False

    def confirm_database_edits(self):
        return not hasattr(self,"database_window") or self.database_window.confirm_navigation()

    def confirm_discard(self):
        if not self.confirm_database_edits():return False
        self.end_stroke()
        if self.stack.isClean():return True
        answer=QMessageBox.question(self,"Unsaved edits","Save your project edits first?",QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Save:return self.save_project()
        return answer==QMessageBox.StandardButton.Discard

    def recover_autosave(self):
        self.open_project(recovery=True)

    def new_project(self):
        if not self.confirm_discard():return
        self.play.setChecked(False)
        # Discard windows that hold selections or snapshots from the old ROM
        # catalog, especially IDs belonging to newly created maps.
        browser=getattr(self,'event_browser',None)
        if browser is not None and browser.inspector is not None:
            browser.inspector.close();browser.inspector.deleteLater()
        for name in ('event_browser','event_inspector','metatile_window','pixel_window','database_window','patch_dialog'):
            widget=getattr(self,name,None)
            if widget is not None:widget.close();widget.deleteLater();delattr(self,name)
        self.tool.setCurrentText('Pencil');self.selection.reset();self.selection.stamp=None
        self.arrival=None;self.brush=0
        self.project=Project(self.project.base_rom);self.area_id=0;self.stack.clear()
        self.last_area={}
        for area in self.project.rom.areas:self.last_area.setdefault(area.layout_id,area.id)
        self.select_area(0)
        self.preset.setCurrentText('Initial');self.frame.setValue(0);self.compare.setChecked(False)
        self.layer_bit.setChecked(False);self.refresh();self.fit_views()
        self.statusBar().showMessage('New project — original ROM, no edits')

    def open_project(self,recovery=False):
        if not self.confirm_discard():return
        name,_=QFileDialog.getOpenFileName(self,"Recover autosave" if recovery else "Open project",str(recovery_directory() if recovery else user_directory()),"FFMQ project (*.json)")
        if not name:return
        try:
            project=Project.load(self.rom,name)
            if recovery:project.path=None
            self.project=project;self.stack.clear();self.area_id=project.area_id
            if recovery:self.stack.resetClean()
            self.areas.blockSignals(True);self.select_area(self.area_id);self.areas.blockSignals(False)
            self.preset.setCurrentText("Custom");self.refresh();self.fit_views()
            if not recovery:
                from .session import remember_project
                remember_project(project)
        except (OSError,ValueError,TypeError) as error:self.error(error)

    def autosave(self):
        if self.stack.isClean() and not self.stroke:return
        if getattr(self,'_recovery_project',None) is not self.project:
            from uuid import uuid4
            self._recovery_project=self.project
            self._recovery_path=recovery_directory()/f'{self.project.path.stem if self.project.path else "Untitled"}-{uuid4().hex[:12]}.autosave.json'
        path=self._recovery_path
        try:self.project.save(path,autosave=True)
        except OSError as error:self.statusBar().showMessage(f"Autosave failed: {error}")

    def export_rom(self):
        if not self.confirm_database_edits():return
        self.end_stroke()
        name,_=QFileDialog.getSaveFileName(self,"Export ROM copy",str(user_directory()/"Mystic Quest edited.sfc"),"SNES ROM (*.sfc)")
        if not name:return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report=self.project.export(Path(name))
            self.statusBar().showMessage(f"Exported {Path(name).name} · {len(report)} resource write(s)")
        except (OSError,ValueError) as error:self.error(error)
        finally:QApplication.restoreOverrideCursor()

    def export_png(self):
        self.play.setChecked(False)
        name,_=QFileDialog.getSaveFileName(self,"Export current frame",str(user_directory()/f"area-{self.area_id:02X}-frame-{self.frame.value()}.png"),"PNG (*.png)")
        if name and not qimage(self.render_area(self.area_id)[0]).save(name):self.error("Could not save PNG")

    def closeEvent(self,event):
        self.play.setChecked(False)
        if self.confirm_discard():event.accept()
        else:event.ignore()

STYLE="""
QMainWindow, QWidget { background: #202730; color: #e2e9f0; }
QMenuBar, QToolBar { background: #29333f; padding: 5px; spacing: 9px; }
QDockWidget::title { background: #303c49; padding: 7px; font-weight: bold; }
QLineEdit, QComboBox { background: #151c24; border: 1px solid #475568; border-radius: 4px; padding: 5px; }
QListWidget, QTableWidget { background: #19212a; border: 1px solid #364353; alternate-background-color: #202b36; }
QListWidget::item { padding: 3px; }
QListWidget::item:selected { background: #355970; color: white; }
QHeaderView::section { background: #303c49; padding: 5px; border: 0px; }
QLabel#heading { font-size: 21px; font-weight: 600; color: #edf6ff; padding-bottom: 5px; }
QPushButton { background: #36566b; padding: 5px 10px; }
QSplitter::handle { background: #303d4c; }
"""

def configure_app(app):
    from .branding import ICON
    from . import __version__
    app.setApplicationName("MysticForge");app.setOrganizationName("MysticForge");app.setApplicationVersion(__version__);app.setWindowIcon(QIcon(str(ICON)))
    # The offscreen Windows plugin may not enumerate system fonts. Load a real
    # local font so screenshots and the live application use the same face.
    font_path=Path("C:/Windows/Fonts/segoeui.ttf")
    if font_path.exists():
        font_id=QFontDatabase.addApplicationFont(str(font_path))
        families=QFontDatabase.applicationFontFamilies(font_id)
        if families:app.setFont(QFont(families[0],10))
    app.setStyle("Fusion");app.setStyleSheet(STYLE)

def main():
    app=QApplication(sys.argv);app.setApplicationName("MysticForge");app.setOrganizationName("MysticForge");configure_app(app)
    from .diagnostics import install
    install()
    from .startup import WelcomeWindow
    window=WelcomeWindow(sys.argv[1] if len(sys.argv)>1 else None)
    window.show()
    # Let Qt display the application before presenting its parented file dialog.
    QTimer.singleShot(100,window.start)
    app.exec()

if __name__=="__main__":main()


