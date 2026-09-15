"""Shared tile properties and a deliberately scoped terrain movement preview."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QFormLayout,QSpinBox,QPushButton,QComboBox,QCheckBox
from .resources import terrain_passage

class PropertyEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window
        box=QVBoxLayout(self);self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        form=QFormLayout();self.tile=QSpinBox();self.tile.setRange(0,127);self.tile.setDisplayIntegerBase(16);form.addRow("Metatile $",self.tile)
        self.level=QSpinBox();self.level.setRange(0,7);form.addRow("Traversal class",self.level)
        self.bridge=QCheckBox("Allow entry from level 1");form.addRow(self.bridge)
        self.raw=[]
        for i in range(2):
            spin=QSpinBox();spin.setRange(0,255);spin.setDisplayIntegerBase(16);spin.setPrefix("$");self.raw.append(spin);form.addRow(f"Property byte {i}",spin)
        self.raw[0].valueChanged.connect(self.decode)
        self.level.valueChanged.connect(self.encode);self.bridge.toggled.connect(self.encode)
        box.addLayout(form)
        button=QPushButton("Apply shared tile properties");button.clicked.connect(self.commit);box.addWidget(button)
        self.overlay=QComboBox();self.overlay.addItems(["No traversal overlay","Traversal classes","Ordinary step from level 0","Ordinary step from level 1","Ordinary step from level 2","Ordinary step from level 3","Ordinary step from level 4","Ordinary step from level 5","Ordinary step from level 6"])
        box.addWidget(self.overlay);self.overlay.currentIndexChanged.connect(lambda:self.window.refresh_map())
        note=QLabel("Class 0 accepts any level; 1–6 normally require a match; 7 blocks ordinary entry.\n\nGreen passes the terrain gate, red fails. Objects, jumping, tools and scripts are not simulated.\n\nClick terrain with Tile behavior to select its effective property source. Raw bytes expose other behavior without guessed labels.")
        note.setWordWrap(True);box.addWidget(note);box.addStretch()
        self.tile.valueChanged.connect(lambda:self.refresh())

    def decode(self):
        for widget in (self.level,self.bridge):widget.blockSignals(True)
        self.level.setValue(self.raw[0].value()&7);self.bridge.setChecked(bool(self.raw[0].value()&8))
        for widget in (self.level,self.bridge):widget.blockSignals(False)

    def encode(self):
        self.raw[0].setValue((self.raw[0].value()&0xf0)|self.level.value()|(8 if self.bridge.isChecked() else 0))

    def refresh(self):
        w=self.window;tileset=w.project.tileset(w.area_id)
        tile=self.tile.value();self.resource=tileset
        for i,spin in enumerate(self.raw):spin.setValue(w.project.get(("properties",tileset,tile*2+i)))
        self.decode()
        refs=[a.id for a in w.rom.areas if w.project.tileset(a.id)==tileset]
        self.info.setText(f"Shared set ${tileset:02X}, tile ${tile:02X}\nUsed by {len(refs)} areas: "+", ".join(f"{a:02X}" for a in refs))

    def commit(self):
        p=self.window.project;tile=self.tile.value()
        changes={( "properties",self.resource,tile*2+i):(p.get(("properties",self.resource,tile*2+i)),spin.value()) for i,spin in enumerate(self.raw)}
        self.window.commit_changes({k:v for k,v in changes.items() if v[0]!=v[1]},"Edit shared tile behavior")
