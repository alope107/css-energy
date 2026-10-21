// a diamond of stars
const h = 4;
for (let i = 1 - h; i < h; i++) {
  const w = h - (i < 0 ? -i : i);
  console.log(" ".repeat(h - w) + "*".repeat(2 * w - 1));
}
