"""Evidence for area configurations. Room/story names are never inferred from IDs."""
from pathlib import Path
import json
from itertools import product
import numpy as np
from .connections import Connections
from .event_editing import index

CURATED={
    **{i:(f'Base background ${i:02X}',
        'Same terrain and default appearance as $02-$04. No area-specific metatile replacement. Gameplay purpose is not established.',
        'USA 1.0: shared area record; empty per-area action lists at $06:BE77/$06:BEE3/$06:BF15.') for i in (2,3,4)},
    5:('Ocean background',
       'Uses the shared background terrain with an initial-state metatile replacement, producing the ocean appearance.',
       'USA 1.0: area $05 action (flag $00, replacement $09, opcode $23); 13 metatile replacements. Gameplay purpose is not established.'),
    16:('Kaeli’s house','Loads the NPCs and objects for Kaeli’s house.','User gameplay identification; ROM entry/object data audited.'),
    17:('Other Foresta houses','Loads the objects used by the other Foresta houses.','User gameplay identification; ROM entry/object data audited.'),
    24:('Frozen Aquaria','Frozen Aquaria area record.','Verified restoration mapping; see RESTORATION_STATES.md.'),
    25:('Thawed Aquaria','Thawed Aquaria area record.','Verified restoration mapping; see RESTORATION_STATES.md.'),
}

def audit(p):
    """All areas, concrete transitions in sampled states, and decoded field calls.

    Samples are evidence of a transition, not proof of its complete predicate.
    In particular this does not simulate event execution or saved-return warps.
    """
    rom=p.rom;c=Connections(rom);c.project=p
    rows={a.id:{'id':a.id,'map':a.name,'layout':a.layout_id,'record_offset':a.offset,
                'header':a.header.hex(),'object_count':len(p.objects(a.id)),
                'object_positions':[[o[3]&63,o[2]&63] for o in p.objects(a.id)],
                'restoration_actions':[{'flag':r.flag,'opcode':r.opcode,'value':r.value} for r in rom.area_actions[a.id]],
                'incoming':[],'unresolved_outgoing':[]} for a in rom.areas}
    incoming={a.id:{} for a in rom.areas}
    for area in rom.areas:
        base=set(rom.initial_flags);profiles={tuple(sorted(base)):'Initial'}
        for bits in product((False,True),repeat=4):
            flags=(base-{1,2,3,5})|{f for f,on in zip((1,2,3,5),bits) if on}
            profiles.setdefault(tuple(sorted(flags)),'Restoration flags '+','.join(f'{f:02X}' for f in (1,2,3,5) if f in flags))
        for f in {4,0x13}|{r.flag for r in rom.area_actions[area.id]}:
            profiles.setdefault(tuple(sorted(base^{f})),f'Initial with flag ${f:02X} toggled')
        unresolved=set()
        for flags,label in profiles.items():
            pflags=p.flags;p.flags=set(flags)
            try:
                state=p.state(area.id);props=np.frombuffer(p.fixed('properties',p.tileset(area.id)),dtype=np.uint8).reshape(128,2).copy()
                for dst,src in state.remaps:props[dst]=props[src]
                connections=c.for_area(area.id,state,props)
            finally:p.flags=pflags
            for e in connections:
                if e.target is None or e.source is None:
                    unresolved.add((e.x,e.y,e.action,e.value));continue
                target,x,y,facing=e.target
                key=('entrance',area.id,e.x,e.y,x,y,e.action,e.value)
                record=incoming[target].setdefault(key,{'kind':'entrance','source_area':area.id,'source_xy':[e.x,e.y],
                    'arrival':[x,y],'action':e.action,'value':e.value,'samples':[]})
                record['samples'].append(label)
        rows[area.id]['unresolved_outgoing']=[list(e) for e in sorted(unresolved)]
    # These decoded words are structural evidence only; branches/callers decide
    # whether gameplay executes them. Set-area-ID is not an entrance operation.
    for row in index(p).rows.values():
        words=[row.raw[1:3]] if row.raw[:1]==b'\x2c' else [row.raw[i:i+2] for i in range(1,len(row.raw)-2,2)] if row.raw[:1]==b'\x2a' and row.complete else []
        for word in words:
            if len(word)!=2 or word[1] not in (0,1,2,4,5,6):continue
            dest=c.destination(word[1],word[0])
            if dest is None:continue
            target,x,y,_=dest
            incoming[target].setdefault(('event',row.address,word.hex()),{'kind':'event','address':row.address,'arrival':[x,y],'action':word[1],'value':word[0]})
    for area in rom.areas:
        r=rows[area.id];r['incoming']=list(incoming[area.id].values())
        members=rom.shared_areas(area.layout_id);r['shares_layout_with']=[i for i in members if i!=area.id]
        r['same_record_as']=[a.id for a in rom.areas if a.offset==area.offset and a.id!=area.id]
        r['differences']={str(i):{'header_bytes':[j for j,(a,b) in enumerate(zip(area.header,rom.areas[i].header)) if a!=b],
            'object_list_differs':p.objects(area.id)!=p.objects(i)} for i in members if i!=area.id}
        if area.id in CURATED:r['name'],r['meaning'],r['evidence']=CURATED[area.id]
        else:
            r['name']=f'Object set {members.index(area.id)+1}' if len(members)>1 else area.name
            if r['same_record_as']:r['name']=f'Shared record ${area.id:02X}'
            r['meaning']='Purpose not yet named. Entry links and object differences are available below.' if len(members)>1 else 'Single area setup for this terrain.'
            r['evidence']='ROM records and static transitions; room/story purpose unverified.'
            sources=sorted({rom.areas[e['source_area']].name for e in r['incoming'] if e['kind']=='entrance' and rom.areas[e['source_area']].layout_id!=area.layout_id})
            if sources:r['meaning']='Static entry links from '+', '.join(sources)+'. Room/story purpose has not been named.'
            if r['same_record_as']:r['meaning']='Shares its exact area record and object list with '+', '.join(f'${i:02X}' for i in r['same_record_as'])+'. Entry coordinates may differ; the purpose of each ID is not established.'
            r['external_sources']=sources
    # Use a source name only when it distinguishes this setup within its map.
    for r in rows.values():
        sources=r.get('external_sources',[])
        if len(sources)==1 and not r['same_record_as'] and r['shares_layout_with'] and all(rows[i].get('external_sources')!=sources for i in r['shares_layout_with']):r['name']='From '+sources[0]
    return {'base_sha256':p.base_rom.sha256,'scope':'All original area records; 16 restoration combinations plus individual relevant flag toggles. Samples do not prove all runtime conditions.', 'areas':list(rows.values())}

def catalogue():
    path=Path(__file__).with_name('data')/'map_setups.json'
    return {r['id']:r for r in json.loads(path.read_text(encoding='utf-8'))['areas']}

_catalogue=None
def info(p,area_id):
    global _catalogue
    if _catalogue is None:_catalogue=catalogue()
    r=dict(_catalogue.get(area_id,{'name':p.rom.areas[area_id].name,'meaning':'Custom map setup.','evidence':'Project-defined map.'}))
    custom=p.setup_labels.get(area_id)
    if custom:r.update(name=custom[0],meaning=custom[1],evidence='Project label; not a claim about original gameplay.')
    return r

def validate(p):
    if not isinstance(p.setup_labels,dict):raise ValueError('Invalid map setup labels')
    for i,value in p.setup_labels.items():
        if type(i) is not int or not 0<=i<len(p.rom.areas) or not isinstance(value,(tuple,list)) or len(value)!=2 or any(not isinstance(s,str) for s in value) or not value[0].strip() or len(value[0])>80 or len(value[1])>400:raise ValueError('Invalid map setup label')
