// async / await: each await lets the others run
async function count(name, n) {
  for (let i = 1; i <= n; i++) {
    console.log(name + i);
    await null;
  }
  return name + " done";
}
count("a", 3).then(v => console.log(v));
count("b", 2).then(v => console.log(v));
console.log("main");
const later = new Promise(r => setTimeout(r, 500));
later.then(() => console.log("timer"));
