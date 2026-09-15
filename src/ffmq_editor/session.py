"""Remember saved work only; autosaves never replace the startup project."""
from pathlib import Path
from PySide6.QtCore import QSettings

def settings():
    return QSettings('MysticForge','MysticForge')

def last_session():
    s=settings()
    return str(s.value('session/project','')),str(s.value('session/rom',''))

def remember_project(project):
    if not project.path:return
    s=settings();s.setValue('session/project',str(Path(project.path).resolve()))
    s.setValue('session/rom',str(project.base_rom.path.resolve()));s.sync()
