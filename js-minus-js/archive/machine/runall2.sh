cd /root/vm
GC=1 DT=2000 IMG=direct.json node fullrun.js fvm_fizz.html 3 > r2_fvm_fizz.log 2> r2_fvm_fizz.err
GC=1 DT=2000 IMG=direct.json node fullrun.js fvm_fizz32.html 3 > r2_fvm_fizz32.log 2> r2_fvm_fizz32.err
GC=1 DT=2000 IMG=direct.json node fullrun.js vm_fizz2.html 2.5 > r2_vm_fizz2.log 2> r2_vm_fizz2.err
GC=1 IMG=image.json node fullrun.js fvm32.html 20 > r2_fvm32.log 2> r2_fvm32.err
GC=1 IMG=image.json node fullrun.js vm2.html 25 > r2_vm2.log 2> r2_vm2.err
