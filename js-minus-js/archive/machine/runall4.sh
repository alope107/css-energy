cd /root/vm
for f in b_f4fz48 b_f4fz32 b_fvmfz; do GC=1 DT=2000 IMG=direct.json node fullrun.js $f.html 3 > r5_$f.log 2> r5_$f.err; done
for f in b_f4 b_fvm; do GC=1 DT=5000 IMG=image.json node fullrun.js $f.html 12 > r5_$f.log 2> r5_$f.err; done
