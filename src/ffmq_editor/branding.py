"""MysticForge release identity and About window."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton
from . import __version__
ICON=Path(__file__).with_name('data')/'mysticforge.ico'
LOGO=ICON.with_suffix('.png')

def about(w):
    dialog=QDialog(w);dialog.setWindowTitle('About MysticForge');dialog.resize(630,530)
    box=QVBoxLayout(dialog);box.setContentsMargins(32,28,32,24);box.setSpacing(18)
    hero=QHBoxLayout();logo=QLabel();logo.setPixmap(QPixmap(str(LOGO)).scaled(112,112,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));hero.addWidget(logo)
    titles=QVBoxLayout();name=QLabel('MysticForge');name.setStyleSheet('font-size: 34px; font-weight: 700; color: #a5f2f5;');titles.addWidget(name)
    titles.addWidget(QLabel('Build your own Mystic Quest.'))
    badge=QLabel(f'EARLY ALPHA  ·  {__version__}');badge.setStyleSheet('color: #ffd083; font-weight: bold;');titles.addWidget(badge);hero.addLayout(titles,1);box.addLayout(hero)
    for text in ('A map and game-data editor for Final Fantasy Mystic Quest. Explore terrain, objects, connections, shared graphics, and game events.',
                 'Supports the original unheadered USA v1.0 ROM. Save your work as a project and export a separate ROM copy. Event and script editing is very early, but mostly works.',
                 'This is an early alpha. Automated checks and focused in-game testing do not replace a full playthrough. Keep backups of your projects and saves.'):
        label=QLabel(text);label.setWordWrap(True);box.addWidget(label)
    credits=QLabel('Created by Kraekin with AI-assisted development.<br><br>Research acknowledgments: <a style="color:#8de4ed" href="https://github.com/TheAnsarya/ffmq-info">TheAnsarya / ffmq-info</a> and <a style="color:#8de4ed" href="https://github.com/wildham0/FFMQRando">wildham0 / FFMQRando</a>.<br>Built with Python, PySide6, and NumPy. Original map-and-crystal application icon.');credits.setWordWrap(True);credits.setOpenExternalLinks(True);box.addWidget(credits)
    row=QHBoxLayout();row.addStretch();close=QPushButton('Close');close.clicked.connect(dialog.close);row.addWidget(close);box.addLayout(row)
    w.about_dialog=dialog;dialog.show();return dialog
