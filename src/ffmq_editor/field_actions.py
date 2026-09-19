"""Native v1.0 field commands; parameters are not event bytecode addresses.

Evidence and remaining semantic limits: research/FIELD_BEHAVIOR_INSPECTOR.md.
"""
DIRECTIONS=('up','right','down','left')

def field_action(action,value):
    sub,slot=value>>4,value&15
    obj=f'runtime object slot {slot}'
    reference=f' · reference ${value:02X}'
    if action in (0,1,2,3,4,5,6,8):
        return {0:'Enter area (destination A)',1:'Enter area (destination B)',2:'Warp',3:'Return to saved position',4:'Enter area (destination A)',5:'Warp',6:'Long area transition',8:'Run world entry event'}[action]+reference
    if action in (7,9,10,11,12,16,30,31) or 0x60<=action<=0x6f:
        return 'No field operation'+reference
    if action in (0x22,0x2a):return f'Apply map change ${value:02X}'+(' and refresh terrain' if action==0x2a else '')
    if action in (0x23,0x2b):return f'Copy metatile definitions · copy list ${value:02X}'+(' and refresh terrain' if action==0x2b else '')
    if action==0x25:
        if value in (4,5,6,9,10,11,12,13,15,16,17,23,26,41):return 'No scene operation'+reference
        names={2:'Queue native visual effect $F5 / mode $03',
               0x14:'Queue native visual effect $81 / mode $80 and wait',
               0x2b:'Coordinated two-object movement: 12 steps up, then 4 right; finish facing down',
               0x2c:'Coordinated two-object movement: 3 steps right, then 2 up',
               0x2d:'Scripted player traversal: clear flag $54, follow built-in route, set flag $55',
               0x2e:'Scripted player traversal: clear flag $55, follow built-in route, set flag $54'}
        if value in names:return names[value]+reference
        return 'Native scene routine (visual meaning not verified)'+reference
    if 0x70<=action<=0x7f:
        if value==4:return 'Service one field update / frame'
        if value==5:return 'Update objects and wait for next field frame'
        return 'Native player scene routine (meaning not fully verified)'+reference
    if action==0x26:return f'Send music command · track ${value&31:02X}'
    if action==0x27:return f'Play sound effect ${value:02X}'
    if action==0x29:return f'Set current area ID to ${value:02X} (does not load the map itself)'
    if action==0x2c:return f'Set runtime object slot {value} facing right and refresh its sprite'
    if action==0x20:
        names={0:'Shake screen horizontally',11:'Shake screen horizontally',3:'Fade screen to black',4:'Fade screen to black',5:'Fade screen to black',6:'Fade screen in',7:'Fade screen in',8:'Fade screen in',1:'No field operation',9:'No field operation',10:'No field operation',12:'No field operation'}
        if value in names:return names[value]
    if 0x40<=action<=0x43 or 0x47<=action<=0x4e or 0x50<=action<=0x53 or 0x57<=action<=0x5e:
        player=action>=0x50
        direction=DIRECTIONS[(action&3) if (action&15)<=3 else ((action+1)&3)]
        mode=action&15
        style='' if mode<=3 else ' (preserve facing)' if mode<=10 else ' (alternate movement animation)'
        count=f'{sub} tile(s)' if sub else 'zero count — native counter underflows'
        return f'Move {"player" if player else obj} {direction} · {count}'+style
    if action in (0x44,0x54):
        who='player' if action==0x54 else obj
        if sub<4:return f'Turn {who} {DIRECTIONS[sub]}'
        if sub<8:return f'Play directional pose for {who} facing {DIRECTIONS[sub&3]}, then restore facing'
        return f'Play pose ${sub:X} for {who} (pose meaning not verified)'
    if action in (0x45,0x55):
        who='player' if action==0x55 else obj
        if sub in (4,5,6,7):return 'No field operation'+reference
        if sub<4 or 8<=sub<12:
            return f'Show sprite effect {"A" if sub<4 else "B"} beside {who} · position {sub&3} (effect artwork not named)'
        if sub==13:return f'Spin {who} through all four directions'
        if sub==14:return f'Lift {who} 24 pixels, spin, then lower back'
    if action==0x46:
        if sub<3:return f'Set {obj} movement speed to {(1,2,4)[sub]} pixels per update'
        names={3:'Show',4:'Hide',5:'Show with sprite disabled for',6:'Hide and release sprite for',7:'Play native effect $3E for',8:'Disable sprite for',9:'Enable sprite for',10:'No operation for',13:'No operation for',14:'No operation for'}
        if sub in names:return f'{names[sub]} {obj}'
    if action==0x56:
        if sub<3:return f'Set player movement parameter to {sub+1} (speed interpretation not verified)'
        names={3:'Disable player sprite',5:'Disable player sprite',4:'Restore player sprite',6:'Restore player sprite',7:'Set player pose $10',8:'No field operation',9:'Set game flag $F5 and refresh player pose',10:'Clear game flag $F5 and refresh player pose'}
        if sub in names:return names[sub]
    family='Object action' if 0x40<=action<0x50 else 'Player action' if 0x50<=action<0x60 else 'Field action'
    return f'{family} ${action:02X} (meaning not verified)'+reference
