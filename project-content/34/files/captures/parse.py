import struct, sys
HS=64
d=open(sys.argv[1],'rb').read(); i=0; ev=[]
while i+HS<=len(d):
    (uid,typ,xt,ep,dev,bus,fs,fd,sec,usec,st,ln,lc)=struct.unpack_from('<QBBBBHccqiiII',d,i)
    setup=d[i+40:i+48]; data=d[i+HS:i+HS+lc]; i+=HS+lc
    ev.append(dict(id=uid,t=sec+usec/1e6,typ=chr(typ),xt=xt,ep=ep,st=st,ln=ln,setup=setup if fs==b'\0' else None,data=data))
pend={}; xfers=[]
for e in ev:
    if e['typ']=='S': pend[e['id']]=e
    else:
        s=pend.pop(e['id'],None)
        if s: xfers.append((s,e))
t0=xfers[0][0]['t']; last=t0
full='-v' in sys.argv
for s,c in xfers:
    if s['t']-last>3: print('-'*20, f'gap {s["t"]-last:.0f}s')
    last=s['t']
    if s['xt']==1:
        print(f'{s["t"]-t0:8.3f} INT ep84 <- {c["data"].hex(" ")}'); continue
    rt,req,wv,wi,wl=struct.unpack('<BBHHH',s['setup'])
    kind={(0x21,9):'SET_REPORT',(0xa1,1):'GET_REPORT'}.get((rt,req),f'rt{rt:02x} req{req:02x}')
    rtype={1:'in',2:'out',3:'feat'}.get(wv>>8,'?')
    payload=s['data'] if rt&0x80==0 else c['data']
    nz=len(payload.rstrip(b'\0')) if not full else len(payload)
    show=payload[:max(nz,8)]
    print(f'{s["t"]-t0:8.3f} {kind} {rtype} id={wv&0xff} if={wi} len={wl} st={c["st"]} actual={c["ln"]}')
    lim = len(show) if full else min(len(show), 96)
    for o in range(0,lim,32):
        print(f'           {o:04x} '+show[o:o+32].hex(' '))
    if lim<len(show): print(f'           ... ({len(show)} bytes until last nonzero)')
