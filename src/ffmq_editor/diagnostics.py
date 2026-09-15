"""Small persistent diagnostic log for a console-free alpha build."""
import logging,sys,platform
from logging.handlers import RotatingFileHandler
from .paths import recovery_directory

def install():
    folder=recovery_directory().parent/'logs';folder.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(folder/'editor.log',maxBytes=1000000,backupCount=2,encoding='utf-8')
    logging.getLogger('mysticforge').addHandler(handler);logging.getLogger('mysticforge').setLevel(logging.INFO)
    logging.getLogger('mysticforge').info('Startup: Python %s, %s',platform.python_version(),platform.platform())
    def report(kind,value,tb):
        logging.getLogger('mysticforge').error('Unhandled error',exc_info=(kind,value,tb))
        from PySide6.QtWidgets import QMessageBox,QApplication
        QMessageBox.critical(QApplication.activeWindow(),'Unexpected error',f'{value}\n\nDiagnostic log: {folder / "editor.log"}')
    sys.excepthook=report

def show(w):
    from PySide6 import __version__
    from PySide6.QtWidgets import QMessageBox,QApplication
    from . import __version__
    text=f'MysticForge {__version__} · early alpha\nPython: {platform.python_version()}\nPySide6: {__version__}\nPlatform: {platform.platform()}\nROM: USA v1.0\nLogs: {recovery_directory().parent / "logs"}\nRecovery: {recovery_directory()}'
    box=QMessageBox(w);box.setWindowTitle('Diagnostics');box.setText(text);copy=box.addButton('Copy diagnostics',QMessageBox.ButtonRole.ActionRole);box.addButton(QMessageBox.StandardButton.Close);box.exec()
    if box.clickedButton()==copy:QApplication.clipboard().setText(text)
