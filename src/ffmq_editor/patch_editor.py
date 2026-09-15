"""Patch export from the active project; no external patch import."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,QPushButton,QFileDialog,QApplication,QMessageBox
from .rom import BASE_SHA256
from .paths import user_directory

class PatchExportDialog(QDialog):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.setWindowTitle('MysticForge — Export patch');self.resize(640,330)
        box=QVBoxLayout(self);heading=QLabel('Share your project as a patch');heading.setObjectName('heading');box.addWidget(heading)
        note=QLabel('Builds directly from the current project. No intermediate ROM file is needed. Every patch is reapplied and verified before saving.');note.setWordWrap(True);box.addWidget(note)
        self.format=QComboBox();self.format.addItem('BPS — recommended','bps');self.format.addItem('IPS — compatibility','ips');box.addWidget(self.format)
        self.explanation=QLabel();self.explanation.setWordWrap(True);box.addWidget(self.explanation);self.format.currentIndexChanged.connect(self.describe);self.describe()
        box.addWidget(QLabel('Required original: unheadered USA v1.0 Final Fantasy Mystic Quest'))
        fingerprint=QLineEdit(BASE_SHA256);fingerprint.setReadOnly(True);fingerprint.setToolTip('Required original ROM SHA-256');box.addWidget(fingerprint)
        self.status=QLabel('The patch includes all applied project edits, including enabled ROM fixes.');self.status.setWordWrap(True);box.addWidget(self.status)
        row=QHBoxLayout();row.addStretch();close=QPushButton('Close');close.clicked.connect(self.close);row.addWidget(close);self.save_button=QPushButton('Export patch…');self.save_button.clicked.connect(self.export);row.addWidget(self.save_button);box.addLayout(row)
    def describe(self,*_):
        self.explanation.setText('BPS verifies the original ROM, the resulting ROM, and the patch using built-in checksums.' if self.format.currentData()=='bps' else 'IPS supports older patching tools but has no built-in ROM identity checks. Tell recipients to use the exact original ROM shown below.')
    def refresh_format(self):
        expanded=self.w.project.expanded
        self.format.model().item(1).setEnabled(not expanded)
        if expanded:
            self.format.setCurrentIndex(0)
            self.explanation.setText('Expanded 1 MiB project: use BPS. The patch applies to the original 512 KiB ROM and produces the expanded ROM. IPS export is unavailable for expanded projects.')
        else:self.describe()
    def export(self):
        w=self.w
        if not w.confirm_database_edits():return
        w.end_stroke();kind=self.format.currentData();label=w.project.path.stem if w.project.path else 'My MysticForge mod'
        name,_=QFileDialog.getSaveFileName(self,'Export '+kind.upper()+' patch',str(user_directory()/(label+'.'+kind)),kind.upper()+' patch (*.'+kind+')')
        if not name:return
        path=Path(name)
        if not path.suffix:
            path=path.with_suffix('.'+kind)
            if path.exists() and QMessageBox.question(self,'Replace existing patch?',f'Replace {path.name}?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.save_button.setEnabled(False);QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report=w.project.export_patch(path,kind)
            self.status.setText(f'Exported and verified {path.name} · {report["patch_bytes"]:,} bytes · {report["writes"]} ROM resource writes. Applies to the original unheadered USA v1.0 ROM.')
        except (OSError,ValueError) as error:self.status.setText(f'Could not export: {error}')
        finally:self.save_button.setEnabled(True);QApplication.restoreOverrideCursor()

def show_patch_export(w):
    if not w.confirm_database_edits():return
    w.end_stroke()
    if not hasattr(w,'patch_dialog'):w.patch_dialog=PatchExportDialog(w)
    w.patch_dialog.refresh_format()
    w.patch_dialog.show();w.patch_dialog.raise_();w.patch_dialog.activateWindow()
