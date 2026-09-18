"""Shared tile properties and a deliberately scoped terrain movement preview."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QFormLayout,QSpinBox,QPushButton,QComboBox,QCheckBox
from .resources import terrain_passage

class PropertyEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window
        box=QVBoxLayout(self);self.point=None;self.copied=None
        title=QLabel('Collision & movement');box.addWidget(title)
        self.mode=QComboBox();self.mode.addItems(['Inspect square','Choose starting square for preview','Paint blocked walking','Pick movement to copy','Paint copied movement']);box.addWidget(self.mode)
        self.mode.currentIndexChanged.connect(lambda _:self.window.tool.setCurrentText('Tile behavior'))
        self.summary=QLabel('Click a map square to inspect its movement rules.');self.summary.setWordWrap(True);box.addWidget(self.summary)
        self.variant=QComboBox();box.addWidget(self.variant)
        self.variant_note=QLabel();self.variant_note.setWordWrap(True);box.addWidget(self.variant_note)
        self.variant.currentIndexChanged.connect(self.describe_variant)
        apply_variant=QPushButton('Use variant on selected square');apply_variant.clicked.connect(self.apply_variant);box.addWidget(apply_variant)
        self.feedback=QLabel();self.feedback.setWordWrap(True);box.addWidget(self.feedback)
        audit=QPushButton('Check unused tile slots…');audit.clicked.connect(self.audit_slots);box.addWidget(audit)
        self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        advanced=QCheckBox('Advanced: edit every use of this tile');box.addWidget(advanced)
        self.advanced=QWidget();advanced_box=QVBoxLayout(self.advanced);self.advanced.hide();advanced.toggled.connect(self.advanced.setVisible);box.addWidget(self.advanced)
        form=QFormLayout();self.tile=QSpinBox();self.tile.setRange(0,127);self.tile.setDisplayIntegerBase(16);form.addRow("Metatile $",self.tile)
        self.level=QSpinBox();self.level.setRange(0,7);form.addRow("Traversal class",self.level)
        self.bridge=QCheckBox("Allow entry from level 1");form.addRow(self.bridge)
        self.raw=[]
        for i in range(2):
            spin=QSpinBox();spin.setRange(0,255);spin.setDisplayIntegerBase(16);spin.setPrefix("$");self.raw.append(spin);form.addRow(f"Property byte {i}",spin)
        self.raw[0].valueChanged.connect(self.decode)
        self.level.valueChanged.connect(self.encode);self.bridge.toggled.connect(self.encode)
        advanced_box.addLayout(form)
        button=QPushButton("Apply shared tile properties");button.clicked.connect(self.commit);advanced_box.addWidget(button)
        self.overlay=QComboBox();self.overlay.addItems(["No traversal overlay","Traversal classes","Terrain check from level 0","Terrain check from level 1","Terrain check from level 2","Terrain check from level 3","Terrain check from level 4","Terrain check from level 5","Terrain check from level 6"])
        box.addWidget(self.overlay);self.overlay.currentIndexChanged.connect(lambda:self.window.refresh_map())
        note=QLabel('Preview: red = terrain gate blocks; green = terrain gate passes; amber = extra behavior or trigger needs inspection. Object markers identify possible additional obstacles. This is not a pathfinding simulation.\n\nPainting changes map cells using existing matching-art variants. Shared layouts still affect other setups. Raw properties and edits to every use of a tile are under Advanced.')
        note.setWordWrap(True);box.addWidget(note);box.addStretch()
        self.tile.valueChanged.connect(lambda:self.refresh())

    def decode(self):
        for widget in (self.level,self.bridge):widget.blockSignals(True)
        self.level.setValue(self.raw[0].value()&7);self.bridge.setChecked(bool(self.raw[0].value()&8))
        for widget in (self.level,self.bridge):widget.blockSignals(False)

    def encode(self):
        self.raw[0].setValue((self.raw[0].value()&0xf0)|self.level.value()|(8 if self.bridge.isChecked() else 0))

    def refresh(self):
        w=self.window
        if getattr(self,'inspected_area',None)!=w.area_id:
            self.inspected_area=w.area_id;self.point=None;self.variant.clear()
            self.summary.setText('Click a map square to inspect its movement rules.');self.feedback.clear()
        tileset=w.project.tileset(w.area_id)
        tile=self.tile.value();self.resource=tileset
        for i,spin in enumerate(self.raw):spin.setValue(w.project.get(("properties",tileset,tile*2+i)))
        self.decode()
        refs=[a.id for a in w.rom.areas if w.project.tileset(a.id)==tileset]
        self.info.setText(f"Shared set ${tileset:02X}, tile ${tile:02X}\nUsed by {len(refs)} areas: "+", ".join(f"{a:02X}" for a in refs))

    def commit(self):
        p=self.window.project;tile=self.tile.value()
        changes={( "properties",self.resource,tile*2+i):(p.get(("properties",self.resource,tile*2+i)),spin.value()) for i,spin in enumerate(self.raw)}
        self.window.commit_changes({k:v for k,v in changes.items() if v[0]!=v[1]},"Edit shared tile behavior")

    def click(self,x,y,pick=False,drag=False):
        from .collision import describe,variants,replacement
        w=self.window;p=w.project;attrs=w.rom.attributes[w.rom.areas[w.area_id].attributes_id]
        if not (0<=x<attrs.width and 0<=y<attrs.height):return
        mode=0 if pick else self.mode.currentIndex()
        if drag and mode not in (2,4):return
        index=w.terrain_source(x,y);cell=w._state.cells[index];tile=cell&127
        props=p.fixed('properties',p.tileset(w.area_id));sources=list(range(128))
        for dest,source in w._state.remaps:sources[dest]=sources[source]
        effective=sources[tile]
        value=props[effective*2]
        if mode==1:
            if value&7==7:self.feedback.setText('Choose a square that permits ordinary walking as the starting level.');return
            self.overlay.setCurrentIndex((value&7)+2);self.feedback.setText(f'Preview uses traversal level {value&7} from ({x}, {y}).');self.mode.setCurrentIndex(0);return
        if mode==3:
            self.copied=value;self.feedback.setText('Copied movement: '+describe(value));self.mode.setCurrentIndex(4);return
        if mode in (2,4):
            if mode==4 and self.copied is None:self.feedback.setText('Pick movement to copy first.');return
            try:
                movement=((value&0xf8)|7) if mode==2 else self.copied
                candidate=replacement(p,w.area_id,tile,movement)
                self.paint(x,y,candidate)
            except ValueError as error:self.feedback.setText(str(error))
            return
        self.tile.setValue(effective);self.refresh();self.point=(w.area_id,x,y)
        self.summary.setText(f'Square ({x}, {y}): '+describe(value)+(' · entrance/script trigger' if props[effective*2+1]&0xe0==0x80 else ''))
        self.variant.clear()
        for candidate in variants(p,w.area_id,tile):
            self.variant.addItem(f'${candidate:02X}: '+describe(props[candidate*2]),candidate)
        self.variant.setToolTip('Variants preserve artwork and property byte 1. Choosing a variant replaces the complete movement byte, including additional behavior bits.')
        if not self.variant.count():self.variant.addItem('No safe existing artwork variants',None)
        self.feedback.setText('Select a variant to change this square, or choose a paint mode. Other cells are not repainted; shared layouts remain shared.')

    def paint(self,x,y,candidate):
        w=self.window;p=w.project;key=w.edit_key(x,y)
        if key is None:raise ValueError('This square is outside the selected editable terrain.')
        attrs=w.rom.attributes[w.rom.areas[w.area_id].attributes_id];index=w.terrain_source(x,y)
        old=p.get(key)
        if old!=w._state.cells[index]:raise ValueError('A story change covers this square. Select that terrain change before painting.')
        from .collision import reserved_remaps
        if old&127 in reserved_remaps(p,w.area_id) or candidate in reserved_remaps(p,w.area_id):raise ValueError('A story tile replacement references this tile; local substitution is not enabled here.')
        props=p.fixed('properties',p.tileset(w.area_id))
        if props[(old&127)*2+1]&0xe0==0x80:raise ValueError('Entrance triggers are edited with Entrances.')
        new=(old&128)|candidate
        if new==old:return
        w.stroke[key]=(w.stroke.get(key,(old,new))[0],new);p.set(key,new)
        w.refresh_map();self.feedback.setText(f'Changed square ({x}, {y}) using existing tile ${candidate:02X}. Undo restores the stroke.')

    def apply_variant(self):
        w=self.window;candidate=self.variant.currentData()
        if self.point is None or self.point[0]!=w.area_id or candidate is None:self.feedback.setText('Inspect a square and select a variant first.');return
        x,y=self.point[1:]
        try:
            from .collision import variants
            index=w.terrain_source(x,y);tile=w._state.cells[index]&127
            if candidate not in variants(w.project,w.area_id,tile):raise ValueError('The square changed; inspect it again.')
            w.end_stroke();self.paint(x,y,candidate);w.end_stroke()
        except ValueError as error:self.feedback.setText(str(error))

    def audit_slots(self):
        from .collision import allocation_audit
        from PySide6.QtWidgets import QMessageBox
        report=allocation_audit(self.window.project,self.window.area_id)
        candidates=', '.join(f'${i:02X}' for i in report['static_candidates']) or 'None'
        local=', '.join(f'${i:02X}' for i in report['absent_from_shared_base_layouts']) or 'None'
        QMessageBox.information(self,'Unused tile investigation',report['scope']+'\n\nAbsent from this set’s shared base layouts (not proof of safety): '+local+'\n\nConservative static candidates: '+candidates+'\nVerified safe to allocate: none\n\n'+'\n'.join(report['blockers']))

    def describe_variant(self):
        candidate=self.variant.currentData()
        if candidate is None:self.variant_note.clear();return
        props=self.window.project.fixed('properties',self.window.project.tileset(self.window.area_id))
        old=props[self.tile.value()*2];new=props[candidate*2]
        self.variant_note.setText(f'Movement byte ${old:02X} → ${new:02X}. '+('This also changes additional behavior bits; test the result in-game.' if (old^new)&0xf0 else 'Other behavior bits are preserved.'))
