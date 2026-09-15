"""Route and condition editing without reallocating route streams."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,QComboBox,QCheckBox,QPushButton,QTableWidget,QScrollArea
from .world import DIRECTIONS,points,position,gate,available,validate
from .resources import changes

class WorldEditor(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.loading=False
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();scroll.setWidget(body);outer.addWidget(scroll);box=QVBoxLayout(body)
        self.node=QSpinBox();self.node.setRange(1,56);self.node.setPrefix("Node $");self.node.setDisplayIntegerBase(16);self.node.setValue(0x16)
        self.direction=QComboBox();self.direction.addItems(DIRECTIONS)
        box.addWidget(self.node);box.addWidget(self.direction)
        self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        line=QHBoxLayout();line.addWidget(QLabel("Destination node"));self.destination=QSpinBox();self.destination.setRange(0,56);self.destination.setDisplayIntegerBase(16);line.addWidget(self.destination);box.addLayout(line)
        line=QHBoxLayout();line.addWidget(QLabel("Required flag $"));self.flag=QSpinBox();self.flag.setRange(0,255);self.flag.setDisplayIntegerBase(16);line.addWidget(self.flag);box.addLayout(line)
        self.preview=QCheckBox("Flag set in preview");box.addWidget(self.preview)
        self.steps=QTableWidget(0,2);self.steps.setHorizontalHeaderLabels(["Step direction","Tiles (1–31)"]);self.steps.setMinimumHeight(180);box.addWidget(self.steps)
        apply=QPushButton("Apply route and condition");apply.clicked.connect(self.commit);box.addWidget(apply)
        self.overlay=QCheckBox("Show routes on overworld");self.overlay.setChecked(True);box.addWidget(self.overlay)
        follow=QPushButton("Select destination node");follow.clicked.connect(lambda:self.node.setValue(self.destination.value() or self.node.value()));box.addWidget(follow)
        note=QLabel("Green: flag allows route. Gray: locked or disabled. Cyan: selected route.\n\nFlag 0 disables the direction. Segment count stays within its original span. Endpoint must match the destination; reverse routes are separate. Ship travel and scripted movement are separate resources.");note.setWordWrap(True);box.addWidget(note);box.addStretch()
        for control in (self.node,self.direction):
            (control.valueChanged if control is self.node else control.currentIndexChanged).connect(self.selected)
        self.flag.valueChanged.connect(self.flag_changed);self.preview.toggled.connect(self.preview_changed);self.overlay.toggled.connect(lambda:self.window.refresh_map())

    def route(self):return self.window.rom.routes[(self.node.value()-1)*4+self.direction.currentIndex()]

    def selected(self):
        self.refresh()
        if hasattr(self.window,"render_timer"):
            self.window.refresh_map();x,y=position(self.window.project,self.node.value());self.window.canvas.centerOn(x*16+8,y*16+8)

    def flag_changed(self):
        self.preview.blockSignals(True);self.preview.setChecked(self.flag.value() in self.window.project.flags);self.preview.setEnabled(self.flag.value()!=0);self.preview.blockSignals(False)

    def preview_changed(self,enabled):
        if self.loading or not self.flag.value():return
        flags=self.window.project.flags
        (flags.add if enabled else flags.discard)(self.flag.value())
        self.window.refresh()

    def refresh(self):
        self.loading=True
        try:
            p=self.window.project;r=self.route();raw=p.fixed("world_route",r.offset)
            self.destination.setValue(raw[0]);self.flag.setValue(gate(p,r));self.flag_changed()
            end=points(p,r)[-1];refs=[f"{x.node:02X}/{DIRECTIONS[x.direction]}" for x in p.rom.routes if x.offset==r.offset]
            self.info.setText(f"ROM ${r.offset:06X} · {len(raw)-1} segments\nStart {position(p,r.node)} → end {end}\n"+("Available" if available(p,r) else "Locked/disabled")+" · shared by "+", ".join(refs))
            self.steps.setRowCount(len(raw)-1)
            for i,step in enumerate(raw[1:]):
                direction=QComboBox();direction.addItems(DIRECTIONS);direction.setCurrentIndex((step>>5)&3)
                length=QSpinBox();length.setRange(1,31);length.setValue(step&31)
                self.steps.setCellWidget(i,0,direction);self.steps.setCellWidget(i,1,length)
            self.steps.resizeColumnsToContents()
        finally:self.loading=False

    def commit(self):
        p=self.window.project;r=self.route()
        raw=bytes([self.destination.value()]+[128|(self.steps.cellWidget(i,0).currentIndex()<<5)|self.steps.cellWidget(i,1).value() for i in range(self.steps.rowCount())])
        try:validate(p,r,raw)
        except ValueError as error:self.window.error(error);return
        edits=changes(p,"world_route",r.offset,raw)
        key=("world_gate",r.node,r.direction);old=p.get(key)
        if old!=self.flag.value():edits[key]=(old,self.flag.value())
        self.window.commit_changes(edits,"Edit overworld route")
