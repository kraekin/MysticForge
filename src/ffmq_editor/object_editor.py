"""Inspect, move and place seven-byte field objects within verified capacity."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QListWidget,QLabel,QFormLayout,QSpinBox,QPushButton,QScrollArea,QHBoxLayout,QComboBox,QStackedWidget

# Field encodings verified against the area loader. Unexposed bits survive edits.
FIELDS={"X":(3,0x3f,0),"Y":(2,0x3f,0),"Facing":(3,0xc0,6),
        "Palette":(4,0xe0,5),"Sprite":(6,0x7f,0),"Visibility flag":(0,0xff,0),
        "Behavior index":(4,0x1f,0),"Interaction class":(5,0x18,3),"Interaction ID":(1,0xff,0),
        "Traversal class":(5,7,0),"Pass through":(5,0x20,5),"Push flag":(5,0x40,6)}


def field_changes(project,area_id,index,values):
    area=project.rom.areas[area_id]
    original=project.objects(area_id)[index];edited=bytearray(original)
    for name,value in values.items():
        byte,mask,shift=FIELDS[name]
        maximum=254 if name=="Visibility flag" else 127 if name=="Behavior index" else mask>>shift
        if type(value) is not int or not 0<=value<=maximum:raise ValueError(f"Invalid {name}")
        if name=="Behavior index":
            edited[2]=(edited[2]&63)|((value&96)<<1)
            edited[4]=(edited[4]&224)|(value&31)
        else:edited[byte]=(edited[byte]&(~mask&255))|(value<<shift)
    return {project.object_key(area_id,index,b):(original[b],value)
            for b,value in enumerate(edited) if value!=original[b]}


class ObjectEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.area_id=None
        root=QVBoxLayout(self);self.mode=QComboBox();self.mode.addItems(['Select / move','Place objects']);root.addWidget(self.mode)
        sprites=QPushButton('Map sprites…');root.addWidget(sprites)
        from .sprite_set_editor import open_sprites,open_interactions
        sprites.clicked.connect(lambda:open_sprites(window))
        self.pages=QStackedWidget();root.addWidget(self.pages,1);details=QWidget();self.pages.addWidget(details);box=QVBoxLayout(details)
        self.list=QListWidget();box.addWidget(self.list,1)
        self.list.currentRowChanged.connect(self.show_record)
        self.list.currentRowChanged.connect(self.open_content)
        self.summary=QLabel();self.summary.setWordWrap(True);box.addWidget(self.summary)
        body=QWidget();form=QFormLayout(body);self.fields={}
        for name,(_,mask,shift) in FIELDS.items():
            spin=QSpinBox();spin.setRange(0,254 if name=="Visibility flag" else 127 if name=="Behavior index" else mask>>shift)
            if name in ("Sprite","Visibility flag"):spin.setDisplayIntegerBase(16);spin.setPrefix("$")
            self.fields[name]=spin;form.addRow(name,spin)
        self.fields["Facing"].setToolTip("Stored orientation 0–3; preserves all coordinate bits.")
        self.fields["Sprite"].setToolTip("Index in this area's loaded sprite set. Some slots may be empty.")
        self.fields["Behavior index"].setToolTip("Full 7-bit index assembled by the v1.0 loader from byte 2 bits 6–7 and byte 4 bits 0–4.")
        self.fields["Interaction class"].setToolTip("Stored dispatch class 0–3. Changing a class also requires an appropriate interaction ID and graphics.")
        self.fields["Interaction ID"].setToolTip("Reference consumed by the interaction class; not a direct item ID. Scripts, encounters and chest rewards are separate resources.")
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);box.addWidget(scroll,2)
        self.apply=QPushButton("Apply object changes");box.addWidget(self.apply);self.apply.clicked.connect(self.commit)
        choose_interaction=QPushButton('Choose interaction…');box.addWidget(choose_interaction);choose_interaction.clicked.connect(lambda:open_interactions(self))
        choose_appearance=QPushButton('Choose appearance from palette…');box.addWidget(choose_appearance);choose_appearance.clicked.connect(lambda:self.mode.setCurrentIndex(1))
        content=QPushButton("Open reward / encounter");content.clicked.connect(lambda:self.window.content_editor.open_object(self.selected));box.addWidget(content)
        inspect=QPushButton("Open full inspector…");inspect.clicked.connect(self.inspect);box.addWidget(inspect)
        buttons=QHBoxLayout();self.add=QPushButton("Append copy");self.remove=QPushButton("Remove last")
        buttons.addWidget(self.add);buttons.addWidget(self.remove);box.addLayout(buttons)
        self.add.clicked.connect(self.append_copy);self.remove.clicked.connect(self.remove_last)
        note=QLabel("Expanded mode permits up to 16 stored objects on smaller field maps; larger original lists keep their original limit. Append copies the selected object's interaction and visibility flag—choose these deliberately, since a copied chest/enemy may share persistence. Only tail removal is supported. Overworld landmarks use another format.")
        note.setWordWrap(True);box.addWidget(note)
        from .object_palette import ObjectPalette
        self.palette=ObjectPalette(self);self.pages.addWidget(self.palette)
        self.mode.currentIndexChanged.connect(self.change_mode)

    def change_mode(self,index):
        self.window.end_stroke();self.window._drag_object=-1
        self.window.canvas.object_preview=None;self.window.canvas.viewport().update()
        self.pages.setCurrentIndex(index)
        if index:self.palette.refresh()

    def placing(self):return self.mode.currentIndex()==1

    @property
    def selected(self):return self.list.currentRow()

    def inspect(self):
        from .event_inspector import open_object
        open_object(self.window,self.selected)

    def open_content(self,index):
        if self.placing():return
        if not hasattr(self.window,"content_editor"):return
        objects=self.window.project.objects(self.window.area_id)
        if 0<=index<len(objects) and ((objects[index][5]>>3)&3) in (1,2):
            self.window.content_editor.open_object(index)

    def refresh(self):
        w=self.window;previous=self.selected if self.area_id==w.area_id else -1
        self.area_id=w.area_id
        self.list.blockSignals(True);self.list.clear()
        for i,obj in enumerate(w.project.objects(w.area_id)):
            state="visible" if obj[0] in w.project.flags else "hidden"
            self.list.addItem(f"{i:02X} · sprite ${obj[6]&127:02X} · ({obj[3]&63}, {obj[2]&63}) · {state}")
        self.list.setCurrentRow(previous if previous<self.list.count() else -1)
        self.list.blockSignals(False);self.show_record(self.selected)
        if self.placing():self.palette.refresh()

    def show_record(self,index):
        w=self.window;objects=w.project.objects(w.area_id);valid=0<=index<len(objects)
        area=w.rom.areas[w.area_id];structural=area.offset in w.rom.structural_object_sets
        self.remove.setEnabled(structural and bool(objects))
        self.add.setEnabled(structural and len(objects)<w.project.object_capacity(w.area_id))
        self.add.setText('Append copy' if valid else 'Add object')
        self.apply.setEnabled(valid)
        for spin in self.fields.values():spin.setEnabled(valid)
        if not valid:
            self.summary.setText("Select an object from the list or click its marker with the Objects tool.")
        else:
            area=w.rom.areas[w.area_id];obj=w.project.objects(w.area_id)[index]
            for name,(byte,mask,shift) in FIELDS.items():self.fields[name].setValue(((obj[2]&192)>>1)|(obj[4]&31) if name=="Behavior index" else (obj[byte]&mask)>>shift)
            offset=area.offset+8+index*7;refs=w.rom.object_references.get(offset,[(a.id,index) for a in w.rom.areas if a.offset==area.offset]) if index<len(area.objects) else [(a.id,index) for a in w.rom.areas if a.offset==area.offset]
            location=f"Original record ${offset:06X}" if index<len(area.objects) else "Expanded record"
            self.summary.setText(location+" · shared by areas "+", ".join(f"${a:02X}" for a,_ in refs)+
                                 f"\nRaw: {obj.hex(' ').upper()}\nSlots: {len(objects)}/{w.project.object_capacity(w.area_id)}"+(" · new expanded record" if index>=len(area.objects) else ""))
        if hasattr(w,"render_timer"):w.refresh_map()

    def commit(self):
        w=self.window
        if self.selected<0:return
        attrs=w.rom.attributes[w.rom.areas[w.area_id].attributes_id]
        values={name:spin.value() for name,spin in self.fields.items()}
        if values["X"]>=attrs.width or values["Y"]>=attrs.height:
            w.error("Object coordinates exceed this area's dimensions");return
        changes=field_changes(w.project,w.area_id,self.selected,values)
        w.commit_changes(changes,"Edit object")

    def remove_last(self):
        w=self.window;area=w.rom.areas[w.area_id];count=len(w.project.objects(w.area_id))
        if area.offset not in w.rom.structural_object_sets or not count:return
        w.commit_changes({("object_count",area.offset,0):(count,count-1)},"Remove final object")

    def append_copy(self):
        w=self.window;area=w.rom.areas[w.area_id];objects=w.project.objects(w.area_id);count=len(objects)
        if area.offset not in w.rom.structural_object_sets or count>=w.project.object_capacity(w.area_id):return
        offset=area.offset+8+count*7
        raw=objects[self.selected] if self.selected>=0 else bytes(w.project.get(w.project.object_key(w.area_id,count,i)) for i in range(7))
        changes={w.project.object_key(w.area_id,count,i):(w.project.get(w.project.object_key(w.area_id,count,i)),v) for i,v in enumerate(raw)}
        changes[("object_count",area.offset,0)]=(count,count+1)
        w.commit_changes(changes,"Append object copy");self.list.setCurrentRow(count)
