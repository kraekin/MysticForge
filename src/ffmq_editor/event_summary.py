"""Conservative summaries, not execution or a proof that an event completes."""
from dataclasses import dataclass
from .events import decode
from .event_presentation import readable_rows,Dialogue,technical_setup,literal_text

@dataclass(frozen=True)
class Summary:
    opening:tuple
    possible:tuple
    conditions:tuple
    notes:tuple

    def plain(self):
        sections=[('On entry — before the first branch or unexpanded call',self.opening),
                  ('Possible actions — branches and called events',self.possible),
                  ('Conditions checked',self.conditions),('Inspection limits',self.notes)]
        return '\n\n'.join(title+'\n'+'\n'.join('• '+line for line in lines) for title,lines in sections if lines)

def summarize(rom,entry,extent=None):
    rows=[];pending=[(entry,extent)];visited=set()
    while pending and len(rows)<4096:
        target,bound=pending.pop(0)
        if (target,bound) in visited:continue
        visited.add((target,bound))
        batch=decode(rom,target,limit=4096-len(rows),follow_calls=False,extent=bound)
        rows.extend(batch)
        for row in batch:
            # Reconstructed literal fragments and name inserts already appear
            # in dialogue. Do not list their implementation as extra messages.
            if literal_text(rom,row.raw) is not None:continue
            for kind,address in row.edges:
                if kind in ('call','fragment','bounded'):
                    pending.append((address,row.raw[-1] if kind=='bounded' else None))
    by_address={r.address:r for r in rows};prefix=set();cursor=entry
    while cursor in by_address and cursor not in prefix:
        row=by_address[cursor];prefix.add(cursor)
        # Literal dictionary references are safe to summarize as dialogue.
        if not row.complete or (any(k!='next' for k,_ in row.edges) and literal_text(rom,row.raw) is None):break
        nexts=[v for k,v in row.edges if k=='next']
        if not nexts:break
        cursor=nexts[0]
    opening=[];possible=[];conditions=[];notes=[];seen=set()
    for row in readable_rows(rom,rows):
        if isinstance(row,Dialogue):
            text='Dialogue: “'+row.text+'”'
            certain=all(r.address in prefix for r in row.instructions)
        else:
            text=row.description;certain=row.address in prefix
            if not row.complete:notes.append(f'${row.address:06X}: {text}')
            if text.startswith(('If ','Conditional call')):
                conditions.append(text);continue
            if technical_setup(row) or text.startswith(('End / return','Go to branch','Call event','Shared text/event fragment','Text spacing','New line','Blank line')):continue
        key=(text,certain)
        if key in seen:continue
        seen.add(key);(opening if certain else possible).append(text)
    notes.insert(0,'Static overview: possible actions are not a play order or guaranteed outcomes. Calls, loops, input and native routines can prevent continuation. Runtime values remain symbolic; no game state is changed.')
    if pending:notes.append('Summary inspection limit reached; additional called events are not included.')
    if any(r.raw[:1]==b'\x09' or 'native assembly' in r.description for r in rows):
        notes.append('Native assembly side effects are not expanded into this summary.')
    return Summary(tuple(opening),tuple(possible),tuple(dict.fromkeys(conditions)),tuple(dict.fromkeys(notes)))
