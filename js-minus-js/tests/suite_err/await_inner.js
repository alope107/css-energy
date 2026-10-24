// await in an arrow that is not async, inside an async function
async function f(p) {
  const g = () => await p;
}
