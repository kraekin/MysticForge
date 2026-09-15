"""Small, conservative constant store. Never executes game code or reads a save."""
MEMORY=0x1000000

def ram_address(address):
    bank=address>>16;offset=address&65535
    if bank==0x7e:return offset
    if bank in range(0x40) and offset<0x2000:return offset
    return None

def known_bytes(context,address,length):
    address=ram_address(address)
    if address is None or length>256:return None
    values=[context.get(MEMORY+address+i) for i in range(length)]
    return None if any(v is None for v in values) else bytes(values)

def writes(raw,working):
    if raw[0] in (0x0c,0x0d,0x0e):return int.from_bytes(raw[1:3],'little'),raw[3:]
    if raw[:2] in (b'\x05\xf0',b'\x05\xf1',b'\x05\xf2'):return int.from_bytes(raw[2:5],'little'),raw[5:]
    if raw[:2] in (b'\x05\x27',b'\x05\x29',b'\x05\x2b') and working is not None:return working,raw[2:]
    return None

def update_memory(context,raw,working):
    result=writes(raw,working)
    # Retain bytes only across a tiny verified set of register/config commands.
    safe=(raw[0]==5 and raw[1] in (0x3b,0x3c,0x3d,0x40,0xed,0xee,0xef,0x6b,0x6c)) or raw[0] in (4,0x13,0x14)
    if result is None and not safe:
        for key in list(context):
            if key>=MEMORY:context.pop(key)
    if result is not None:
        address,payload=result;address=ram_address(address)
        if address is None:
            for key in list(context):
                if key>=MEMORY:context.pop(key)
        else:
            # The working register aliases RAM. A write there invalidates it.
            for i,byte in enumerate(payload):context[MEMORY+address+i]=byte
            if len(context)>512:
                for key in list(context):
                    if key>=MEMORY:context.pop(key)

def interaction_note(raw,working):
    result=writes(raw,working)
    if result is None:return None
    address,payload=result;address=ram_address(address)
    if address is None:return None
    notes=[]
    for i,value in enumerate(payload):
        at=address+i
        if 0x1a81<=at<0x1a81+26*29 and (at-0x1a81)%26==0:
            notes.append(f'Assign runtime actor {(at-0x1a81)//26} interaction reference ${value:02X}; interaction class and map-object identity depend on runtime state')
        elif at==0x19e6:notes.append(f'Set current interaction reference to ${value:02X}')
    return '; '.join(notes) or None
