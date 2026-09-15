"""Vanilla v1.0 overworld route records and gate flags."""
from dataclasses import dataclass
from .rom import pc,read,u16,FormatError

DIRECTIONS=("Up","Right","Down","Left")
DELTAS=((0,-1),(1,0),(0,1),(-1,0))

@dataclass(frozen=True)
class Route:
    node:int
    direction:int
    offset:int
    size:int

def inventory(data):
    result=[]
    for node in range(1,57):
        cursor=pc(0x070000|u16(data,pc(0x07F011)+(node-1)*2))
        for direction in range(4):
            start=cursor;destination=read(data,cursor,1)[0];cursor+=1
            if destination>56:raise FormatError("Invalid overworld route destination")
            while destination and read(data,cursor,1)[0]&128:
                cursor+=1
                if cursor-start>128:raise FormatError("Unterminated overworld route")
            result.append(Route(node,direction,start,cursor-start))
    return tuple(result)

def position(project,node):return tuple(project.fixed("world_node",node))

def points(project,route,raw=None):
    raw=project.fixed("world_route",route.offset) if raw is None else raw
    x,y=position(project,route.node);result=[(x,y)]
    for step in raw[1:]:
        dx,dy=DELTAS[(step>>5)&3]
        # The engine's byte decrement makes a zero count mean 256 steps.
        for _ in range((step&31) or 256):
            x=(x+dx)%64;y=(y+dy)%48;result.append((x,y))
    return tuple(result)

def validate(project,route,raw):
    if len(raw)!=route.size:raise FormatError("Route must retain its original segment count; expansion is not enabled")
    if raw[0]>56 or any(step<128 or step&31==0 for step in raw[1:]):raise FormatError("Invalid route node or segment length (use 1–31)")
    if raw[0]==0:
        if len(raw)>1:raise FormatError("Disable a route with gate flag 0, preserving its destination and steps")
    elif points(project,route,raw)[-1]!=position(project,raw[0]):
        raise FormatError("Route endpoint does not match the destination node; adjust its steps or destination")

def gate(project,route):return project.fixed("world_gate",route.node)[route.direction]

def available(project,route):
    flag=gate(project,route)
    return bool(flag and flag in project.flags and project.fixed("world_route",route.offset)[0])
