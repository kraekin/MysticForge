"""Visible setup choices and the evidence behind their names."""
from html import escape
from PySide6.QtCore import Qt,QRectF,QSize
from PySide6.QtWidgets import (QWidget,QToolButton,QDialog,QVBoxLayout,QHBoxLayout,
    QLabel,QPushButton,QTabWidget,QTextBrowser,QTreeWidget,QTreeWidgetItem,QApplication,QLineEdit,QPlainTextEdit,QSizePolicy)
from .map_setups import info,audit,catalogue

class SetupButtons(QWidget):
    """Compact, content-sized buttons that wrap without hiding any choices."""
    def __init__(self,w):
        super().__init__();self.w=w;self.buttons={};self.signature=None
        self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setFixedHeight(26)
    def sizeHint(self):
        return QSize(200,self.height())
    def update_setups(self,members):
        p=self.w.project;signature=tuple((i,info(p,i)['name']) for i in members)
        if signature!=self.signature:
            self.signature=signature
            for b in self.buttons.values():b.hide();b.deleteLater()
            self.buttons={}
            for i,name in signature:
                b=QToolButton(self);b.setText(name);b.setCheckable(True)
                b.setStyleSheet('QToolButton {padding:2px 6px;border:1px solid #53616c;border-radius:3px;} QToolButton:checked {background:#41677b;border:1px solid #a6d6ed;}')
                b.clicked.connect(lambda checked=False,a=i:self.w.select_area(a));self.buttons[i]=b;b.show()
        for i,b in self.buttons.items():
            r=info(p,i);b.setChecked(i==self.w.area_id);b.setAccessibleName(r['name'])
            b.setToolTip(f'{r["name"]}\n{r["meaning"]}\n{len(p.objects(i))} object records · area ${i:02X}\n'+r['evidence'])
        self.arrange()
    def arrange(self):
        width=max(1,self.width());x=y=0;gap=4
        height=max(26,self.fontMetrics().height()+8)
        for i,b in self.buttons.items():
            name=b.accessibleName()
            bw=min(width,b.fontMetrics().horizontalAdvance(name)+16)
            if x and x+bw>width:x=0;y+=height+gap
            b.setText(b.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,max(1,bw-14)))
            b.setGeometry(x,y,bw,height);x+=bw+gap
        needed=y+height
        if self.height()!=needed:self.setFixedHeight(needed)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.arrange()


class TerrainButtons(SetupButtons):
    def update_targets(self):
        from .event_flags import KNOWN_NAMES,flag_label
        combo=self.w.target;p=self.w.project
        choices=[]
        for index in range(combo.count()):
            kind,resource=combo.itemData(index)
            if kind=='layout':
                name='Base terrain';tip='Edit the underlying terrain shared by this map’s setups.'
            else:
                actions=[a for a in self.w.rom.area_actions[self.w.area_id] if a.opcode==0x22 and a.value==resource]
                names=[KNOWN_NAMES.get(a.flag,f'Flag ${a.flag:02X}') for a in actions]
                name=' / '.join(dict.fromkeys(names))
                patch=self.w.rom.changes[resource]
                tip=f'Story terrain change ${resource:02X}: {patch.width} × {patch.height} tiles at ({patch.x}, {patch.y}).\n'+ '\n'.join(flag_label(a.flag)+(' — active' if a.flag in p.flags else ' — inactive in preview') for a in actions)
            choices.append((index,name,tip))
        # Distinguish multiple patches controlled by the same flag without inventing roles.
        for index,name,tip in choices:
            if sum(n==name for _,n,_ in choices)>1:name+=f' · change ${combo.itemData(index)[1]:02X}'
            if index not in self.buttons:
                b=QToolButton(self);b.setCheckable(True)
                b.setStyleSheet('QToolButton {padding:2px 6px;border:1px solid #53616c;border-radius:3px;} QToolButton:checked {background:#41677b;border:1px solid #a6d6ed;}')
                b.clicked.connect(lambda checked=False,i=index:combo.setCurrentIndex(i));self.buttons[index]=b;b.show()
            b=self.buttons[index];b.setAccessibleName(name);b.setToolTip(tip);b.setChecked(index==combo.currentIndex())
        for index in list(self.buttons):
            if index>=combo.count():
                b=self.buttons.pop(index);b.hide();b.deleteLater()
        self.arrange()


def focus_objects(w):
    objects=w.project.objects(w.area_id)
    if not objects:w.fit_views();return
    xs=[o[3]&63 for o in objects];ys=[o[2]&63 for o in objects]
    w.canvas.fitInView(QRectF((min(xs)-3)*16,(min(ys)-3)*16,(max(xs)-min(xs)+7)*16,(max(ys)-min(ys)+7)*16),Qt.AspectRatioMode.KeepAspectRatio)

def show_details(w):
    p=w.project;area_id=w.area_id;r=info(p,area_id)
    dialog=QDialog(w);dialog.setWindowTitle('Map setup — entrances, differences & name');dialog.resize(1000,730)
    box=QVBoxLayout(dialog);heading=QLabel(f'{w.rom.areas[area_id].name} · {r["name"]}');heading.setStyleSheet('font-size:20px;font-weight:bold');box.addWidget(heading)
    note=QLabel('Setup selects an area record and its object list. Story preview selects flags within that setup. Shared terrain edits can affect several setups.');note.setWordWrap(True);box.addWidget(note)
    tabs=QTabWidget();box.addWidget(tabs,1)
    overview=QWidget();layout=QVBoxLayout(overview);tabs.addTab(overview,'Meaning & name')
    description=QTextBrowser();description.setHtml(f'<h3>{escape(r["name"])}</h3><p>{escape(r["meaning"])}</p><p>{escape(r["evidence"])}</p><p>Names describe the original game unless you assign a project label. Object or entrance edits may change that role.</p>');layout.addWidget(description)
    from .event_flags import flag_label
    from .field_actions import field_action
    changes=''.join('<li>'+escape(flag_label(a.flag)+': '+field_action(a.opcode,a.value))+'</li>' for a in p.rom.area_actions[area_id])
    description.append('<h3>Story-dependent changes within this setup</h3>'+('<ul>'+changes+'</ul>' if changes else '<p>No restoration actions in this area’s action list. Object visibility and scripts can still depend on flags.</p>'))
    label=QLineEdit(r['name']);label.setMaxLength(80);layout.addWidget(QLabel('Name in this project'));layout.addWidget(label)
    meaning=QPlainTextEdit(r['meaning']);meaning.setMaximumHeight(100);layout.addWidget(QLabel('Description (up to 400 characters)'));layout.addWidget(meaning)
    buttons=QHBoxLayout();layout.addLayout(buttons)
    save=QPushButton('Save name & description');reset=QPushButton('Use original name');buttons.addWidget(save);buttons.addWidget(reset)
    def rename(clear=False):
        from .expanded_content_editor import commit
        def apply():
            if clear:p.setup_labels.pop(area_id,None)
            else:p.setup_labels[area_id]=[label.text().strip(),meaning.toPlainText()]
        if commit(w,apply,'Name map setup'):
            fresh=info(p,area_id);label.setText(fresh['name']);meaning.setPlainText(fresh['meaning']);heading.setText(f'{w.rom.areas[area_id].name} · {fresh["name"]}')
    save.clicked.connect(lambda:rename());reset.clicked.connect(lambda:rename(True))
    differences=QTreeWidget();differences.setHeaderLabels(['Other setup','Shared terrain?','Object list','Area settings','Metatiles','Palette']);tabs.addTab(differences,'Compare setups')
    area=p.rom.areas[area_id]
    for i in p.rom.shared_areas(area.layout_id):
        if i==area_id:continue
        other=p.rom.areas[i];changed=[n for n,(a,b) in enumerate(zip(area.header,other.header)) if a!=b]
        fields={0:'terrain/flags',1:'graphics profile',2:'sprite set'}
        item=QTreeWidgetItem([info(p,i)['name'],'Yes' if p.layout_id(i)==p.layout_id(area_id) else 'Independent terrain',
             'Identical' if p.objects(i)==p.objects(area_id) else f'Different · {len(p.objects(i))} records',
             'Same record (alias)' if area.offset==other.offset and area.header==other.header else 'Different '+', '.join(fields.get(n,f'header byte {n}') for n in changed) if changed else 'Same header; separate record',
             'Shared set' if p.tileset(i)==p.tileset(area_id) else 'Different sets',
             'Shared palette' if p.state(i).palette==p.state(area_id).palette else 'Different palettes'])
        item.setToolTip(3,'Changed header byte indices: '+str(changed)+'. Identical headers do not imply identical coordinate tables.');differences.addTopLevelItem(item)
    if differences.topLevelItemCount()==0:differences.addTopLevelItem(QTreeWidgetItem(['No other setups share this original layout.']))
    for i in range(3):differences.resizeColumnToContents(i)
    entry_page=QWidget();entry_box=QVBoxLayout(entry_page);tabs.addTab(entry_page,'Entered from')
    entry_note=QLabel('Original-ROM evidence. Inspect current project to account for your entrance and terrain edits. Records are static possibilities, not a complete gameplay trace.');entry_note.setWordWrap(True);entry_box.addWidget(entry_note)
    tree=QTreeWidget();tree.setHeaderLabels(['Source','Source tile','Arrival tile','Evidence']);tree.setColumnWidth(0,265);entry_box.addWidget(tree)
    def fill(record):
        tree.clear()
        for e in record.get('incoming',[]):
            source=(p.rom.areas[e['source_area']].name+' · '+info(p,e['source_area'])['name']) if e['kind']=='entrance' else f'Event ${e["address"]:06X}'
            item=QTreeWidgetItem([source,str(tuple(e.get('source_xy',()))),str(tuple(e['arrival'])),'Coordinate-backed trigger' if e['kind']=='entrance' else 'Decoded field command'])
            item.setData(0,Qt.ItemDataRole.UserRole,e);item.setToolTip(3,'Preview samples: '+', '.join(e.get('samples',[])) if e['kind']=='entrance' else 'Execution depends on event callers and branches.');tree.addTopLevelItem(item)
        if not record.get('incoming'):tree.addTopLevelItem(QTreeWidgetItem(['No static incoming link found. Runtime entry remains possible.']))
    fill(catalogue().get(area_id,{}))
    controls=QHBoxLayout();entry_box.addLayout(controls);scan=QPushButton('Inspect current project');visit=QPushButton('Go to selected source');controls.addWidget(scan);controls.addWidget(visit)
    def inspect():
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:report=audit(p);fill(next(r for r in report['areas'] if r['id']==area_id));entry_note.setText('Current-project snapshot. All restoration combinations and individual relevant flags sampled. Unresolved/runtime-only entries are not guessed.')
        except (ValueError,IndexError) as error:w.error(error)
        finally:QApplication.restoreOverrideCursor()
    scan.clicked.connect(inspect)
    def go():
        item=tree.currentItem();e=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if not e:return
        if e['kind']=='entrance':
            dialog.accept();w.select_area(e['source_area']);w.tool.setCurrentText('Entrances');w.show_connections.setChecked(True)
            x,y=e['source_xy'];w.arrival=(e['source_area'],x,y);w.refresh_map();w.canvas.centerOn(x*16+8,y*16+8)
            w.statusBar().showMessage('Entry source highlighted. Its availability depends on story state and the reachable map section.')
        else:
            from .event_inspector import EventInspector
            dialog.accept();w.event_inspector=EventInspector(w,f'Entry command ${e["address"]:06X}','Static field command; callers determine when it executes.',e['address']);w.event_inspector.show()
    visit.clicked.connect(go);tree.itemDoubleClicked.connect(lambda *_:go())
    close=QPushButton('Close');close.clicked.connect(dialog.accept);box.addWidget(close);dialog.exec()
