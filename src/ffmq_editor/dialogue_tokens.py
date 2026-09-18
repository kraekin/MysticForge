"""Common token insertion and illustrative text preview for dialogue editors."""
import re
from PySide6.QtWidgets import QComboBox, QPushButton
from .event_editing import SPECIAL, NAME_OPS, atomize
from .events import inline_name


def add_token_picker(row, editor, rom):
    picker=QComboBox();picker.setObjectName('dialogueTokenPicker')
    picker.setMinimumContentsLength(18)
    picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    for token in SPECIAL:picker.addItem(token,token)
    for text in ('“','”','…'):picker.addItem('Punctuation: '+text,text)
    for name,(op,count) in NAME_OPS.items():
        for i in range(count):
            picker.addItem(f'{name}: {inline_name(rom,op,i) or i} (${i:02X})',f'[{name}:{i:02X}]')
    picker.setToolTip('Names come from the game. Hero and companion use the current party; Number uses the current runtime number buffer.')
    button=QPushButton('Insert name / token');button.setObjectName('insertDialogueToken')
    button.setToolTip('Insert at the text cursor, replacing selected text. Undo restores the previous text.')
    def insert():
        editor.insertPlainText(picker.currentData());editor.setFocus()
    button.clicked.connect(insert);row.addWidget(picker,1);row.addWidget(button)
    return picker,button


def preview_text(rom,text):
    def resolve(m):
        name,i=m[1],int(m[2],16)
        return (inline_name(rom,NAME_OPS[name][0],i) if i<NAME_OPS[name][1] else None) or m[0]
    text=re.sub(r'\[(Character|Item|Location|Enemy):([0-9A-Fa-f]{2})\]',resolve,text)
    return re.sub(r'\[(?:Glyph|Draw glyph):([0-9A-Fa-f]{2})\]',r'[\1]',text).replace('[Spacing]',' ').replace('[Line break or space]','[line break or space]')


def wrap_text(rom,text,width=28):
    """Preserve whole tokens and existing newlines; runtime names reserve 8 cells."""
    result=[]
    for line in text.split('\n'):
        words=[];word=[]
        for atom in atomize(line):
            if atom==' ':
                if word:words.append(word);word=[]
            else:word.append(atom)
        if word:words.append(word)
        current='';used=0
        for word in words:
            def cells(a):
                if a in ('[Hero name]','[Companion name]','[Number]'):return 8
                if a.startswith(('[Glyph:', '[Draw glyph:')):return 1
                if a=='[Line break or space]':return 1
                return len(preview_text(rom,a))
            size=sum(cells(a) for a in word)
            if current and used+1+size>width:result.append(current);current='';used=0
            for index,a in enumerate(word):
                n=cells(a)
                if current and used+n+(1 if index==0 else 0)>width and size>width:
                    result.append(current);current='';used=0
                if index==0 and current:current+=' ';used+=1
                current+=a;used+=n
        result.append(current)
    return '\n'.join(result)
