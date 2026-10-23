// a Caesar cipher on strings
function shift(s, k) {
  let r = "";
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 65 && c <= 90)
      r += String.fromCharCode((c - 65 + k + 26) % 26 + 65);
    else r += s.charAt(i);
  }
  return r;
}
const words = ["HAL", "CSS", "VMS", "OK"];
for (let i = 0; i < words.length; i++) {
  const w = shift(words[i], 1);
  console.log(words[i] + ">" + w);
}
console.log(shift(shift("ROUND", 13), 13));
