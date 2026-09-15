"""Explicit packaged-build smoke test; never modifies the supplied ROM."""
import json,tempfile,sys
from pathlib import Path

def run(rom_path,report_path):
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow,configure_app
    from .startup import WelcomeWindow
    from .rom import Rom
    from .project import Project
    from .dialogue_preview import FONT
    app=QApplication.instance() or QApplication([]);configure_app(app)
    welcome=WelcomeWindow();welcome.show();app.processEvents()
    result={'welcome_visible':welcome.isVisible(),'font_bytes':len(FONT.read_bytes())}
    rom=Rom(Path(rom_path));w=MainWindow(rom);w.show();app.processEvents();welcome.close()
    from .metatile_editor import open_metatiles
    from .database_editor import open_database
    open_metatiles(w);open_database(w);app.processEvents()
    result.update(maps=len(rom.areas),metatiles=w.metatile_window.metatiles.count(),database_records=w.database_window.records.count())
    key=('metatile_attributes',2,0);old=w.project.get(key);w.commit_changes({key:(old,old^1)},'Packaged smoke test')
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);w.project.save(p/'test.json');loaded=Project.load(rom,p/'test.json');loaded.export(p/'test.sfc')
        result['project_roundtrip']=loaded.edits==w.project.edits
        result['export_bytes']=(p/'test.sfc').stat().st_size
    w.database_window.close();w.metatile_window.close();w.stack.setClean();w.close();app.processEvents()
    result['passed']=result['welcome_visible'] and result['font_bytes']==2048 and result['metatiles']==128 and result['project_roundtrip'] and result['export_bytes']==len(rom.data)
    Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
