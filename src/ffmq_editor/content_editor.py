"""Shared treasure rewards, encounter groups and formation members."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,QComboBox,QCheckBox,QPushButton,QTabWidget,QFormLayout,QScrollArea
from .rom import pc,read
from .resources import changes

ITEM_NAMES=("Elixir","Tree Wither","Wakewater","Venus Key","Multi Key","Mask","Magic Mirror","Thunder Rock","Captain's Cap","Libra Crest","Gemini Crest","Mobius Crest","Sand Coin","River Coin","Sun Coin","Sky Coin","Cure Potion","Heal Potion","Seed","Refresher","Exit Book","Cure Book","Heal Book","Life Book","Quake Book","Blizzard Book","Fire Book","Aero Book","Thunder Seal","White Seal","Meteor Seal","Flare Seal","Steel Sword","Knight Sword","Excalibur","Axe","Battle Axe","Giant's Axe","Cat Claw","Charm Claw","Dragon Claw","Bomb","Jumbo Bomb","Mega Grenade","Morning Star","Bow of Grace","Ninja Star","Steel Helm","Moon Helm","Apollo Helm","Steel Armor","Noble Armor","Gaia's Armor","Replica Armor","Mystic Robes","Flame Armor","Black Robe","Steel Shield","Venus Shield","Aegis Shield","Ether Shield","Charm","Magic Ring","Cupid Locket")

def enemy_name(rom,index):
    from .database import name
    raw=rom.fixed('monster_name',index) if hasattr(rom,'fixed') else read(rom.data,pc(0x0CCBA0)+index*16,16)
    return name(raw)

class ContentEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window
        outer=QVBoxLayout(self);self.tabs=QTabWidget();outer.addWidget(self.tabs)
        self.info=QLabel();self.info.setWordWrap(True);outer.addWidget(self.info)
        reward=QWidget();box=QVBoxLayout(reward);self.tabs.addTab(reward,"Chest rewards")
        self.treasure=QSpinBox();self.treasure.setRange(0,250);self.treasure.setDisplayIntegerBase(16);self.treasure.setPrefix("Reward ID $");box.addWidget(self.treasure)
        self.item=QComboBox()
        for i,name in enumerate(ITEM_NAMES):self.item.addItem(f"${i:02X} · {name}",i)
        self.item.addItem("$DD · Bomb refill",0xdd);self.item.addItem("$DE · Projectile refill",0xde);box.addWidget(self.item)
        button=QPushButton("Apply shared reward");button.clicked.connect(self.commit_reward);box.addWidget(button)
        note=QLabel("The object interaction ID selects this reward. Amounts, refill type, opening animation and persistence are controlled by the game's scripts. Shared IDs change together.");note.setWordWrap(True);box.addWidget(note);box.addStretch()
        body=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);self.tabs.addTab(scroll,"Encounters");box=QVBoxLayout(body)
        self.encounter_scroll=scroll
        self.encounter=QSpinBox();self.encounter.setRange(0,206);self.encounter.setPrefix("Encounter $");self.encounter.setDisplayIntegerBase(16);box.addWidget(self.encounter)
        note=QLabel("Each battle selects one of these three variants. Editing one lineup leaves the other variants available. Choose Edit beside a lineup, or use the same formation for all variants below.");note.setWordWrap(True);box.addWidget(note)
        self.variants=[];self.variant_names=[];form=QFormLayout()
        for i in range(3):
            spin=QSpinBox();spin.setRange(0,233);spin.setDisplayIntegerBase(16);self.variants.append(spin)
            row=QWidget();line=QHBoxLayout(row);line.setContentsMargins(0,0,0,0);line.addWidget(spin)
            button=QPushButton("Edit lineup");button.clicked.connect(lambda checked=False,s=spin:self.edit_variant(s.value()));line.addWidget(button)
            form.addRow(f"Variant {i+1} · ID $",row)
            label=QLabel();label.setWordWrap(True);self.variant_names.append(label);form.addRow(label)
            spin.valueChanged.connect(self.update_variant_names)
        box.addLayout(form);button=QPushButton("Apply shared encounter");button.clicked.connect(self.commit_encounter);box.addWidget(button)
        self.formation=QSpinBox();self.formation.setRange(0,233);self.formation.setPrefix("Inspect/edit formation $");self.formation.setDisplayIntegerBase(16);box.addWidget(self.formation)
        self.formation_scope=QLabel();self.formation_scope.setWordWrap(True);box.addWidget(self.formation_scope)
        self.enemies=[];self.high=[]
        for i in range(3):
            line=QHBoxLayout();combo=QComboBox();combo.addItem("Empty",255)
            for enemy in range(81):combo.addItem(f"${enemy:02X} · {enemy_name(window.project,enemy)}",enemy)
            check=QCheckBox("Bit 7");check.setToolTip("Per-slot high flag loaded separately by the battle engine; preserve it unless intentionally changing it.")
            line.addWidget(combo);line.addWidget(check);self.enemies.append(combo);self.high.append(check);box.addLayout(line)
        self.settings=QSpinBox();self.settings.setRange(0,255);self.settings.setDisplayIntegerBase(16);self.settings.setPrefix("Raw formation settings $");box.addWidget(self.settings)
        advanced=QCheckBox("Show advanced formation flags");box.addWidget(advanced)
        for control in [*self.high,self.settings]:
            control.setVisible(False);advanced.toggled.connect(control.setVisible)
        button=QPushButton("Apply shared formation");button.clicked.connect(self.commit_formation);box.addWidget(button)
        button=QPushButton("Use this formation for all variants");button.clicked.connect(self.use_for_all);box.addWidget(button)
        note=QLabel("Enemy objects select an encounter group. The game selects one of its three formations. Each formation has three enemy slots and a settings byte. Sprite artwork on the field is a separate object setting.");note.setWordWrap(True);box.addWidget(note);box.addStretch()
        self.treasure.valueChanged.connect(self.refresh);self.encounter.valueChanged.connect(self.refresh);self.formation.valueChanged.connect(self.refresh);self.tabs.currentChanged.connect(self.refresh)

    def update_variant_names(self):
        from collections import Counter
        for spin,label in zip(self.variants,self.variant_names):
            raw=self.window.project.fixed("formation",spin.value())
            counts=Counter(enemy_name(self.window.project,v&127) for v in raw[:3] if v!=255)
            label.setText(" + ".join(f"{count} × {name}" for name,count in counts.items()) or "Empty")

    def edit_variant(self,formation):
        self.formation.setValue(formation)
        self.encounter_scroll.ensureWidgetVisible(self.enemies[-1],0,70)
        self.enemies[0].setFocus()

    def use_for_all(self):
        raw=self.edited_formation()
        if all(v==255 for v in raw[:3]):self.window.error("A formation needs at least one enemy");return
        edits=changes(self.window.project,"formation",self.formation.value(),raw)
        edits.update(changes(self.window.project,"encounter",self.encounter.value(),bytes([self.formation.value()])*3))
        self.window.commit_changes(edits,"Use one formation for all encounter variants")

    def refresh(self):
        p=self.window.project
        # Terrain painting, preview flags and selection do not change these
        # tables or references. Include sparse values so undo/redo invalidates too.
        kinds={'monster_name','treasure','encounter','formation','object','extra_object','object_count'}
        signature=(id(p),id(p.rom),tuple(sorted((k,v) for k,v in p.edits.items() if k[0] in kinds)),
                   self.treasure.value(),self.encounter.value(),self.formation.value(),self.tabs.currentIndex())
        if getattr(self,'_refresh_signature',None)==signature:return
        names=tuple(enemy_name(p,i) for i in range(81))
        for combo in self.enemies:
            for i in range(81):combo.setItemText(i+1,f'${i:02X} · {names[i]}')
        p=self.window.project
        self.item.setCurrentIndex(self.item.findData(p.fixed("treasure",self.treasure.value())[0]))
        for spin,value in zip(self.variants,p.fixed("encounter",self.encounter.value())):
            spin.blockSignals(True);spin.setValue(value);spin.blockSignals(False)
        raw=p.fixed("formation",self.formation.value())
        for combo,check,value in zip(self.enemies,self.high,raw):combo.setCurrentIndex(combo.findData(255 if value==255 else value&127));check.setChecked(value!=255 and bool(value&128))
        self.settings.setValue(raw[3])
        self.update_variant_names()
        users=[i for i in range(207) if self.formation.value() in p.fixed("encounter",i)]
        self.formation_scope.setText("This lineup is shared by "+str(len(users))+" encounter group(s). Changing its enemies affects those groups too. Use for all variants also applies your lineup edits. Field sprites are edited separately.")
        kind=2 if self.tabs.currentIndex()==0 else 1;resource=self.treasure.value() if kind==2 else self.encounter.value()
        refs=[f"{a.id:02X}/{i:02X}" for a in p.rom.areas for i,obj in enumerate(p.objects(a.id)) if ((obj[5]>>3)&3)==kind and obj[1]==resource]
        self.info.setText("Object uses (area/object): "+(", ".join(refs) or "none")+". Scripts and battlefields may also use this resource.")

        self._refresh_signature=signature

    def open_object(self,index):
        objects=self.window.project.objects(self.window.area_id)
        if not 0<=index<len(objects):return
        obj=objects[index];kind=(obj[5]>>3)&3
        if kind==2 and obj[1]<251:self.tabs.setCurrentIndex(0);self.treasure.setValue(obj[1])
        elif kind==1 and obj[1]<207:
            self.tabs.setCurrentIndex(1);self.encounter.setValue(obj[1]);self.formation.setValue(self.window.project.fixed("encounter",obj[1])[0])
        else:self.window.statusBar().showMessage("This object uses a script or unsupported reference; no reward/encounter was guessed.");return
        self.refresh();self.window.content_dock.show();self.window.content_dock.raise_()

    def commit_reward(self):
        if self.item.currentData() is not None:self.window.commit_changes(changes(self.window.project,"treasure",self.treasure.value(),bytes([self.item.currentData()])),"Edit shared chest reward")

    def commit_encounter(self):
        self.window.commit_changes(changes(self.window.project,"encounter",self.encounter.value(),bytes(s.value() for s in self.variants)),"Edit encounter formations")

    def edited_formation(self):
        return bytes([255 if c.currentData()==255 else c.currentData()|(128 if h.isChecked() else 0) for c,h in zip(self.enemies,self.high)]+[self.settings.value()])

    def commit_formation(self):
        raw=self.edited_formation()
        if all(v==255 for v in raw[:3]):self.window.error("A formation needs at least one enemy");return
        self.window.commit_changes(changes(self.window.project,"formation",self.formation.value(),raw),"Edit formation enemies")
