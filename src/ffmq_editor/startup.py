"""Welcome actions and restoration of the last saved project."""
from pathlib import Path
from PySide6.QtWidgets import QMainWindow,QWidget,QVBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox
from .paths import application_dir,user_directory
from .rom import Rom
from .session import last_session,remember_project

class WelcomeWindow(QMainWindow):
    def __init__(self,rom_path=None):
        super().__init__();self.editor=None;self.rom_path=rom_path;self.setWindowTitle('MysticForge — Welcome');self.resize(900,600)
        root=QWidget();self.setCentralWidget(root);box=QVBoxLayout(root);box.setContentsMargins(50,50,50,50);box.addStretch()
        from . import __version__
        title=QLabel(f'MysticForge · {__version__}');title.setObjectName('heading');box.addWidget(title)
        text=QLabel('Final Fantasy Mystic Quest editor · Early alpha\n\nContinue a saved project, start a new one, or open another project.\nYour original ROM stays unchanged; export creates a separate copy.');text.setWordWrap(True);box.addWidget(text)
        self.resume_button=QPushButton('Continue last project');self.resume_button.clicked.connect(self.resume);box.addWidget(self.resume_button)
        project,_=last_session();self.resume_button.setVisible(bool(project));self.resume_button.setToolTip(project)
        self.open_button=QPushButton('New Project…');self.open_button.clicked.connect(self.new_project);box.addWidget(self.open_button)
        self.project_button=QPushButton('Open Project…');self.project_button.clicked.connect(self.open_project);box.addWidget(self.project_button)
        self.status=QLabel('');self.status.setWordWrap(True);box.addWidget(self.status);box.addStretch()
    def start(self):
        if self.rom_path:self.load_rom(Path(self.rom_path));return
        project,rom=last_session()
        if project and rom:
            if Path(project).is_file() and Path(rom).is_file():self.load_rom(Path(rom),Path(project));return
            self.status.setText('Your last project or its original ROM has moved. Choose Continue last project to locate it, or start/open another project.')
    def find_rom(self):
        _,remembered=last_session()
        for candidate in (self.rom_path,remembered,application_dir()/'Final Fantasy - Mystic Quest (USA).sfc'):
            if candidate and Path(candidate).is_file():return Path(candidate)
        return self.choose_rom_path()
    def choose_rom_path(self):
        name,_=QFileDialog.getOpenFileName(self,'Select original unheadered USA v1.0 ROM',str(application_dir()),'SNES ROM (*.sfc *.smc)')
        if name:return Path(name)
        self.status.setText('No ROM selected. Your project has not been changed.');return None
    def choose_rom(self):
        path=self.choose_rom_path()
        if path:self.load_rom(path)
    def new_project(self):
        path=self.find_rom()
        if path:self.load_rom(path)
    def open_project(self):
        name,_=QFileDialog.getOpenFileName(self,'Open project',str(user_directory()),'FFMQ project (*.json)')
        if not name:return
        path=self.find_rom()
        if path:self.load_rom(path,Path(name))
    def resume(self):
        project,rom=last_session()
        if not project or not Path(project).is_file():self.open_project();return
        path=Path(rom) if rom and Path(rom).is_file() else self.choose_rom_path()
        if path:self.load_rom(path,Path(project))
    def load_rom(self,path,project_path=None):
        from .app import MainWindow
        from .project import Project
        self.open_button.setEnabled(False);self.status.setText('Loading project…' if project_path else 'Loading ROM…')
        editor=None
        try:
            rom=Rom(path)
            project=Project.load(rom,project_path) if project_path else None
            editor=MainWindow(rom)
            if project is not None:
                editor.project=project;editor.area_id=project.area_id;editor.stack.clear()
                editor.select_area(project.area_id);editor.preset.setCurrentText('Custom');editor.refresh();editor.fit_views()
            self.editor=editor;editor.show()
            if project is not None:remember_project(project)
            self.close()
            if project is None:
                from .expansion_editor import show_expansion
                show_expansion(editor,startup=True)
        except Exception as error:
            if editor is not None:editor.stack.setClean();editor.close();editor.deleteLater()
            self.editor=None
            self.status.setText('Could not open saved work. Use Open Project to choose a project, or New Project to start again.')
            QMessageBox.warning(self,'Could not open project' if project_path else 'Could not open ROM',str(error))
        finally:self.open_button.setEnabled(True)
