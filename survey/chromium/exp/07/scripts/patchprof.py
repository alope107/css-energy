import sys
src = sys.argv[1]
def patch(path, pairs):
    p = f'{src}/{path}'; s = open(p).read()
    for old, new in pairs:
        n = s.count(old)
        assert n == 1 or (n == 2 and 'r.apply (c, lookup_context))' in old), (path, old[:60], n)
        s = s.replace(old, new)
    open(p, 'w').write(s)
patch('hb-ot-layout.cc', [
 ("""	apply_string<Proxy> (&c,
			     proxy.accel.table->get_lookup (lookup_index),
			     *accel);
      }""", """	hbp_cur = lookup_index < HBP_NL ? lookup_index : HBP_NL - 1;
	uint64_t hbp_t0 = __builtin_ia32_rdtsc ();
	apply_string<Proxy> (&c,
			     proxy.accel.table->get_lookup (lookup_index),
			     *accel);
	hbp_lookups[hbp_cur].cyc += __builtin_ia32_rdtsc () - hbp_t0; hbp_lookups[hbp_cur].apps++;
      }
      else if (!buffer->messaging ()) HBC(19);"""),
 ("""    if (accel.apply (c, use_hot_subtable_cache))
      ret = true;""", """    HBL(fwd_apply); HBC(1);
    if (accel.apply (c, use_hot_subtable_cache))
      { ret = true; HBC(2); }"""),
 ("""  bool use_hot_subtable_cache = accel.cache_enter (c);
""", """  bool use_hot_subtable_cache = accel.cache_enter (c);
  if (use_hot_subtable_cache) { HBC(12); HBCN(13, c->buffer->len); }
"""),
 ("""      ret |= accel.apply (c, false);""", """      { HBL(fwd_apply); HBC(15); ret |= accel.apply (c, false); }"""),
 ("""  apply (proxy, plan, font, buffer);
  if (buffer->messaging ())
    (void) buffer->message (font, "end table GSUB script tag '%s'", tag);""",
  """  int hbp_ops0 = buffer->max_ops; uint64_t hbp_t0 = __builtin_ia32_rdtsc ();
  apply (proxy, plan, font, buffer);
  hbp_cnt[18] += hbp_ops0 - buffer->max_ops; hbp_cnt[40] += __builtin_ia32_rdtsc () - hbp_t0; hbp_cnt[41]++;
  if (!buffer->successful) hbp_cnt[42]++;
  if (buffer->messaging ())
    (void) buffer->message (font, "end table GSUB script tag '%s'", tag);"""),
])
patch('hb-ot-layout-gsubgpos.hh', [
 ("""    while ((signed) idx < stop)
    {
      idx++;
      switch (match (info[idx]))""", """    while ((signed) idx < stop)
    {
      idx++; HBC(7); HBL(steps);
      switch (match (info[idx]))"""),
 ("""    while (idx > stop)
    {
      idx--;
      switch (match (out_info[idx]))""", """    while (idx > stop)
    {
      idx--; HBC(8); HBL(steps);
      switch (match (out_info[idx]))"""),
 ("""    if (unlikely (skip == matcher_t::SKIP_YES))
      return SKIP;""", """    if (unlikely (skip == matcher_t::SKIP_YES))
      { HBC(9); return SKIP; }"""),
 ("""    nesting_level_left--;
    bool ret = recurse_func (this, sub_lookup_index);""", """    nesting_level_left--; HBC(14);
    bool ret = recurse_func (this, sub_lookup_index);"""),
 ("""    unsigned num_rules = rule.len;

#ifndef HB_NO_OT_RULESETS_FAST_PATH
    if (HB_OPTIMIZE_SIZE_VAL || num_rules <= 4)
#endif
    {
    slow:
      return_trace (
      + hb_iter (rule)
      | hb_map (hb_add (this))
      | hb_map ([&] (const ChainRuleType &_) { return _.apply (c, lookup_context); })""",
 """    unsigned num_rules = rule.len; HBC(3);

#ifndef HB_NO_OT_RULESETS_FAST_PATH
    if (HB_OPTIMIZE_SIZE_VAL || num_rules <= 4)
#endif
    {
    slow: HBC(21);
      return_trace (
      + hb_iter (rule)
      | hb_map (hb_add (this))
      | hb_map ([&] (const ChainRuleType &_) { HBC(5); HBL(rapply); return _.apply (c, lookup_context); })"""),
 ("""	  !digest->may_have (lookup_context.get_input_value (*first, lookup_context.match_data[1])))
	{""", """	  !digest->may_have (lookup_context.get_input_value (*first, lookup_context.match_data[1])))
	{ HBC(22);"""),
 ("""    for (unsigned int i = 0; i < num_rules; i++)
    {
      const auto &r = this+rule.arrayZ[i];

      const auto &input = StructAfter<decltype (r.inputX)> (r.backtrack);
      const auto &lookahead = StructAfter<decltype (r.lookaheadX)> (input);

      unsigned lenP1 = input.lenP1;""", """    for (unsigned int i = 0; i < num_rules; i++)
    {
      const auto &r = this+rule.arrayZ[i]; HBC(4); HBL(rules);

      const auto &input = StructAfter<decltype (r.inputX)> (r.backtrack);
      const auto &lookahead = StructAfter<decltype (r.lookaheadX)> (input);

      unsigned lenP1 = input.lenP1;"""),
 ("""	{
	  if (r.apply (c, lookup_context))
	  {
	    if (unsafe_to != (unsigned) -1)""", """	{ HBC(5); HBL(rapply);
	  if (r.apply (c, lookup_context))
	  { HBC(6);
	    if (unsafe_to != (unsigned) -1)"""),
])
patch('OT/Layout/GDEF/GDEF.hh', [
 ("""    bool mark_set_covers_slow (unsigned int set_index, hb_codepoint_t glyph_id) const
    {""", """    bool mark_set_covers_slow (unsigned int set_index, hb_codepoint_t glyph_id) const
    { HBC(10);"""),
])
patch('hb-ot-layout-common.hh', [
 ("""  unsigned int get_class (hb_codepoint_t glyph_id) const
  {
    switch (u.format.v) {""", """  unsigned int get_class (hb_codepoint_t glyph_id) const
  { HBC(11); HBL(cls);
    switch (u.format.v) {"""),
])
patch('OT/Layout/GSUB/ReverseChainSingleSubstFormat1.hh', [
 ("""      c->replace_glyph_inplace (substitute[index]);""", """      c->replace_glyph_inplace (substitute[index]); HBC(16);"""),
])
patch('hb-buffer.hh', [
 ("""    max_ops -= end - start;
    if (unlikely (max_ops < 0))
      successful = false;

    unsigned cluster_first""", """    max_ops -= end - start; HBC(26); HBCN(27, end - start);
    if (unlikely (max_ops < 0))
      successful = false;

    unsigned cluster_first"""),
])
print('patched')
