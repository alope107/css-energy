// a linked list of objects, null at the end
var head = null;
for (var i = 1; i <= 6; i++) head = {v: i, next: head};
var s = 0;
var n = head;
while (n) { s += n.v; n = n.next; }
console.log(s);
function rev(l) {
  var r = null;
  while (l) { var nx = l.next; l.next = r; r = l; l = nx; }
  return r;
}
head = rev(head);
console.log(head.v, head.next.v, head.next.next.next.v);
