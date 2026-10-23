# Compact view: one line per SET_REPORT write/preview/save command, grouped by burst.
import struct, sys, datetime
HS=64; d=open(sys.argv[1],'rb').read(); i=0; ev=[]
while i+HS<=len(d):
    (uid,typ,xt,ep,dev,bus,fs,fd,sec,usec,st,ln,lc)=struct.unpack_from('<QBBBBHccqiiII',d,i)
    ev.append((chr(typ),xt,sec+usec/1e6,d[i+40:i+48] if fs==b'\0' else None,d[i+HS:i+HS+lc])); i+=HS+lc
last=0
for typ,xt,t,setup,data in ev:
    if typ!='S' or xt!=2 or not setup or setup[0]!=0x21: continue
    if t-last>3: print('----', datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S'))
    last=t
    cmd=data[1]
    if cmd==2:
        addr,ln=struct.unpack_from('<HH',data,2)
        print(f'  WRITE 0x{addr:04x} len {ln:3d} (rep {data[0]}): {data[8:8+ln].hex(" ")}')
    elif cmd==3: pass
    else: print(f'  CMD {cmd:02x}: {data[2:8].hex(" ")}')
