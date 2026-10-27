const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const {join} = require('node:path');
function app() {
  const elements = new Map();
  const context = vm.createContext({document:{getElementById(id) {
    if (!elements.has(id)) elements.set(id,{value:'',checked:false,addEventListener(){}});
    return elements.get(id);
  }}, fetch:()=>new Promise(()=>{}), URL, Blob, setTimeout});
  vm.runInContext(readFileSync(join(__dirname,'../app.js'),'utf8'), context);
  return {run:code=>vm.runInContext(code,context), elements};
}
test('full dates are shown without timezone shifts; partial dates stay partial',()=>{
  const {run}=app();
  assert.match(run("dateMarkup({publicationDate:'2026-09-07',dateSource:'online'})"), /在线发表.*datetime="2026-09-07">2026-09-07/);
  const month=run("dateMarkup({publicationDate:'2026-09'})");
  assert.match(month,/未提供具体日/);
  assert.doesNotMatch(month,/2026-09-01/);
  assert.match(run("dateMarkup({year:'2026'})"),/仅提供年份/);
  assert.match(run('dateMarkup({})'),/发表日期未提供/);
});
test('latest and oldest sort by month and day within the same year',()=>{
  const {run,elements}=app();
  run("entry={papers:[{id:'a',year:'2026',publicationDate:'2026-02-12',citations:1},{id:'b',year:'2026',publicationDate:'2026-09-07',citations:1},{id:'c',year:'2026',publicationDate:'2026-09-17',citations:1}]}");
  elements.get('sort').value='new';
  assert.equal(run("filtered().map(p=>p.id).join(',')"),'c,b,a');
  elements.get('sort').value='old';
  assert.equal(run("filtered().map(p=>p.id).join(',')"),'a,b,c');
});
test('year filter and citation sort still work, including records without dates',()=>{
  const {run,elements}=app();
  run("entry={papers:[{id:'a',year:'2025',publicationDate:'2025-09-07',citations:2},{id:'b',year:'2026',publicationDate:'2026-02',citations:1},{id:'c',year:'',publicationDate:'',citations:100}]}");
  elements.get('sort').value='cited';
  assert.equal(run("filtered().map(p=>p.id).join(',')"),'c,a,b');
  elements.get('year').value='2026';
  assert.equal(run("filtered().map(p=>p.id).join(',')"),'b');
});

test('cached publisher images stay inside the gallery asset directory',()=>{
  const {run}=app();
  run("document.baseURI='https://gallery.example/GCE-scholar/'");
  const asset='assets/publisher/'+'a'.repeat(32)+'.png';
  assert.equal(run('safeImageURL('+JSON.stringify(asset)+')'),'https://gallery.example/GCE-scholar/'+asset);
  assert.equal(run("safeImageURL('../private.png')"),'#');
  assert.equal(run("safeImageURL('assets/publisher/../../private.png')"),'#');
  assert.equal(run("safeImageURL('javascript:alert(1)')"),'#');
  assert.equal(run("figureLabel({publisherImageStatus:'access_restricted'})"),'原图获取受限 · 文献封面');
});
