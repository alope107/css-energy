// learnxinyminutes 3: logic and control structures
var count = 1;
if (count == 3) { console.log(3); }
else if (count == 4) { console.log(4); }
else { console.log("other"); }
var input, k = 0;
do { input = k++; } while (input < 3);
outer:
for (var i = 0; i < 10; i++) {
  for (var j = 0; j < 10; j++) {
    if (i == 5 && j == 5) { break outer; } }
}
console.log(i, j, input);
var desc = "", person = {fname: "Paul", lname: "Ken", age: 18};
for (var x in person) { desc += person[x] + " "; }
var myPets = "", pets = ["cat", "dog", "hamster"];
for (var pet of pets) { myPets += pet + " "; }
console.log(desc, myPets);
var colour = "red", otherName;
var name = otherName || "default"; grade = 'B';
switch (grade) { case 'A': console.log("Great job"); break;
  case 'B': console.log("OK job"); break;
  default: console.log("Oy vey"); }
console.log(name, colour == "red" && name.length);
