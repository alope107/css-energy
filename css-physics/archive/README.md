# Archive

Earlier generators, kept for reference (see docs/HISTORY.md). Not maintained.

- `rigid2d/gen_v1.py`, `rigid2d/gen.py` (+ `page.html`, `ui.css`): rigid.css, the 2D engine the 3D machine grew from. Run with `python3 gen.py [substeps] [out.html]` in that directory.
- `rigid3d-v3/gen3d_v3.py` (+ `simp.py`): the 3D engine before the big optimization session (Oct 10). It has unnamed style() gates, a separate solve level and one register per element. It still builds with the current page builder, which makes it an A/B baseline:
  `GEN=../archive/rigid3d-v3/gen3d_v3.py COUNTS=16 PLAIN=1 python3 src/build3d.py out/v3_16.html`
  (`build3d_v3.py` is the builder from that time, for reference.)
