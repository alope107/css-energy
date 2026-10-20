// string methods
var t = "  Hello, World  ".trim();
console.log(t, t.length);
console.log(t.toUpperCase(), t.toLowerCase());
console.log(t.indexOf("o"), t.lastIndexOf("o"), t.indexOf("z"));
console.log(t.includes("World"), t.startsWith("He"));
console.log(t.endsWith("x"), t.endsWith("ld"));
console.log(t.slice(0, 5), t.slice(-5), t.slice(7, -1));
console.log(t.substring(5, 0), t.substring(7), "ab".repeat(3));
var p = t.split(", ");
console.log(p.length, p[0], p[1]);
console.log("a-b-c".split("-").join("+"), "abc".split("")[2]);
console.log("x".concat("y"), parseInt("12") * 2, Number("-5"));
console.log(String(7) + 1, String(1 < 2), parseInt("  9x"));
