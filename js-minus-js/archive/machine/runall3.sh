cd /root/vm
for c in 8_32 12_24 16_32 8_16; do GC=1 nohup node fullrun.js f4_$c.html 15 > r4_$c.log 2> r4_$c.err; done
