"""Read-only event blocks, call navigation and map destination links."""
from PySide6.QtCore import Qt,Signal,QSize,QRect
from PySide6.QtGui import QColor,QBrush,QFontMetrics
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QCheckBox,QTreeWidget,QTreeWidgetItem
from .events import decode,status
from .event_presentation import readable_rows,Dialogue,technical_setup

class EventFlowView(QWidget):
    entryChanged=Signal(int)
    def __init__(self,window,entry,extent=None):
        super().__init__();self.window=window;self.root=entry;self.history=[];self.entry=entry;self.extent=extent;self.limit=256
        box=QVBoxLayout(self);bar=QHBoxLayout();box.addLayout(bar)
        self.back=QPushButton('Back');self.back.clicked.connect(self.go_back);bar.addWidget(self.back)
        home=QPushButton('Original event');home.clicked.connect(lambda:self.navigate(self.root,extent));bar.addWidget(home)
        follow=QPushButton('Expand / collapse steps');follow.clicked.connect(self.follow);bar.addWidget(follow)
        self.expand_button=follow
        self.focus_button=QPushButton('Focus selected event');self.focus_button.clicked.connect(self.focus_event);bar.addWidget(self.focus_button)
        self.map_button=QPushButton('Show destination on map');self.map_button.clicked.connect(self.show_map);bar.addWidget(self.map_button)
        self.technical=QCheckBox('Technical details');self.technical.toggled.connect(self.populate);bar.addWidget(self.technical)
        self.more=QPushButton('Inspect more');self.more.clicked.connect(self.inspect_more);bar.addWidget(self.more)
        self.location=QLabel();box.addWidget(self.location)
        self.coverage=QLabel();self.coverage.setWordWrap(True);box.addWidget(self.coverage)
        preview_bar=QHBoxLayout();box.addLayout(preview_bar)
        self.preview_button=QPushButton('Preview selected dialogue…');self.preview_button.clicked.connect(self.preview_dialogue);preview_bar.addWidget(self.preview_button)
        glyphs=QPushButton('Game glyph reference…');glyphs.clicked.connect(self.show_glyphs);preview_bar.addWidget(glyphs);preview_bar.addStretch()
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Address','Action / branch','Bytes']);self.tree.setColumnWidth(0,155);self.tree.setColumnWidth(1,720);box.addWidget(self.tree)
        self.tree.setTreePosition(1);self.tree.setIndentation(24);self.tree.setWordWrap(True);self.tree.setUniformRowHeights(False)
        self.tree.header().sectionResized.connect(self.row_sizes)
        self.tree.itemExpanded.connect(self.expand_event)
        self.tree.itemClicked.connect(self.click_link);self.tree.itemSelectionChanged.connect(self.selection)
        note=QLabel('Click “Show steps” to read a called event here, beneath its caller. Collapse it to return to the surrounding sequence. Both branch outcomes are available; nothing is executed. “Focus selected event” opens a separate view with Back navigation.');note.setWordWrap(True);box.addWidget(note)
        self.populate()

    def columns(self):
        self.tree.setColumnHidden(0,not self.technical.isChecked());self.tree.setColumnHidden(2,not self.technical.isChecked())
        self.expand_button.setVisible(not self.technical.isChecked())

    def populate(self):
        self.tree.clear();self.inline_rows=0;self.paths={};rows=decode(self.window.rom,self.entry,limit=self.limit,follow_calls=False,extent=self.extent)
        self.more.setVisible(any(status(r)=='limit' for r in rows) and self.limit<8192)
        leaders={self.entry}
        for r in rows:
            if any(label not in ('next','call','fragment') for label,_ in r.edges):leaders.update(target for label,target in r.edges if label not in ('call','fragment'))
        group=None;previous=None;blocks=0
        for r in sorted(rows,key=lambda x:x.address):
            if group is None or r.address in leaders or previous!=r.address:
                blocks+=1;group=QTreeWidgetItem([f'${r.address:06X}',f'Block {blocks}'+(' · entry' if r.address==self.entry else ''),'']);self.tree.addTopLevelItem(group);group.setExpanded(True)
            item=QTreeWidgetItem([f'${r.address:06X}',r.description,r.raw.hex(' ').upper()]);group.addChild(item);item.setData(0,Qt.ItemDataRole.UserRole+1,r)
            item.setToolTip(1,r.description)
            condition=r.description.startswith('If ')
            for label,target in r.edges:
                if label=='next':continue
                yes=label=='yes' or (label=='set' and 'is clear' not in r.description) or (label=='clear' and 'is clear' in r.description)
                caption=('Yes' if yes else 'No')+f' · {label}' if condition else {'call':'Open called event','fragment':'Open shared text/event fragment','jump':'Go to branch'}.get(label,label)
                link=QTreeWidgetItem([f'${target:06X}',caption,f'${target:06X}']);link.setData(0,Qt.ItemDataRole.UserRole,target);item.addChild(link)
                if label=='bounded':link.setData(0,Qt.ItemDataRole.UserRole+2,r.raw[-1]);link.setText(1,'Open bounded text/event data')
            if r.raw and r.raw[0]==0x2c and len(r.raw)==3 and r.raw[2]<0x80:
                target=self.window.connections.destination(r.raw[2],r.raw[1])
                if target:
                    a,x,y,_=target;item.addChild(QTreeWidgetItem(['',f'Destination: {self.window.rom.areas[a].name} (${a:02X}), ({x}, {y})','']))
            item.setExpanded(True);previous=r.address+len(r.raw)
        unknown=sum(not r.complete for r in rows);calls=sum(label in ('call','fragment') for r in rows for label,_ in r.edges)
        unnamed=sum('not verified' in r.description for r in rows)
        self.coverage.setText(f'{len(rows)} decoded rows · {blocks} blocks · {calls} call/fragment links · {unknown} partial/unsupported rows · {unnamed} rows with unnamed actions. Counts cover this view, not called events or runtime behavior.')
        if not self.technical.isChecked():self.readable(rows,unknown,unnamed)
        trail=[a for a,_ in self.history]+[self.entry]
        self.location.setText('Original event'+''.join(f'  →  ${a:06X}' for a in trail))
        self.back.setEnabled(bool(self.history));self.columns();self.selection()
        self.entryChanged.emit(self.entry)

    def inspect_more(self):
        self.limit=min(8192,self.limit*4);self.populate()

    def readable(self,rows,unknown,unnamed,parent=None,ancestry=None):
        if parent is None:self.tree.clear()
        ancestry=ancestry or ((self.entry,self.extent),)
        presented=readable_rows(self.window.rom,rows)
        branch_sources={}
        for r in rows:
            for label,target in r.edges:
                if label not in ('next','call','fragment','bounded'):branch_sources.setdefault(target,[]).append(r.address)
        active_parent=parent;setup=None;setup_count=0
        def attach(item,container):
            if container is None:self.tree.addTopLevelItem(item)
            else:container.addChild(item)
        dialogues=0
        for row in presented:
            if row.address in branch_sources and rows and row.address!=rows[0].address:
                sources=branch_sources[row.address]
                path=QTreeWidgetItem(['',f'{"Shared path" if len(sources)>1 else "Branch path"} ${row.address:06X} · {len(sources)} incoming route(s)',''])
                path.setToolTip(1,'Reached from '+', '.join(f'${a:06X}' for a in sources)+'. Expand to read this path; it is not the next step of every branch.')
                path.setForeground(1,QBrush(QColor('#c4b5fd')));attach(path,parent)
                self.paths[row.address]=path;active_parent=path;setup=None
            if isinstance(row,Dialogue):
                dialogues+=1
                item=QTreeWidgetItem(['','Dialogue\n\n'+row.text.strip(),''])
                item.setData(0,Qt.ItemDataRole.UserRole+7,row.text)
                item.setBackground(1,QBrush(QColor('#293e4b')))
                font=item.font(1);font.setPointSize(11);item.setFont(1,font)
                item.setToolTip(1,'Combined text, shared fragments and fixed ROM name references. Names reflect this ROM, not a running save. Technical details shows the original instructions. Unknown glyphs retain their hex code.')
            else:
                item=QTreeWidgetItem(['',row.description,'']);item.setData(0,Qt.ItemDataRole.UserRole+1,row)
                for label,target in row.edges:
                    if label=='next':continue
                    if row.description.startswith('If '):
                        yes=label=='yes' or (label=='set' and 'is clear' not in row.description) or (label=='clear' and 'is clear' in row.description)
                        caption='Yes — show branch steps' if yes else 'No — show branch steps'
                    else:caption='Show steps in called event' if label=='call' else 'Show shared fragment steps' if label=='fragment' else 'Show branch steps'
                    link=QTreeWidgetItem(['',caption,'']);link.setData(0,Qt.ItemDataRole.UserRole,target);item.addChild(link)
                    if label=='bounded':link.setData(0,Qt.ItemDataRole.UserRole+2,row.raw[-1]);link.setText(1,'Show bounded text/event steps')
                    link.setData(0,Qt.ItemDataRole.UserRole+3,ancestry)
                    link.setToolTip(1,f'Event ${target:06X}. Expands here without leaving the caller. Runtime object slots depend on the active scene.')
                    link.addChild(QTreeWidgetItem(['','Expand to inspect this event','']))
                    link.setForeground(1,QBrush(QColor('#91cfe9')))
                if row.raw and row.raw[0]==0x2c and len(row.raw)==3 and row.raw[2]<0x80:
                    target=self.window.connections.destination(row.raw[2],row.raw[1])
                    if target:
                        a,x,y,_=target;item.setText(1,f'Go to {self.window.rom.areas[a].name}\nArrival: ({x}, {y}) · area ${a:02X}')
                if not row.complete:item.setForeground(1,QBrush(QColor('#ffd08a')))
            if technical_setup(row):
                if setup is None:
                    setup=QTreeWidgetItem(['','Technical setup','']);attach(setup,active_parent);setup_count=0
                setup_count+=1;setup.setText(1,f'Technical setup · {setup_count} command(s) — expand for details');setup.addChild(item)
            else:
                setup=None;attach(item,active_parent)
            if not isinstance(row,Dialogue) and row.description.startswith(('If ','Conditional call')):
                item.setBackground(1,QBrush(QColor('#38334a')))
            item.setExpanded(True)
        self.inline_rows+=len(presented)
        if parent is not None:
            self.row_sizes();return
        counts={kind:sum(status(row)==kind for row in rows) for kind in ('runtime','unsupported','invalid','limit')}
        labels={'runtime':'runtime dependencies','unsupported':'unsupported commands','invalid':'invalid data rows','limit':'inspection limits'}
        self.coverage.setText(f'This event: {dialogues} dialogue passage(s) · {len(presented)-dialogues} steps (called events expand below)'+''.join(f' · {count} {labels[kind]}' for kind,count in counts.items() if count)+(f' · {unnamed} steps with unverified action names' if unnamed else ''))
        self.coverage.setToolTip('Text fragments and verified fixed-name helpers are combined with adjacent dialogue. Other calls, branches and unknown commands remain separate. This is not a runtime dialogue simulation.')
        self.row_sizes()

    def row_sizes(self,*_):
        if not hasattr(self,'tree') or self.technical.isChecked():return
        width=max(180,self.tree.columnWidth(1)-65)
        def size(item,depth=0):
            metrics=QFontMetrics(item.font(1));height=metrics.boundingRect(QRect(0,0,max(100,width-depth*24),10000),Qt.TextFlag.TextWordWrap,item.text(1)).height()
            item.setSizeHint(1,QSize(0,max(38,height+24)))
            for i in range(item.childCount()):size(item.child(i),depth+1)
        for i in range(self.tree.topLevelItemCount()):size(self.tree.topLevelItem(i))

    def navigate(self,target,extent=None):
        if (target,extent)==(self.entry,self.extent):return
        self.history.append((self.entry,self.extent));self.entry=target;self.extent=extent;self.limit=256;self.populate()

    def go_back(self):
        if self.history:self.entry,self.extent=self.history.pop();self.limit=256;self.populate()

    def follow(self):
        item=self.tree.currentItem()
        if item is None:return
        target=item.data(0,Qt.ItemDataRole.UserRole)
        if target is not None:
            if self.technical.isChecked():self.focus_event()
            else:item.setExpanded(not item.isExpanded())

    def click_link(self,item,column):
        path=item.data(0,Qt.ItemDataRole.UserRole+6)
        if path is not None and path in self.paths:
            existing=self.paths[path];existing.setExpanded(True);self.tree.setCurrentItem(existing);self.tree.scrollToItem(existing);return
        if not self.technical.isChecked() and item.data(0,Qt.ItemDataRole.UserRole) is not None:
            item.setExpanded(True)

    def expand_event(self,item):
        target=item.data(0,Qt.ItemDataRole.UserRole)
        if self.technical.isChecked() or target is None or item.data(0,Qt.ItemDataRole.UserRole+4):return
        item.setData(0,Qt.ItemDataRole.UserRole+4,True)
        item.takeChildren()
        extent=item.data(0,Qt.ItemDataRole.UserRole+2)
        ancestry=tuple(tuple(v) for v in (item.data(0,Qt.ItemDataRole.UserRole+3) or ()))
        if (target,extent) in ancestry:
            item.addChild(QTreeWidgetItem(['','Loop / repeated caller — this event is already above. Collapse to continue reading.','']))
        elif target in self.paths:
            existing=self.paths[target];existing.setExpanded(True)
            link=QTreeWidgetItem(['',f'Shared path ${target:06X} is shown in this view — click to locate it',''])
            link.setData(0,Qt.ItemDataRole.UserRole+6,target);item.addChild(link)
        elif len(ancestry)>=8 or self.inline_rows>=2048:
            item.addChild(QTreeWidgetItem(['','Inline inspection limit reached. Use “Focus selected event” to inspect this event separately.','']))
        else:
            rows=decode(self.window.rom,target,limit=min(256,2048-self.inline_rows),follow_calls=False,extent=extent)
            self.readable(rows,0,0,item,ancestry+((target,extent),))
            item.addChild(QTreeWidgetItem(['','End of this preview · continue with the caller below. Branches may leave the caller; this is not an execution trace.','']))
        self.row_sizes()

    def focus_event(self):
        item=self.tree.currentItem()
        if item is not None:
            target=item.data(0,Qt.ItemDataRole.UserRole)
            if target is not None:self.navigate(target,item.data(0,Qt.ItemDataRole.UserRole+2))

    def destination(self):
        item=self.tree.currentItem()
        r=item.data(0,Qt.ItemDataRole.UserRole+1) if item else None
        if r and r.raw and r.raw[0]==0x2c and len(r.raw)==3 and r.raw[2]<0x80:return self.window.connections.destination(r.raw[2],r.raw[1])

    def selection(self):
        self.map_button.setEnabled(self.destination() is not None)
        item=self.tree.currentItem()
        self.focus_button.setEnabled(item is not None and item.data(0,Qt.ItemDataRole.UserRole) is not None)
        self.preview_button.setEnabled(item is not None and item.data(0,Qt.ItemDataRole.UserRole+7) is not None)

    def preview_dialogue(self):
        from .dialogue_preview import DialoguePreview
        item=self.tree.currentItem();text=item.data(0,Qt.ItemDataRole.UserRole+7) if item else None
        if text is not None:
            self.dialogue_preview=DialoguePreview(self,text);self.dialogue_preview.show()

    def show_glyphs(self):
        from .dialogue_preview import GlyphViewer
        self.glyph_viewer=GlyphViewer(self);self.glyph_viewer.show()

    def show_map(self):
        target=self.destination()
        if target:
            area,x,y,_=target;self.window.select_area(area);self.window.show_connections.setChecked(True)
            self.window.arrival=(area,x,y);self.window.refresh_map();self.window.canvas.centerOn(x*16+8,y*16+8)
