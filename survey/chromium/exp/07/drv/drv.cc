// Shape the font CPU's input texts with HarfBuzz; time it; optionally dump per-lookup profile.
// usage: drv font.ttf texts.txt reps [script-tag|-] [nolf]
#include <hb.h>
#include <hb-ot.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <vector>
#include <algorithm>
#include <string>
#ifdef HBPROF
#include "hbprof.h"
#endif
static double now () { timespec ts; clock_gettime (CLOCK_MONOTONIC, &ts); return ts.tv_sec + ts.tv_nsec * 1e-9; }
int main (int argc, char **argv)
{
  if (argc < 4) { fprintf (stderr, "usage\n"); return 1; }
  hb_blob_t *blob = hb_blob_create_from_file_or_fail (argv[1]);
  if (!blob) { fprintf (stderr, "no font\n"); return 1; }
  hb_face_t *face = hb_face_create (blob, 0);
  hb_font_t *font = hb_font_create (face);
  std::vector<std::vector<uint32_t>> texts;
  FILE *f = fopen (argv[2], "r"); char line[1 << 16];
  while (fgets (line, sizeof line, f)) {
    std::vector<uint32_t> t; char *p = line, *e;
    for (;;) { unsigned long v = strtoul (p, &e, 10); if (e == p) break; t.push_back ((uint32_t) v); p = e; }
    if (!t.empty ()) texts.push_back (t);
  }
  int reps = atoi (argv[3]);
  hb_script_t script = HB_SCRIPT_INVALID;
  if (argc > 4 && strcmp (argv[4], "-")) script = hb_script_from_string (argv[4], -1);
  hb_feature_t feat; hb_feature_from_string ("cv01=1", -1, &feat);
  if (argc > 5) { hb_feature_from_string (argv[5], -1, &feat); }
  hb_buffer_t *buf = hb_buffer_create ();
  unsigned long long checksum = 0;
  // warm up (accelerators, plan cache)
  for (auto &t : texts) {
    hb_buffer_clear_contents (buf); hb_buffer_add_utf32 (buf, t.data (), t.size (), 0, t.size ());
    hb_buffer_set_direction (buf, HB_DIRECTION_LTR); if (script != HB_SCRIPT_INVALID) hb_buffer_set_script (buf, script);
    hb_buffer_guess_segment_properties (buf); hb_shape (font, buf, &feat, 1);
  }
#ifdef HBPROF
  hbprof_reset ();
#endif
  std::vector<double> per (reps);
  for (int r = 0; r < reps; r++) {
    double t0 = now ();
    for (auto &t : texts) {
      hb_buffer_clear_contents (buf); hb_buffer_add_utf32 (buf, t.data (), t.size (), 0, t.size ());
      hb_buffer_set_direction (buf, HB_DIRECTION_LTR); if (script != HB_SCRIPT_INVALID) hb_buffer_set_script (buf, script);
      hb_buffer_guess_segment_properties (buf); hb_shape (font, buf, &feat, 1);
      unsigned n; hb_glyph_info_t *gi = hb_buffer_get_glyph_infos (buf, &n);
      hb_glyph_position_t *gp = hb_buffer_get_glyph_positions (buf, &n);
      for (unsigned i = 0; i < n; i++) checksum = checksum * 31 + gi[i].codepoint + gp[i].x_advance;
    }
    per[r] = (now () - t0) / texts.size () * 1e3;
  }
  std::sort (per.begin (), per.end ());
  printf ("shapings %zu reps %d  ms/shaping min %.3f med %.3f  checksum %016llx\n", texts.size (), reps, per[0], per[reps / 2], checksum);
#ifdef HBPROF
  hbprof_dump (stdout, texts.size () * (size_t) reps);
#endif
  return 0;
}
#ifdef HBPROF
extern "C" {
hbp_lk_t hbp_lookups[HBP_NL];
uint64_t hbp_cnt[HBP_NC];
unsigned hbp_cur;
void hbprof_reset () { memset (hbp_lookups, 0, sizeof hbp_lookups); memset (hbp_cnt, 0, sizeof hbp_cnt); }
void hbprof_dump (FILE *f, size_t shapings)
{
  // TSC calibration
  double t0 = now (); uint64_t c0 = __builtin_ia32_rdtsc (); while (now () - t0 < 0.2); uint64_t c1 = __builtin_ia32_rdtsc (); double t1 = now ();
  double ghz = (c1 - c0) / (t1 - t0) / 1e9;
  fprintf (f, "tsc_ghz %.4f shapings %zu\n", ghz, shapings);
  for (int i = 0; i < HBP_NC; i++) if (hbp_cnt[i]) fprintf (f, "cnt %d %llu\n", i, (unsigned long long) hbp_cnt[i]);
  for (int i = 0; i < HBP_NL; i++) if (hbp_lookups[i].apps) {
    auto &l = hbp_lookups[i];
    fprintf (f, "lk %d %llu %llu %llu %llu %llu %llu %llu\n", i, (unsigned long long) l.cyc, (unsigned long long) l.apps, (unsigned long long) l.fwd_apply,
	     (unsigned long long) l.rules, (unsigned long long) l.rapply, (unsigned long long) l.steps, (unsigned long long) l.cls);
  }
}
}
#endif
