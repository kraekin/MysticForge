"""Visible application shell before ROM selection, including cancel/retry."""
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow,QWidget,QVBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox
from .paths import application_dir
from .rom import Rom

class WelcomeWindow(QMainWindow):
    def __init__(self,rom_path=None):
        super().__init__();self.editor=None;self.rom_path=rom_path;self.setWindowTitle('MysticForge — Welcome');self.resize(900,600)
        root=QWidget();self.setCentralWidget(root);box=QVBoxLayout(root);box.setContentsMargins(50,50,50,50);box.addStretch()
        from . import __version__
        title=QLabel(f'MysticForge · {__version__}');title.setObjectName('heading');box.addWidget(title)
        text=QLabel('Final Fantasy Mystic Quest editor · Early alpha\n\nOpen your original, unheadered USA v1.0 ROM to begin.\nEdits are saved as projects; export creates a separate ROM copy.');text.setWordWrap(True);box.addWidget(text)
        self.open_button=QPushButton('Open original ROM…');self.open_button.clicked.connect(self.choose_rom);box.addWidget(self.open_button)
        self.status=QLabel('');self.status.setWordWrap(True);box.addWidget(self.status);box.addStretch()
    def start(self):
        path=Path(self.rom_path) if self.rom_path else application_dir()/'Final Fantasy - Mystic Quest (USA).sfc'
        if path.is_file():self.load_rom(path)
        else:self.choose_rom()
    def choose_rom(self):
        name,_=QFileDialog.getOpenFileName(self,'Select original unheadered USA v1.0 ROM',str(application_dir()),'SNES ROM (*.sfc *.smc)')
        if name:self.load_rom(Path(name))
        else:self.status.setText('No ROM opened. Choose Open original ROM when you are ready.')
    def load_rom(self,path):
        from .app import MainWindow
        self.open_button.setEnabled(False);self.status.setText('Loading ROM…')
        try:
            editor=MainWindow(Rom(path));self.editor=editor;editor.show();self.close()
        except Exception as error:
            self.status.setText('Could not open this ROM. Select an original unheadered USA v1.0 copy and try again.')
            QMessageBox.warning(self,'Could not open ROM',str(error))
        finally:self.open_button.setEnabled(True)
