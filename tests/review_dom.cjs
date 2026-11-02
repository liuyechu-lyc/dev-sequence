/* Offline template behavior checks; no browser, network, or external packages. */
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict'), path=require('node:path');
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this._text='';this.open=false;}
  set textContent(v){this._text=String(v);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this._text='';this.children=[...items];}
  setAttribute(k,v){this.attributes[k]=String(v);}
  descendants(){return this.children.flatMap(c=>[c,...c.descendants()]);}
  querySelector(selector){return this.descendants().find(c=>c.tagName===selector)||null;}
}
for(const filename of process.argv.slice(2)){
  const source=fs.readFileSync(filename,'utf8');
  const data=source.match(/<script id="ds-review-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
  const script=source.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  const entries={};
  ['page-title','page-meta','stage-tabs','review-content','expand-all','collapse-all','ds-review-data'].forEach(id=>entries[id]=new Element('div'));
  entries['ds-review-data'].textContent=data;
  const content=entries['review-content'];
  const document={title:'',getElementById:id=>entries[id],createElement:tag=>new Element(tag),querySelectorAll:selector=>{
    assert.equal(selector,'#review-content details');return content.descendants().filter(e=>e.tagName==='details');
  }};
  vm.runInNewContext(script,{document,Node:Element});
  assert(!content.textContent.includes('记录无法显示'));
  const rounds=content.descendants().filter(e=>(e.className||'').split(' ').includes('round-fold'));
  const expected=JSON.parse(data).stages[0].rounds;
  assert.equal(rounds.length,expected.length);
  rounds.forEach((r,i)=>assert(r.children[0].textContent.includes('第'+String(expected[i].number).padStart(3,'0')+'轮')));
  const all=document.querySelectorAll('#review-content details');
  assert(all.length>0);assert(rounds[0].open);
  entries['collapse-all'].onclick();assert(all.every(d=>!d.open));
  entries['expand-all'].onclick();assert(all.every(d=>d.open));
  const links=content.descendants().filter(e=>e.tagName==='a');
  assert(links.length>0);
  links.forEach(a=>{
    const href=a.attributes.href;assert(!/^[a-z][a-z0-9+.-]*:/i.test(href));
    assert(fs.existsSync(path.resolve(path.dirname(filename),href)),'Broken generated link: '+href);
  });
  assert(all.every(d=>d.children[0].tagName==='summary'));
}
console.log('Offline DOM: round order, nested folds, expand/collapse controls and local links passed.');
