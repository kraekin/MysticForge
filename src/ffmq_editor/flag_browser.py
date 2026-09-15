"""Search flags, read evidence, and visit their project sources."""
from html import escape
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QTreeWidget,QTreeWidgetItem,QPushButton,QSplitter,QTextBrowser,QComboBox,QCheckBox
from .event_flags import flag_label,NAMES,EVIDENCE
from .flag_audit import FlagAudit

class FlagBrowser(QDialog):
    def __init__(self,browser):
        super().__init__(browser);self.browser=browser;self.audit=FlagAudit(browser.window.rom,browser.window.project,browser.catalog)
        self.setWindowTitle('Flag guide & evidence — read-only');self.resize(1240,790)
        box=QVBoxLayout(self)
        note=QLabel('Choose a flag to learn what it controls. Expand it for individual sources; select a source to read its evidence. This is a project snapshot, not the running game.');note.setWordWrap(True);box.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText('Search a flag, map, action, or associated dialogue…');box.addWidget(self.search)
        self.scope=QComboBox();self.scope.addItems(['All flags','Verified story meanings','Known uses, unnamed story meaning','No indexed uses']);box.addWidget(self.scope)
        split=QSplitter();box.addWidget(split,1)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Flag / use','Source','Location']);self.tree.setColumnWidth(0,255);self.tree.setColumnWidth(1,255);split.addWidget(self.tree)
        self.details=QTextBrowser();split.addWidget(self.details);split.setSizes([650,590])
        self.tree.setColumnHidden(2,True)
        self.groups=[]
        for dossier in self.audit.dossiers:
            flag=dossier.flag;group=QTreeWidgetItem([flag_label(flag),f'{len(dossier.evidence)} source references','']);self.tree.addTopLevelItem(group)
            group.setData(2,Qt.ItemDataRole.UserRole,flag);group.setToolTip(0,dossier.overview)
            for evidence in dossier.evidence:
                child=QTreeWidgetItem([evidence.kind+' · '+evidence.action,evidence.explanation,evidence.source])
                child.setData(0,Qt.ItemDataRole.UserRole,evidence.target);child.setData(1,Qt.ItemDataRole.UserRole,evidence)
                child.setData(2,Qt.ItemDataRole.UserRole,flag);child.setToolTip(1,evidence.explanation);group.addChild(child)
            self.groups.append(group)
        self.search.textChanged.connect(self.filter);self.scope.currentIndexChanged.connect(self.filter)
        self.tree.itemDoubleClicked.connect(self.visit);self.tree.itemSelectionChanged.connect(self.select)
        self.open_button=QPushButton('Open selected source');self.open_button.clicked.connect(lambda:self.visit(self.tree.currentItem()));box.addWidget(self.open_button)
        technical=QCheckBox('Show technical source locations');technical.toggled.connect(lambda checked:self.tree.setColumnHidden(2,not checked));box.addWidget(technical)
        coverage=QPushButton('Audit coverage & unresolved references…');coverage.clicked.connect(self.show_coverage);box.addWidget(coverage)
        self.filter();self.tree.setCurrentItem(self.groups[1])

    def filter(self,*_):
        query=self.search.text().strip();words=query.lower().replace('$','').split();scope=self.scope.currentIndex()
        exact=int(query.lstrip('$'),16) if re.fullmatch(r'\$?[0-9a-fA-F]{2}',query) else None
        for group,dossier in zip(self.groups,self.audit.dossiers):
            category=scope==0 or scope==1 and dossier.flag in NAMES or scope==2 and dossier.flag not in NAMES and bool(dossier.evidence) or scope==3 and not dossier.evidence
            match=category and (dossier.flag==exact if exact is not None else all(w in dossier.search_text.replace('$','') for w in words))
            group.setHidden(not match);group.setExpanded(bool(words and match))
        item=self.tree.currentItem()
        root=item.parent() if item and item.parent() else item
        if root is None or root.isHidden():self.tree.setCurrentItem(next((g for g in self.groups if not g.isHidden()),None))

    def select(self):
        item=self.tree.currentItem();self.open_button.setEnabled(False)
        if item is None:self.details.setPlainText('No flags match this search.');return
        dossier=self.audit.dossiers[item.data(2,Qt.ItemDataRole.UserRole)]
        evidence=item.data(1,Qt.ItemDataRole.UserRole)
        def p(text):return '<p>'+escape(text).replace('\n','<br>')+'</p>'
        html='<h2>'+escape(flag_label(dossier.flag))+'</h2>'+p(dossier.status)+p(dossier.overview)
        html+='<h3>Starting value</h3>'+p(('Set' if dossier.initial else 'Clear')+' in the original new-game flag block. This is not your save state and does not establish the flag’s purpose.')
        if evidence is not None:
            html+='<h3>Selected evidence</h3>'+p(evidence.explanation)+p(evidence.context)+p('Source: '+evidence.source)
            self.open_button.setEnabled(evidence.target is not None)
            if evidence.target is None:html+=p('Native source is shown here; it is not event bytecode and cannot be opened as an event.')
        else:
            html+='<h3>How to investigate this flag</h3>'+p('Start with Set and Clear references to find when it changes. Compare checks, visible objects, maps and routes to understand the consequences. Dialogue in a caller is a clue, not a verified name.')
            places=list(dict.fromkeys(e.explanation for e in dossier.evidence if e.kind in ('Map','Object','Route','Entrance')))
            if places:html+='<h3>Observed effects</h3><ul>'+''.join('<li>'+escape(s)+'</li>' for s in places[:18])+'</ul>'+ (p(f'{len(places)-18} more effects are listed in the source tree.') if len(places)>18 else '')
        if dossier.flag in NAMES:html+='<h3>Name evidence</h3>'+p(EVIDENCE)
        html+='<h3>Next investigation</h3>'+p(dossier.next_step)
        html+=p('This guide covers indexed static sources. Runtime-dependent and unaudited code can have additional effects. Use Audit coverage for the exact limits.')
        self.details.setHtml(html)

    def show_coverage(self):
        self.coverage=QDialog(self);self.coverage.setWindowTitle('Flag audit coverage — read-only');self.coverage.resize(820,600)
        box=QVBoxLayout(self.coverage);text=QTextBrowser();box.addWidget(text)
        text.setPlainText('AUDIT SCOPE\n\n'+'\n\n'.join(self.audit.notes)+'\n\nRUNTIME-INDEXED NATIVE CALLERS\n\n'+'\n'.join(f'{c["action"]} at CPU ${c["address"]:06X}: '+c['explanation'] for c in self.audit.unresolved))
        self.coverage.show()

    def visit(self,item,*_):
        target=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if target is None:return
        b=self.browser
        # Refreshing is explicit: keep this guide tied to its original snapshot.
        if b.stale or b.project is not b.window.project or b.snapshot_edits!=b.window.project.edits:
            self.details.setPlainText('The project changed. Refresh the event browser and reopen Flags & references to inspect current sources.');return
        if target[0]=='event':
            key=tuple(target[1]);b.search.clear();b.category.setCurrentIndex(0);b.list.setCurrentItem(b.items[key]);b.open_event();return
        w=b.window;area=target[1];w.select_area(area)
        if target[0]=='object':w.tool.setCurrentText('Objects');w.object_editor.list.setCurrentRow(target[2])
        w.raise_();w.activateWindow()
