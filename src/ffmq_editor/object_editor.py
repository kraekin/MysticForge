"""Inspect, move and place seven-byte field objects within verified capacity."""
from .event_flags import flag_label
from PySide6.QtWidgets import QWidget,QVBoxLayout,QListWidget,QLabel,QFormLayout,QSpinBox,QPushButton,QScrollArea,QHBoxLayout,QComboBox,QStackedWidget,QTabWidget

# Field encodings verified against the area loader. Unexposed bits survive edits.
FIELDS={"X":(3,0x3f,0),"Y":(2,0x3f,0),"Facing":(3,0xc0,6),
        "Palette":(4,0xe0,5),"Sprite":(6,0x7f,0),"Visibility flag":(0,0xff,0),
        "Behavior index":(4,0x1f,0),"Interaction class":(5,0x18,3),"Interaction ID":(1,0xff,0),
        "Traversal class":(5,7,0),"Pass through":(5,0x20,5),"Push flag":(5,0x40,6)}


class ChoiceField(QComboBox):
    """Named choices with the same value interface as the raw property fields."""
    def value(self):return self.currentIndex()
    def setValue(self,value):self.setCurrentIndex(value)


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
        self.list=QListWidget();self.list.setMaximumHeight(125);box.addWidget(self.list)
        self.list.currentRowChanged.connect(self.show_record)
        self.list.currentRowChanged.connect(self.open_content)
        self.summary=QLabel();self.summary.setWordWrap(True);box.addWidget(self.summary)
        self.tabs=QTabWidget();self.tabs.setStyleSheet('QTabBar::tab { padding: 5px 6px; }');box.addWidget(self.tabs,1);forms={}
        for title in ('Appearance','Movement','Interaction','Advanced'):
            page=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page)
            self.tabs.addTab(scroll,{'Appearance':'Looks','Interaction':'Actions'}.get(title,title));forms[title]=QFormLayout(page);forms[title].setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form=forms['Advanced'];self.fields={}
        for name,(_,mask,shift) in FIELDS.items():
            spin=QSpinBox();spin.setRange(0,254 if name=="Visibility flag" else 127 if name=="Behavior index" else mask>>shift)
            if name in ("Sprite","Visibility flag"):spin.setDisplayIntegerBase(16);spin.setPrefix("$")
            group='Appearance' if name in ('X','Y','Facing','Palette') else 'Movement' if name in ('Pass through',) else 'Advanced'
            if name=='Facing':
                spin=ChoiceField();spin.addItems(['Up','Right','Down','Left'])
            elif name=='Palette':
                spin=ChoiceField();spin.addItems([f'Color palette {i}' for i in range(8)])
            elif name=='Pass through':
                spin=ChoiceField();spin.addItems(['Solid object','Player can pass through'])
            elif name=='Behavior index':
                from .object_behavior import ObjectBehavior,PROFILE_BASE,PROFILE_COUNT
                from .rom import pc
                spin=ChoiceField()
                for i in range(128):
                    raw=window.rom.data[pc(PROFILE_BASE)+i*2:pc(PROFILE_BASE)+i*2+2]
                    label=ObjectBehavior(i,raw,0).summary if i<PROFILE_COUNT else 'Unverified profile'
                    spin.addItem(f'{label} · {i}')
                    if i>=PROFILE_COUNT:spin.model().item(i).setEnabled(False)
            if isinstance(spin,QComboBox):
                spin.setMinimumContentsLength(12);spin.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.fields[name]=spin;forms[group].addRow('Sprite and behavior profile' if name=='Behavior index' else name,spin)
        self.visibility_name=QLabel();self.visibility_name.setWordWrap(True);form.addRow('',self.visibility_name)
        self.fields['Visibility flag'].valueChanged.connect(lambda value:self.visibility_name.setText(flag_label(value)))
        self.visibility_name.setText(flag_label(self.fields['Visibility flag'].value()))
        self.fields["Facing"].setToolTip("Initial direction. Scene scripts may turn the object later.")
        self.fields["Sprite"].setToolTip("Index in this area's loaded sprite set. Some slots may be empty.")
        self.fields["Behavior index"].setToolTip("Full 7-bit index assembled by the v1.0 loader from byte 2 bits 6–7 and byte 4 bits 0–4.")
        self.fields["Interaction class"].setToolTip("Stored dispatch class 0–3. Changing a class also requires an appropriate interaction ID and graphics.")
        self.fields["Interaction ID"].setToolTip("Reference consumed by the interaction class; not a direct item ID. Scripts, encounters and chest rewards are separate resources.")
        self.safe_behavior=QComboBox();forms['Movement'].addRow('Movement (matching sprite layout)',self.safe_behavior)
        self.safe_behavior.currentIndexChanged.connect(self.choose_safe_behavior)
        self.behavior_note=QLabel();self.behavior_note.setWordWrap(True);forms['Movement'].addRow(self.behavior_note)
        def explain_behavior():
            from .object_behavior import ObjectBehavior,PROFILE_BASE,PROFILE_COUNT
            from .rom import pc
            index=self.fields['Behavior index'].value()
            self.populate_safe_behaviors(index)
            if index>=PROFILE_COUNT:self.behavior_note.setText('No verified compatible choices for this profile.');return
            raw=window.rom.data[pc(PROFILE_BASE)+index*2:pc(PROFILE_BASE)+index*2+2]
            info=ObjectBehavior(index,raw,self.fields['Facing'].value())
            self.behavior_note.setText('\n'.join(f'{k}: {v}' for k,v in info.fields() if k in ('Movement speed','Animation layout','Sprite position adjustment'))+'\nThese choices preserve the current animation layout and sprite offsets. Scene scripts can override movement. If Stationary is absent, no matching original profile is available. The full list is under Advanced.')
        self.explain_behavior=explain_behavior
        self.fields['Behavior index'].currentIndexChanged.connect(explain_behavior)
        self.technical=QLabel();self.technical.setWordWrap(True);forms['Advanced'].addRow(self.technical)
        self.apply=QPushButton("Apply object changes");box.addWidget(self.apply);self.apply.clicked.connect(self.commit)
        choose_interaction=QPushButton('Choose interaction…');forms['Interaction'].addRow(choose_interaction);choose_interaction.clicked.connect(lambda:open_interactions(self))
        self.dialogue_button=QPushButton('Customize NPC dialogue…');forms['Interaction'].addRow(self.dialogue_button);self.dialogue_button.clicked.connect(self.independent_dialogue)
        self.dialogue_button.setToolTip('Give this NPC its own conversation without changing other NPCs.')
        self.event_button=QPushButton('Customize NPC event…');forms['Interaction'].addRow(self.event_button);self.event_button.clicked.connect(self.custom_event)
        from .story_scene_editor import open_scene
        self.scene_button=QPushButton('Edit axe scene movement…');forms['Interaction'].addRow(self.scene_button);self.scene_button.clicked.connect(lambda:open_scene(window))
        choose_appearance=QPushButton('Choose appearance from palette…');forms['Appearance'].addRow(choose_appearance);choose_appearance.clicked.connect(lambda:self.mode.setCurrentIndex(1))
        content=QPushButton("Open reward / encounter");content.clicked.connect(lambda:self.window.content_editor.open_object(self.selected));forms['Interaction'].addRow(content)
        inspect=QPushButton("Open full inspector…");inspect.clicked.connect(self.inspect);forms['Advanced'].addRow(inspect)
        buttons=QHBoxLayout();self.add=QPushButton("Append copy");self.remove=QPushButton("Remove last")
        buttons.addWidget(self.add);buttons.addWidget(self.remove);box.addLayout(buttons)
        self.add.clicked.connect(self.append_copy);self.remove.clicked.connect(self.remove_last)
        note=QLabel("Expanded mode permits up to 16 stored objects on smaller field maps; larger original lists keep their original limit. Append copies the selected object's interaction and visibility flag—choose these deliberately, since a copied chest/enemy may share persistence. Only tail removal is supported. Overworld landmarks use another format.")
        note.setWordWrap(True);forms['Advanced'].addRow(note)
        from .object_palette import ObjectPalette
        self.palette=ObjectPalette(self);self.pages.addWidget(self.palette)
        self.mode.currentIndexChanged.connect(self.change_mode)

    def populate_safe_behaviors(self,index):
        from .object_behavior import compatible_profiles
        self.safe_behavior.blockSignals(True);self.safe_behavior.clear()
        for profile in compatible_profiles(self.window.rom,index):
            speed=(1,2,4,4)[profile.raw[0]>>6]
            self.safe_behavior.addItem(f'{profile.summary} · speed {speed} · profile {profile.index}',profile.index)
        self.safe_behavior.setCurrentIndex(self.safe_behavior.findData(index))
        self.safe_behavior.setEnabled(self.selected>=0 and self.safe_behavior.count()>1)
        self.safe_behavior.blockSignals(False)

    def choose_safe_behavior(self,index):
        value=self.safe_behavior.itemData(index)
        if value is not None:self.fields['Behavior index'].setValue(value)

    def change_mode(self,index):
        self.window.end_stroke();self.window._drag_object=-1
        self.window.canvas.object_preview=None;self.window.canvas.viewport().update()
        self.pages.setCurrentIndex(index)
        if index:self.palette.refresh()

    def custom_event(self):
        from .custom_event_editor import show_event_editor
        show_event_editor(self.window,self.window.area_id,self.selected)

    def independent_dialogue(self):
        from .private_dialogue_editor import show_dialogue
        show_dialogue(self.window,self.window.area_id,self.selected)

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
        self.scene_button.setVisible(w.area_id==16 and index in (1,5))
        npc=valid and ((objects[index][5]>>3)&3)==0
        custom=npc and objects[index][1] in w.project.private_dialogues
        self.event_button.setEnabled(npc)
        structured=custom and 'actions' in w.project.private_dialogues[objects[index][1]]
        self.event_button.setText('Edit NPC event…' if structured else 'Customize NPC event…')
        self.dialogue_button.setEnabled(npc and not structured)
        self.dialogue_button.setToolTip('Use Edit NPC event to change dialogue within its action list.' if structured else 'Give this NPC its own conversation without changing other NPCs.')
        self.dialogue_button.setText('Edit NPC dialogue…' if custom else 'Customize NPC dialogue…')
        for spin in self.fields.values():spin.setEnabled(valid)
        if not valid:
            self.safe_behavior.setEnabled(False)
            self.summary.setText("Select an object from the list or click its marker with the Objects tool.")
        else:
            area=w.rom.areas[w.area_id];obj=w.project.objects(w.area_id)[index]
            for name,(byte,mask,shift) in FIELDS.items():self.fields[name].setValue(((obj[2]&192)>>1)|(obj[4]&31) if name=="Behavior index" else (obj[byte]&mask)>>shift)
            self.explain_behavior()
            from PySide6.QtGui import QIcon
            from PySide6.QtCore import QSize
            self.fields['Palette'].setIconSize(QSize(48,48))
            for color in range(8):
                preview=bytearray(obj);preview[4]=(preview[4]&31)|(color<<5)
                self.fields['Palette'].setItemIcon(color,QIcon(self.palette.preview(preview)))
            offset=area.offset+8+index*7;refs=w.rom.object_references.get(offset,[(a.id,index) for a in w.rom.areas if a.offset==area.offset]) if index<len(area.objects) else [(a.id,index) for a in w.rom.areas if a.offset==area.offset]
            location=f"Original record ${offset:06X}" if index<len(area.objects) else "Expanded record"
            self.technical.setText(location+" · shared by areas "+", ".join(f"${a:02X}" for a,_ in refs)+
                                 f"\nRaw: {obj.hex(' ').upper()}\nSlots: {len(objects)}/{w.project.object_capacity(w.area_id)}"+(" · new expanded record" if index>=len(area.objects) else ""))
            kind=('NPC','Encounter','Chest / reward','Special interaction')[(obj[5]>>3)&3]
            self.summary.setText(f'{kind} · object {index:02X} · {len(objects)}/{w.project.object_capacity(w.area_id)} slots used'+(f' · shared by {len(refs)} area records' if len(refs)>1 else ''))
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
