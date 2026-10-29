// Independent reference: ICU's Persian calendar through Intl (Node).  Prints "YYYY-MM-DD jalaliYear" per day.
const fmt = new Intl.DateTimeFormat('en-u-ca-persian-nu-latn', {year: 'numeric', timeZone: 'UTC'});
const [y0, y1] = [Number(process.argv[2]), Number(process.argv[3])];
const out = [];
for (let t = Date.UTC(y0, 0, 1); t < Date.UTC(y1 + 1, 0, 1); t += 86400000) {
  const d = new Date(t);
  const year = fmt.formatToParts(d).find(p => p.type === 'year').value;
  out.push(d.toISOString().slice(0, 10) + ' ' + year);
}
console.log(out.join('\n'));
