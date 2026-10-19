import sys
src, var = sys.argv[1], sys.argv[2]
def patch(path, pairs):
    p = f'{src}/{path}'; s = open(p).read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:70], s.count(old)); s = s.replace(old, new)
    open(p, 'w').write(s)
G = 'OT/Layout/GDEF/GDEF.hh'
if var == 'inl':   # V1: inline the wide-set slow path again (as in 14.3.1)
    patch(G, [("""    HB_NEVER_INLINE
    bool mark_set_covers_slow""", """    HB_ALWAYS_INLINE
    bool mark_set_covers_slow""")])
if var == 'flat':  # V2: exact flat bitmaps for wide mark sets
    patch(G, [
     ("""    bool mark_set_covers_slow (unsigned int set_index, hb_codepoint_t glyph_id) const
    {""", """    bool mark_set_covers_slow (unsigned int set_index, hb_codepoint_t glyph_id) const
    {
      if (flat_words)
      { unsigned w = glyph_id >> 6; return w < flat_words && (flat.arrayZ[set_index * flat_words + w] >> (glyph_id & 63)) & 1; }"""),
     ("""	    if (max_gid - min_gid >= hb_bit_page_t::PAGE_BITS)
	    {""", """	    if (max_gid - min_gid >= hb_bit_page_t::PAGE_BITS)
	    {
	      if (!flat_words) { flat_words = (face->get_num_glyphs () + 63) / 64; if (!flat.resize (sets.length * flat_words)) flat_words = 0; }
	      if (flat_words) for (hb_codepoint_t gid : set) if ((gid >> 6) < flat_words) flat.arrayZ[i * flat_words + (gid >> 6)] |= (uint64_t) 1 << (gid & 63);"""),
     ("""    hb_vector_t<mark_glyph_set_bitmap_t> mark_glyph_set_bitmaps;""", """    hb_vector_t<mark_glyph_set_bitmap_t> mark_glyph_set_bitmaps;
    hb_vector_t<uint64_t> flat; unsigned flat_words = 0;"""),
    ])
if var == 'nohot':  # no hot-subtable (syllable-byte) cache
    patch('hb-ot-layout.cc', [("  bool use_hot_subtable_cache = accel.cache_enter (c);", "  bool use_hot_subtable_cache = false;")])
print('ok', var)
