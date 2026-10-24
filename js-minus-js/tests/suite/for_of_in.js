// for (x of a) and for (k in o): elements, keys as strings
var description = "";
var person = {fname:"Paul", lname:"Ken", age:18};
for (var x in person){
    description += person[x] + " ";
}
console.log(description)
var myPets = "";
var pets = ["cat", "dog", "hamster", "hedgehog"];
for (var pet of pets){
    myPets += pet + " ";
}
console.log(myPets)
for (const c of "hi!") console.log(c)
var o = {b: 1, 3: "x", a: 2, 1: "y"}
for (let k in o) { if (k != "a") console.log(k, o[k]) }
for (var i in [7, 8]) console.log(i, typeof i)
function f(a) {
  var s = 0
  for (var v of a) { s += v; if (v > 2) break }
  return s
}
console.log(f([1, 2, 3, 4]), x, pet)
