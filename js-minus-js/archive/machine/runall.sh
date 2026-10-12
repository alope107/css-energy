cd /root/vm
for f in fvm_fizz fvm_fizz32 vm_fizz; do GC=1 DT=5000 IMG=direct.json node fullrun.js $f.html 20 > d_$f.log 2> d_$f.err; done
