#include <hb.h>
#include <stdio.h>
#include <string.h>
int main (int argc, char **argv) {
  hb_blob_t *blob = hb_blob_create_from_file_or_fail (argv[1]);
  hb_font_t *font = hb_font_create (hb_face_create (blob, 0));
  hb_feature_t f; hb_feature_from_string (argc > 3 ? argv[3] : "cv01", -1, &f);
  hb_buffer_t *b = hb_buffer_create (); hb_buffer_add_utf8 (b, argv[2], -1, 0, -1); hb_buffer_guess_segment_properties (b);
  hb_shape (font, b, &f, 1);
  unsigned n; hb_glyph_info_t *gi = hb_buffer_get_glyph_infos (b, &n); hb_glyph_position_t *gp = hb_buffer_get_glyph_positions (b, &n);
  printf ("%s successful=%d:", argv[2], hb_buffer_allocation_successful (b));
  for (unsigned i = 0; i < n; i++) printf (" g%u/%d", gi[i].codepoint, gp[i].x_advance);
  printf ("\n");
}
