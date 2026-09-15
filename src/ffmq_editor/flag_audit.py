"""Project-aware flag dossiers. Evidence is descriptive, not inferred story lore."""
from dataclasses import dataclass,field
from pathlib import Path
import json
from .event_flags import NAMES,flag_label
from .field_actions import field_action
from .rom import pc,u16
from .world import gate,DIRECTIONS

@dataclass(frozen=True)
class Evidence:
    kind:str
    action:str
    explanation:str
    source:str
    target:tuple|None=None
    context:str=''

@dataclass
class Dossier:
    flag:int
    initial:bool
    evidence:list=field(default_factory=list)

    @property
    def status(self):
        return 'Verified story meaning' if self.flag in NAMES else 'Verified uses; story meaning unknown' if self.evidence else 'Unknown — no indexed uses'

    @property
    def overview(self):
        if self.flag in NAMES:return NAMES[self.flag]+'. This is a verified vanilla restoration flag.'
        if self.flag==0x13:return 'Selects between the two Level Forest entrance variants. The broader story meaning is not established.'
        if self.flag==4:return 'Selects between Spencer’s Cave and a different cave area for world entry $30. This is a verified entrance use, not a complete story-event name.'
        if self.flag==0xf2:return 'The monster-graphics loader checks this flag before loading the alternate graphics sheet for eligible map descriptors. It has other uses too; this is not a complete story-event name.'
        if self.flag==0xf5:return 'Native player actions set or clear this flag while refreshing the player pose. The complete gameplay meaning of the pose is not named.'
        if not self.evidence:return 'No use was found in the audited sources. This does not prove the flag is unused.'
        counts={kind:sum(e.kind==kind for e in self.evidence) for kind in ('Event','Object','Map','Route','Entrance','Native')}
        roles=[]
        if counts['Object']:roles.append(f'controls visibility for {counts["Object"]} area/object references')
        if counts['Map']:roles.append(f'gates {counts["Map"]} map-loading actions')
        if counts['Route']:roles.append(f'gates {counts["Route"]} overworld routes')
        if counts['Entrance']:roles.append('selects an entrance destination')
        if counts['Event']:roles.append('is checked or changed by event scripts')
        if counts['Native']:roles.append('is referenced by native engine code')
        return 'This flag '+', and '.join(roles)+'. These are observed uses, not a unique story-event name.'

    @property
    def search_text(self):
        return ' '.join([flag_label(self.flag),self.status,self.overview,*(e.explanation+' '+e.context+' '+e.action for e in self.evidence)]).lower()

    @property
    def next_step(self):
        if self.flag in NAMES:return 'The restoration meaning is established. Inspect individual sources to see which maps, objects and routes respond to it.'
        writers=[e for e in self.evidence if e.action in ('Set','Clear')]
        if writers:return 'Start with '+writers[0].explanation+' ('+writers[0].source+'). Follow its callers and compare nearby dialogue with the effects listed here before assigning a story name.'
        if self.evidence:return 'There is no explicit numbered Set/Clear in the indexed sources. Trace runtime-indexed callers and other native writes before assuming when this flag changes. Do not infer a story event from its initial value.'
        return 'Extend the native-code and runtime-generated-script audit. No indexed references does not establish that this bit is unused.'

class FlagAudit:
    def __init__(self,rom,project,catalog):
        self.dossiers=[Dossier(i,i in rom.initial_flags) for i in range(256)]
        self.notes=[];self.unresolved=[]
        for key,record in catalog.records.items():
            aliases=', '.join(sorted(record.aliases)) or f'Event ${record.address:06X}'
            parents='; '.join(sorted(r.label for r in record.references))
            dialogue='\n\n'.join(record.dialogues)
            context='Indexed callers: '+parents+('\nDialogue elsewhere in this event (association only, not proof of meaning):\n'+dialogue if dialogue else '')
            for use in record.flags:
                self.add(use.flag,'Event',use.action,f'{use.action} in {aliases}',f'CPU ${use.address:06X}',('event',key),context)
        for area in rom.areas:
            for index,obj in enumerate(project.objects(area.id)):
                kind=(obj[5]>>3)&3
                label={0:'NPC',1:'encounter',2:'chest',3:'object'}[kind]
                self.add(obj[0],'Object','Visibility',f'{area.name}: {label} ${index:02X} uses this visibility flag',
                         f'ROM file ${area.offset+8+index*7:06X}',('object',area.id,index),
                         'Set: passes the game-flag visibility test. Clear: fails that test. Collected/defeated state and scripts can still hide or move it. Runtime slots differ from map object IDs.')
            table=rom.data[pc(0x06BE77)+area.id]
            cursor=pc(0x06BF15)+u16(rom.data,pc(0x06BEE3)+2*table) if table<128 else 0
            for i,action in enumerate(rom.area_actions[area.id]):
                text=f'Use palette ${action.value:02X}' if action.opcode==0x24 else field_action(action.opcode,action.value)
                self.add(action.flag,'Map','When set',f'{area.name}: {text}',f'ROM file ${cursor+3*i:06X}',('map',area.id),
                         'The area loading action is gated by this flag. Other enabled actions may override its effect; this is not a full state simulation.')
        for route in rom.routes:
            flag=gate(project,route);destination=project.fixed('world_route',route.offset)[0]
            if not flag or not destination:continue
            self.add(flag,'Route','Unlock test',f'Overworld node ${route.node:02X} → ${destination:02X}, {DIRECTIONS[route.direction]}',
                     f'Route ROM file ${route.offset:06X}',('map',0),'Set: passes this route gate. Clear: blocks this route. Node IDs are not area IDs.')
        # These exact conditional entrance prefixes are already independently
        # verified by Connections; decode destinations using current project.
        from .connections import Connections
        connections=Connections(rom);connections.project=project
        for flag,event in ((0x13,0x2e),(4,0x30)):
            off=connections.destination(8,event,set());on=connections.destination(8,event,{flag})
            if off is None or on is None:continue
            def destination(d):return f'{rom.areas[d[0]].name}, area ${d[0]:02X}, ({d[1]}, {d[2]})'
            self.add(flag,'Entrance','Destination choice',f'Clear → {destination(off)}; set → {destination(on)}',
                     f'World event ${event:02X}',('event',(0x030000|u16(rom.data,pc(0x03BBD2)+event*2),None)),
                     'Verified entrance branch, not proof of the flag’s full story meaning.')
        native=json.loads((Path(__file__).with_name('data')/'flag_native_evidence.json').read_text())
        self.notes.append(native['scope'])
        helpers=native['helpers'];payload=bytes.fromhex(helpers['bytes'])
        valid=rom.sha256==native['rom_sha256'] and rom.data[pc(helpers['start']):pc(helpers['start'])+len(payload)]==payload
        for call in native['calls']:
            raw=bytes.fromhex(call['bytes']);start=pc(call['start'])
            if not valid or rom.data[start:start+len(raw)]!=raw:
                self.notes.append('Native evidence failed its local ROM byte guard and was omitted.');continue
            if call['flag'] is None:self.unresolved.append(call);continue
            self.add(call['flag'],'Native',call['action'],f'{call["action"]} from native engine code',f'CPU ${call["address"]:06X}',None,
                     call['explanation']+'\nSource: '+call['source']+f' at ${call["source_address"]:06X}\nMatched local bytes: '+raw.hex(' ').upper())
        self.notes.extend(['References count source uses and area aliases, not unique physical instructions.',
                           'Event inventory limits: '+'; '.join(catalog.notes) if catalog.notes else 'Event inventory completed within its configured limits; native routines and runtime-generated code are not exhaustively decoded.',
                           f'{len(self.unresolved)} verified native callers use a runtime flag index and are not assigned to numbered flags.',
                           'Item/context bits, chest collection and defeated-encounter bitfields are separate namespaces. They must not inherit these flag names.'])

    def add(self,flag,kind,action,explanation,source,target=None,context=''):
        self.dossiers[flag].evidence.append(Evidence(kind,action,explanation,source,target,context))

    def report(self):
        from dataclasses import asdict
        return {'notes':self.notes,'unresolved_native_callers':self.unresolved,'flags':[
            dict(asdict(d),status=d.status,overview=d.overview,next_step=d.next_step) for d in self.dossiers]}
