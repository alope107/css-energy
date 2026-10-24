// splice: remove, insert, return the removed
var myArray0 = [32,false,"js",12,56,90];
console.log(myArray0.join(";"), myArray0.slice(1,4))
console.log(myArray0.splice(2,4,"hi","wr","ld"))
console.log(myArray0)
var a = [1, 2, 3, 4, 5]
console.log(a.splice(-2))
console.log(a.splice(1, 0, 9, 8))
console.log(a.splice(), a.splice(0, 1))
console.log(a)
var b = [1, 2, 3]
b.splice(1, 2, 4, 5, 6, 7, 8)
console.log(b.join(), b.length, [].splice(0, 5))
