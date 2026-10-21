"""mkimage.py source.js out.json — the register machine's image with the program in RAM (rc_ref.image), for gen_rcss.py,
rsim.py and machine/halttime.js."""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rc_ref as RC
im = RC.image(open(sys.argv[1]).read())
json.dump(im, open(sys.argv[2], 'w'))
print('steps', im['steps'])
