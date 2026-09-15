"""Connection navigation panel."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QAbstractItemView,QPushButton,QHBoxLayout,QSpinBox,QTabWidget,QScrollArea
from .rom import pc
from .resources import changes

class ConnectionPanel(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.entries=();self.area=None
        outer=QVBoxLayout(self);self.tabs=QTabWidget();outer.addWidget(self.tabs)
        browse=QWidget();self.tabs.addTab(browse,"Connections");box=QVBoxLayout(browse)
        note=QLabel("Shared destination editing. Terrain properties select the action; coordinate records select its ID. Scripts and progression can redirect gameplay.")
        note.setWordWrap(True);box.addWidget(note)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(["Source X,Y","Action / ID","Destination","Details"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True);box.addWidget(self.table)
        self.move_button=QPushButton("Move selected entrance on map");self.move_button.setCheckable(True);box.addWidget(self.move_button)
        self.move_button.toggled.connect(self.arm_move)
        self.move_note=QLabel("Drag an entrance marker to its new tile, or use Move and click. The doorway tile swaps with the target tile. Adjust the house artwork separately; check its return arrival too.");self.move_note.setWordWrap(True);box.addWidget(self.move_note)
        self.move_feedback=QLabel();self.move_feedback.setWordWrap(True);box.addWidget(self.move_feedback)
        self.table.itemSelectionChanged.connect(self.locate)
        self.table.cellDoubleClicked.connect(lambda *_:self.follow())
        button=QPushButton("Go to selected destination");button.clicked.connect(self.follow);box.addWidget(button)
        inspect=QPushButton("Open full inspector…");inspect.clicked.connect(self.inspect);box.addWidget(inspect)
        content=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content)
        self.tabs.addTab(scroll,"Edit selected connection");box=QVBoxLayout(content)
        self.scope=QLabel("Select a transition to edit its shared destination.");self.scope.setWordWrap(True);box.addWidget(self.scope)
        form=QHBoxLayout();self.fields={}
        for name,maximum in (("Area",107),("X",63),("Y",63),("Facing",3)):
            form.addWidget(QLabel(name));spin=QSpinBox();spin.setRange(0,maximum);self.fields[name]=spin;form.addWidget(spin)
        self.apply=QPushButton("Apply shared destination");form.addWidget(self.apply);self.apply.clicked.connect(self.commit_destination);box.addLayout(form)
        line=QHBoxLayout();self.source_fields={}
        for name,maximum in (("Source X",63),("Source Y",63),("Destination ID",255)):
            line.addWidget(QLabel(name));spin=QSpinBox();spin.setRange(0,maximum);self.source_fields[name]=spin;line.addWidget(spin)
        self.source_apply=QPushButton("Apply source record");line.addWidget(self.source_apply);self.source_apply.clicked.connect(self.commit_source);box.addLayout(line)
        self.incoming=QPushButton("Find references to selected destination");self.incoming.clicked.connect(self.find_references);box.addWidget(self.incoming)
        box.addStretch();self.selected_key=None;self.update_form()

    def update_entries(self,entries):
        if entries==self.entries and self.area==self.window.area_id:return
        self.move_button.setChecked(False)
        self.entries=entries;self.area=self.window.area_id
        row_before=self.table.currentRow()
        self.table.blockSignals(True);self.table.setRowCount(len(entries))
        for row,entry in enumerate(entries):
            if entry.target:
                area,x,y,facing=entry.target
                target=f"${area:02X} {self.window.rom.areas[area].name} · ({x},{y})"
            else:target="Runtime/script destination" if entry.action==3 else "Unresolved"
            detail=entry.label+(f" · ROM ${entry.source:06X}" if entry.source is not None else "")
            for col,text in enumerate((f"E{row:X} · {entry.x},{entry.y}",f"${entry.action:02X} / ${entry.value:02X}",target,detail)):
                item=QTableWidgetItem(text);item.setToolTip(text);self.table.setItem(row,col,item)
        self.table.resizeColumnsToContents();self.table.blockSignals(False)
        if 0<=row_before<len(entries):self.table.selectRow(row_before)
        self.update_form()

    def locate(self):
        self.update_form()
        row=self.table.currentRow()
        if not 0<=row<len(self.entries):return
        entry=self.entries[row]
        if not getattr(self,"selecting_on_canvas",False):self.window.canvas.centerOn(entry.x*16+8,entry.y*16+8)

    def inspect(self):
        from .event_inspector import open_connection
        open_connection(self.window)

    def entry(self):
        row=self.table.currentRow()
        return self.entries[row] if 0<=row<len(self.entries) else None

    def destination_key(self,entry):
        if entry is None or entry.action not in self.window.connections.TABLES:return None
        base,count,size=self.window.connections.TABLES[entry.action]
        return pc(base)+entry.value*size if 0<=entry.value<count else None

    def update_form(self):
        entry=self.entry();self.selected_key=self.destination_key(entry)
        self.move_button.setEnabled(bool(entry and not entry.label.startswith("World node") and (entry.action==3 or entry.source in self.window.rom.coordinate_offsets)))
        valid=self.selected_key is not None
        self.apply.setEnabled(valid);self.incoming.setEnabled(valid)
        for spin in self.fields.values():spin.setEnabled(valid)
        if valid:
            raw=self.window.project.fixed("destination",self.selected_key);area,y,x=raw[-3:]
            for name,value in (("Area",area),("X",x&63),("Y",y),("Facing",x>>6)):self.fields[name].setValue(value)
            self.scope.setText(f"Shared destination at ROM ${self.selected_key:06X}. All exits using this record change together. Use Find references to list current-preview uses."+(" Long-form runtime byte is preserved." if len(raw)==4 else ""))
        elif entry and entry.action==8 and entry.target:
            self.scope.setText("Scripted entry: the destination shown follows the current preview flags. Script editing is not enabled; this is not a direct destination record.")
        else:self.scope.setText("Runtime/script return; no static destination is editable.")
        field_source=bool(entry and entry.source in self.window.rom.coordinate_offsets and entry.action in self.window.connections.TABLES)
        world_source=bool(entry and entry.label.startswith("World node") and valid)
        self.source_apply.setEnabled(field_source or world_source)
        for name,spin in self.source_fields.items():spin.setEnabled(field_source or (world_source and name=="Destination ID"))
        if entry:
            for name,value in (("Source X",entry.x),("Source Y",entry.y),("Destination ID",entry.value)):self.source_fields[name].setValue(value)

    def arm_move(self,enabled):
        if enabled:
            self.window.tool.setCurrentText('Entrances')
            self.window.statusBar().showMessage('Click the new entrance tile. Click Move again to cancel. The two terrain tiles will swap.')

    def move_to(self,x,y):
        entry=self.entry()
        if entry is None:return
        w=self.window
        try:
            edits=entrance_move_changes(w,entry,x,y)
        except ValueError as error:
            w.error(str(error));return
        self.move_button.setChecked(False)
        w.commit_changes(edits,'Move entrance and trigger tile')
        for row,e in enumerate(self.entries):
            if (e.x,e.y)==(x,y):self.table.selectRow(row);break
        w.statusBar().showMessage('Entrance moved; target terrain was swapped into the old position. Check Shared terrain uses and the return arrival from inside the house.')

    def commit_destination(self):
        if self.selected_key is None:return
        w=self.window;v={name:s.value() for name,s in self.fields.items()};attrs=w.rom.attributes[w.rom.areas[v["Area"]].attributes_id]
        if v["X"]>=attrs.width or v["Y"]>=attrs.height:w.error("Arrival coordinates exceed the destination map");return
        raw=bytearray(w.project.fixed("destination",self.selected_key));raw[-3:]=bytes((v["Area"],v["Y"],v["X"]|(v["Facing"]<<6)))
        w.commit_changes(changes(w.project,"destination",self.selected_key,raw),"Edit shared exit destination")

    def commit_source(self):
        entry=self.entry()
        if not entry:return
        w=self.window;value=self.source_fields["Destination ID"].value()
        if entry.action not in w.connections.TABLES or value>=w.connections.TABLES[entry.action][1]:w.error("Destination ID is outside this action's table");return
        if entry.label.startswith("World node"):
            node=(entry.source-pc(0x07EFCB))//2+0x16
            w.commit_changes(changes(w.project,"world_action",node,bytes((value,entry.action))),"Change overworld location link");return
        if entry.source not in w.rom.coordinate_offsets:return
        x=self.source_fields["Source X"].value();y=self.source_fields["Source Y"].value()
        attrs=w.rom.attributes[w.rom.areas[w.area_id].attributes_id]
        if x>=attrs.width or y>=attrs.height:w.error("Source coordinates exceed this map");return
        # The engine chooses the first matching coordinate, so reject ambiguity.
        if any(e.source!=entry.source and (e.x,e.y)==(x,y) for e in self.entries):w.error("Another transition already uses these coordinates");return
        w.commit_changes(changes(w.project,"coordinate",entry.source,bytes((x,y,value))),"Edit shared exit coordinate record")
        w.statusBar().showMessage("Coordinate record updated. Source terrain must carry the intended trigger property; shared coordinate uses also change.")

    def find_references(self):
        if self.selected_key is None:return
        w=self.window;found=[]
        for area in w.rom.areas:
            _,props,state=w.renderer.metatiles(w.project,area.id)
            for entry in w.connections.for_area(area.id,state,props):
                if self.destination_key(entry)==self.selected_key:found.append(f"${area.id:02X} ({entry.x},{entry.y})")
        self.scope.setText(f"ROM ${self.selected_key:06X} · Current-preview references: "+(", ".join(found) or "none")+". Other story states/scripts can add references.")

    def follow(self):
        row=self.table.currentRow()
        if not 0<=row<len(self.entries):return
        entry=self.entries[row]
        if entry.target is None:
            self.window.statusBar().showMessage("This destination needs runtime/script context; no destination has been guessed.");return
        area,x,y,facing=entry.target;w=self.window
        w.select_area(area);w.arrival=(area,x,y)
        w.canvas.centerOn(x*16+8,y*16+8);w.refresh_map()
        w.statusBar().showMessage(f"Arrival at area ${area:02X}, ({x},{y}), facing {facing}. Preview flags are unchanged.")


def entrance_move_changes(w,entry,x,y):
    """Atomic base-terrain swap plus coordinate lookup move; never changes destinations."""
    area=w.rom.areas[w.area_id];attrs=w.rom.attributes[area.attributes_id]
    if area.layout_id==0:raise ValueError('Move overworld nodes with the Routes editor.')
    if not (0<=x<attrs.width and 0<=y<attrs.height):raise ValueError('New entrance is outside this map.')
    if (x,y)==(entry.x,entry.y):return {}
    if w.target.currentData()!=('layout',area.layout_id):raise ValueError('Choose Base terrain before moving an entrance.')
    points=((entry.x,entry.y),(x,y))
    for px,py in points:
        if w.terrain_source(px,py)!=py*attrs.width+px:raise ValueError('This position uses shifted terrain. Entrance movement here needs separate layer handling.')
        for action in w._state.applied:
            if action.opcode==0x22:
                patch=w.rom.changes[action.value]
                if patch.x<=px<patch.x+patch.width and patch.y<=py<patch.y+patch.height:raise ValueError('An active state change covers this position. Preview a state without that replacement before moving the base entrance.')
    _,props,state=w.renderer.metatiles(w.project,w.area_id)
    target_cell=state.cells[y*attrs.width+x]
    if int(props[target_cell&127,1])&0xE0==0x80:raise ValueError('The target already has a transition trigger. Choose an ordinary terrain tile.')
    if entry.action!=3 and entry.source not in w.rom.coordinate_offsets:raise ValueError('This entrance has no editable coordinate record.')
    # Include inactive coordinate records and fallback records, not only visible triggers.
    cursor=pc(0x05F9F8)+int.from_bytes(w.rom.data[pc(0x05F920)+w.area_id*2:pc(0x05F920)+w.area_id*2+2],'little')
    while cursor+3<=pc(0x05FFFF)+1:
        raw=w.project.fixed('coordinate',cursor) if cursor in w.rom.coordinate_offsets else w.rom.data[cursor:cursor+3]
        rx,ry,_=raw
        if ry&128:break
        if cursor!=entry.source and (rx,ry)==(x,y):raise ValueError('Another coordinate record already uses this tile, including possible inactive entrances.')
        cursor+=3
    raw=bytearray(w.project.resource('layout',area.layout_id));a=entry.y*attrs.width+entry.x;b=y*attrs.width+x
    raw[a],raw[b]=raw[b],raw[a]
    edits=changes(w.project,'layout',area.layout_id,raw)
    if entry.action!=3:edits.update(changes(w.project,'coordinate',entry.source,bytes((x,y,entry.value))))
    return edits
