// objects as records, switch on commands
let acct = {owner: "Ada", balance: 100, log: []};
function apply(op, amt) {
  switch (op) {
    case "dep":
      acct.balance += amt;
      break;
    case "wd":
      if (amt > acct.balance) return "no";
      acct.balance -= amt;
      break;
    default:
      return "??";
  }
  acct.log.push(op);
  return "ok";
}
const ops = [["dep", 50], ["wd", 30], ["wd", 500], ["x", 1]];
for (let i = 0; i < ops.length; i++) {
  console.log(ops[i][0] + " " + apply(ops[i][0], ops[i][1]));
}
console.log("bal " + acct.balance);
console.log(acct.log.join());
