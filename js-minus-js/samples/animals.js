// prototypes: methods shared along a chain
function Animal(name, sound) {
  this.name = name;
  this.sound = sound;
}
Animal.prototype.speak = function () {
  return this.name + ": " + this.sound;
};
const cat = new Animal("cat", "meow");
const dog = new Animal("dog", "woof");
console.log(cat.speak());
console.log(dog.speak());
const pup = Object.create(dog);
pup.sound = "yip";
console.log(pup.speak());
console.log(pup.hasOwnProperty("name"));
const say = dog.speak.bind(cat);
console.log(say());
for (let k in pup) console.log(k);
