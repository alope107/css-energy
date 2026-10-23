"""net_slot.py — the modem's geometry, shared by the page (gen_css.py) and the gateway's documents (net/server.js SLOT):
the slot is SLOT px wide, the modem iframe NW px (answers up to 2^20 px of scroll)."""
SLOT = 100
NW = (1 << 20) + SLOT
