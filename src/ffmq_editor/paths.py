"""Locations independent of the source checkout and executable install folder."""
from pathlib import Path
import sys
from PySide6.QtCore import QStandardPaths


def application_dir():
    return Path(sys.argv[0]).resolve().parent


def user_directory():
    base=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    path=Path(base or str(Path.home()))/'MysticForge';path.mkdir(parents=True,exist_ok=True);return path


def recovery_directory():
    base=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    path=Path(base or str(Path.home()/'.mysticforge'))/'recovery';path.mkdir(parents=True,exist_ok=True);return path
