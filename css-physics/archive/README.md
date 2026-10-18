# Archive

- `rigid3d-v3/gen3d_v3.py` (+ `simp.py`): the 3D engine before the big optimization session (Oct 10): unnamed style()
  gates, a separate solve level, one register per element. It still builds with the current page builder, as an A/B
  baseline: `GEN=../archive/rigid3d-v3/gen3d_v3.py COUNTS=16 PLAIN=1 python3 src/build3d.py out/v3_16.html`

Removed 2026-10-15, still in git at `91d73bc` (`git checkout 91d73bc -- css-physics/archive`): `rigid2d/` (rigid.css,
the 2D engine the 3D one grew from; `python3 gen.py [substeps] [out.html]` in that directory) and
`rigid3d-v3/build3d_v3.py` (the v3-era page builder).
