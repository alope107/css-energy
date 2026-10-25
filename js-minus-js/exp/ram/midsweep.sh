# midsweep.sh out.tsv — csssim's passes per suite program with mid-chain fill stages (MIDM levels apart, MIDW write-backs
# per pass) against none: one line per (program, M, W). Two processes at a time.
cd "$(dirname "$0")/../.."
for f in tests/suite/*.js; do for c in "0 1" "8 1" "8 2" "8 3" "16 1" "16 2" "16 3" "4 3" "4 5"; do echo "$f $c"; done; done |
  xargs -P 2 -L 1 sh -c 'r=$(MIDM=$1 MIDW=$2 timeout 600 python3 machine/csssim.py $0 2>/dev/null | tail -1); echo "$(basename $0 .js)\t$1\t$2\t$(echo "$r" | sed -n "s/.*passes \([0-9]*\).*/\1/p")\t$(echo "$r" | grep -c "output ok True")"' > "$1"
