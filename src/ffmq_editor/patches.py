"""Deterministic BPS/IPS export with independent decoding for round-trip checks.
BPS specification: byuu, public domain. IPS uses classic PATCH records and EOF.
These readers validate our exports; they are not a public patch-import workflow.
"""
from zlib import crc32
from .rom import FormatError
MAX_OUTPUT=64*1024*1024


def number(value):
    if type(value) is not int or value<0:raise FormatError('Invalid BPS integer')
    result=bytearray()
    while True:
        low=value&127;value>>=7
        if not value:result.append(low|128);return bytes(result)
        result.append(low);value-=1


def create_bps(source,target,metadata=b''):
    result=bytearray(b'BPS1'+number(len(source))+number(len(target))+number(len(metadata))+metadata)
    i=0
    while i<len(target):
        same=i<len(source) and source[i]==target[i];start=i;i+=1
        while i<len(target) and (i<len(source) and source[i]==target[i])==same:i+=1
        result.extend(number(((i-start-1)<<2)|(0 if same else 1)))
        if not same:result.extend(target[start:i])
    result.extend(crc32(source).to_bytes(4,'little'));result.extend(crc32(target).to_bytes(4,'little'));result.extend(crc32(result).to_bytes(4,'little'))
    return bytes(result)


class Reader:
    def __init__(self,data,start,end):self.data=data;self.pos=start;self.end=end
    def take(self,count):
        if count<0 or self.pos+count>self.end:raise FormatError('Truncated patch')
        result=self.data[self.pos:self.pos+count];self.pos+=count;return result
    def integer(self):
        value=0;shift=1
        for _ in range(10):
            b=self.take(1)[0];value+=(b&127)*shift
            if b&128:return value
            shift<<=7;value+=shift
        raise FormatError('BPS integer is too large')


def apply_bps(source,patch):
    if len(patch)<19 or patch[:4]!=b'BPS1':raise FormatError('Invalid BPS header')
    if crc32(patch[:-4])!=int.from_bytes(patch[-4:],'little'):raise FormatError('BPS patch checksum mismatch')
    if crc32(source)!=int.from_bytes(patch[-12:-8],'little'):raise FormatError('BPS source ROM checksum mismatch')
    r=Reader(patch,4,len(patch)-12);source_size=r.integer();target_size=r.integer();metadata_size=r.integer()
    if source_size!=len(source):raise FormatError('BPS source size mismatch')
    if target_size>MAX_OUTPUT:raise FormatError('BPS output exceeds verifier limit')
    r.take(metadata_size);out=bytearray();source_cursor=target_cursor=0
    while len(out)<target_size:
        command=r.integer();length=(command>>2)+1;action=command&3
        if len(out)+length>target_size:raise FormatError('BPS action exceeds target size')
        if action==0:
            offset=len(out)
            if offset+length>len(source):raise FormatError('BPS source read is out of bounds')
            out.extend(source[offset:offset+length])
        elif action==1:out.extend(r.take(length))
        else:
            relative=r.integer();delta=-(relative>>1) if relative&1 else relative>>1
            if action==2:
                source_cursor+=delta
                if source_cursor<0 or source_cursor+length>len(source):raise FormatError('BPS source copy is out of bounds')
                out.extend(source[source_cursor:source_cursor+length]);source_cursor+=length
            else:
                target_cursor+=delta
                if target_cursor<0 or target_cursor>=len(out):raise FormatError('BPS target copy is out of bounds')
                for _ in range(length):out.append(out[target_cursor]);target_cursor+=1
    if r.pos!=r.end:raise FormatError('BPS has trailing actions')
    if crc32(out)!=int.from_bytes(patch[-8:-4],'little'):raise FormatError('BPS target checksum mismatch')
    return bytes(out)


def create_ips(source,target):
    if len(source)!=len(target):raise FormatError('IPS export currently requires an unchanged ROM size')
    if len(target)>1<<24:raise FormatError('ROM exceeds classic IPS address space')
    result=bytearray(b'PATCH');i=0
    while i<len(target):
        if source[i]==target[i]:i+=1;continue
        start=i
        # This byte offset spells EOF and cannot begin a record.
        if start==0x454f46:start-=1
        end=min(start+65535,len(target));i+=1
        while i<end and source[i]!=target[i]:i+=1
        data=target[start:i];result.extend(start.to_bytes(3,'big'))
        if len(data)>=4 and data.count(data[0])==len(data):
            result.extend(b'\0\0'+len(data).to_bytes(2,'big')+data[:1])
        else:result.extend(len(data).to_bytes(2,'big')+data)
    return bytes(result+b'EOF')


def apply_ips(source,patch):
    if len(patch)<8 or patch[:5]!=b'PATCH':raise FormatError('Invalid IPS header')
    out=bytearray(source);r=Reader(patch,5,len(patch))
    while True:
        address=r.take(3)
        if address==b'EOF':break
        offset=int.from_bytes(address,'big');size=int.from_bytes(r.take(2),'big')
        if size:data=r.take(size)
        else:
            count=int.from_bytes(r.take(2),'big')
            if not count:raise FormatError('Invalid zero-length IPS run')
            data=r.take(1)*count
        if offset+len(data)>len(out):raise FormatError('IPS record is outside this ROM')
        out[offset:offset+len(data)]=data
    if r.pos!=r.end:raise FormatError('Unexpected IPS trailing bytes')
    return bytes(out)


def verified_patch(source,target,kind,metadata=b''):
    if kind=='bps':patch=create_bps(source,target,metadata);actual=apply_bps(source,patch)
    elif kind=='ips':patch=create_ips(source,target);actual=apply_ips(source,patch)
    else:raise FormatError('Choose BPS or IPS')
    if actual!=target:raise FormatError('Patch verification failed: output differs from the ROM export')
    return patch
