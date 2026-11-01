// Offline controller tests. This DOM model does not verify browser rendering/layout.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const staticDir = path.join(__dirname, '..', 'formatocr', 'static');
const html = fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8');
const source = fs.readFileSync(path.join(staticDir, 'app.js'), 'utf8').replace(/\ninit\(\);\s*$/, '');

class Element {
  constructor(tagName = 'DIV') {
    this.tagName = tagName.toUpperCase(); this.children = []; this.childNodes = [];
    this.value = ''; this.textContent = ''; this.dataset = {}; this.style = {};
    this.attributes = {}; this.events = {}; this.disabled = false;
    const classes = new Set();
    this.classList = {add: c => classes.add(c), remove: c => classes.delete(c),
      toggle: (c, enabled) => enabled ? classes.add(c) : classes.delete(c)};
  }
  get options() { return this.children; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key] || null; }
  addEventListener(name, handler) { this.events[name] = handler; }
  querySelectorAll() { return this.children; }
  querySelector(selector) { return this.children.find(c => selector.includes(c.dataset.panel)); }
  reportValidity() { return true; }
  focus() {}
  select() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  scrollIntoView() {}
  setPointerCapture() {}
}
function harness() {
  const elements = {};
  for (const match of html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"[^>]*>/g)) elements[match[2]] = new Element(match[1]);
  for (const match of html.matchAll(/<select\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
    for (const opt of match[2].matchAll(/<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)<\/option>/g)) {
      const element = new Element('OPTION'); element.value = opt[1]; element.textContent = opt[2];
      elements[match[1]].append(element);
    }
    elements[match[1]].value = elements[match[1]].options[0]?.value || '';
  }
  for (const panel of ['scan', 'inspector', 'queue']) {
    const button = new Element('BUTTON'); button.dataset.panel = panel; elements.mobileTabs.append(button);
  }
  const events = {};
  const context = vm.createContext({
    document: {getElementById: id => elements[id], createElement: tag => new Element(tag),
      createElementNS: (_, tag) => new Element(tag), querySelectorAll: () => [],
      addEventListener: (name, handler) => {events[name] = handler}, documentElement: {}},
    window: {confirm: () => false, matchMedia: () => ({matches:false}), scrollTo() {}, addEventListener() {}},
    Option: function(text, value) { const o = new Element('OPTION'); o.textContent = text; o.value = value; return o; },
    localStorage: {getItem: () => null, setItem() {}}, setTimeout: () => 1, clearTimeout() {}, setInterval() {},
    fetch: () => {throw Error('Network is forbidden in offline tests');},
    rendered: 0
  });
  vm.runInContext(source, context);
  const run = code => vm.runInContext(code, context);
  const fixture = {id:'qa', title:'QA', status:'ready', stats:{pages:2}, document:{mode:'structured',pages:[0,1].map(index => ({
    index, book_page:index, image_size:[800,1200], tokens:Array.from({length:index ? 3 : 333}, (_, i) => ({
      id:`p${index}-${i}`, remedy:`Remedy ${i}`, rubric:'Anxiety', rank:2, status:'needs_review', version:0,
      bbox:[1,2,30,40], machine:{}, review_reasons:i % 3 ? ['classifier-disagreement'] : ['classifier-disagreement','low-confidence']
    }))}))}};
  context.fixture = fixture;
  run('job=fixture; fullRender=render; render=()=>{ rendered++ }; library=async()=>{};');
  return {context, run, elements, events, fixture};
}
test('333 tokens paginate in blocks of 50 without losing the reason filter', () => {
  const h = harness(); h.run('renderQueue()'); h.elements.reasonFilter.value = 'classifier-disagreement';
  h.elements.reasonFilter.onchange(); h.elements.queueNext.onclick();
  assert.equal(h.elements.queuePage.textContent, '51–100 of 333');
  assert.equal(h.elements.queue.children.length, 50);
  assert.equal(h.elements.queue.children[0].children[1].children[0].textContent, '⚠ Remedy 50 · grade 2');
  assert.equal(h.elements.reasonFilter.value, 'classifier-disagreement');
  h.run('queuePageIndex=6; renderQueue()');
  assert.equal(h.elements.queue.children.length, 33); assert.equal(h.elements.queueNext.disabled, true);
  h.elements.reasonFilter.value = 'low-confidence'; h.elements.reasonFilter.onchange();
  assert.equal(h.elements.queuePage.textContent, '1–50 of 111');
});
test('selecting the current token preserves unsaved edits', () => {
  const h=harness(); h.elements.remedy.value='edited'; h.run("selectedId='p0-0'; dirty=true; selectToken('p0-0')");
  assert.equal(h.elements.remedy.value,'edited'); assert.equal(h.run('dirty'),true); assert.equal(h.context.rendered,0);
});
test('declining a token change retains the current token and dirty flag', () => {
  const h=harness(); h.run("selectedId='p0-0'; dirty=true; selectToken('p0-1')");
  assert.equal(h.run('selectedId'),'p0-0'); assert.equal(h.run('dirty'),true);
});
test('selecting a later token reveals the correct queue page', () => {
  const h=harness(); h.run("selectToken('p0-150'); renderQueue()");
  assert.equal(h.elements.queuePage.textContent,'151–200 of 333');
});
test('next review starts after the saved token and wraps across pages', () => {
  const h=harness(); h.run("selectedId='p0-150'; fixture.document.pages[0].tokens[150].status='reviewed'");
  assert.equal(h.run('nextReviewTarget().token'),'p0-151');
  h.run("selectedId='p0-332'; fixture.document.pages[0].tokens[332].status='reviewed'");
  assert.equal(h.run('nextReviewTarget().token'),'p1-0');
});
test('empty filtered batch never calls the assignment API', async () => {
  const h=harness(); h.elements.batchReviewer.value='QA'; h.elements.batchScope.value='filtered';
  h.elements.batchRubric.value='Fear'; h.elements.search.value='no-match';
  h.context.calls=0; h.run('api=async()=>{ calls++; };'); await h.run('applyBatch()');
  assert.equal(h.context.calls,0); assert.match(h.elements.toast.textContent,/Nothing was changed/);
});
test('failed batch preserves the unsaved editor', async () => {
  const h=harness(); h.elements.batchReviewer.value='QA'; h.elements.batchScope.value='selected';
  h.elements.batchRubric.value='Fear'; h.elements.remedy.value='unsaved remedy';
  h.context.window.confirm=()=>true;
  h.run("selectedId='p0-0'; dirty=true; batchSelection.add('p0-0'); api=async()=>{ throw Error('offline') }");
  await h.run('applyBatch()'); assert.equal(h.elements.remedy.value,'unsaved remedy');
  assert.equal(h.run('dirty'),true); assert.equal(h.run('pending'),false);
});
test('saving blocks navigation and a failed save retains edits', async () => {
  const h=harness(); h.elements.reviewer.value='QA'; h.elements.remedy.value='new';
  h.context.rejectWrite=null;
  h.run("selectedId='p0-0'; dirty=true; api=()=>new Promise((_,reject)=>{ rejectWrite=reject })");
  const save=h.run('save()'); h.run("selectToken('p0-1'); navigatePage(1)");
  assert.equal(h.run('selectedId'),'p0-0'); assert.equal(h.run('pageIndex'),0);
  assert.equal(h.elements.remedy.disabled,true);
  h.context.rejectWrite(Error('write failed')); await save;
  assert.equal(h.elements.remedy.value,'new'); assert.equal(h.run('dirty'),true); assert.equal(h.elements.save.disabled,false);
});
test('page changes clear batch selection, notes, and queue position', () => {
  const h=harness(); h.run("batchSelection.add('p0-0'); queuePageIndex=5"); h.elements.note.value='old';
  h.run('navigatePage(1)'); assert.equal(h.run('batchSelection.size'),0); assert.equal(h.run('queuePageIndex'),0);
  assert.equal(h.elements.note.value,'');
});
test('next incomplete page asks about unsaved edits once', () => {
  const h=harness(); let confirms=0; h.context.window.confirm=()=>{confirms++; return true};
  h.run('dirty=true; nextIncompletePage()'); assert.equal(confirms,1); assert.equal(h.run('pageIndex'),1);
});
test('manual token history supports null before/after records', async () => {
  const h=harness(); h.run("selectedId='p0-0'; api=async()=>[{reviewer:'QA',at:'2026-11-01',before_json:null,after_json:{rank:2}}]");
  await h.run('history()'); assert.match(h.elements.historyItems.children[0].textContent,/added → 2/);
});
test('an outdated export preview cannot enable an invalid combination', async () => {
  const h=harness(); h.context.resolvers=[]; h.run('api=()=>new Promise(resolve=>resolvers.push(resolve))');
  const first=h.run('updateExportPreview()'); const second=h.run('updateExportPreview()');
  h.context.resolvers[1]({valid:false,row_count:333,incomplete_count:333,errors:['Reviewed scope required']}); await second;
  h.context.resolvers[0]({valid:true,row_count:333,incomplete_count:0,errors:[]}); await first;
  assert.equal(h.elements.export.disabled,true); assert.equal(h.run('lastExportPreview.valid'),false);
});
test('keyboard skip is safe without a document and works for plain pages', () => {
  const h=harness(); const event={key:'s',target:{tagName:'BODY'},preventDefault(){}};
  h.run('job=null'); h.events.keydown(event);
  h.run("job=fixture; job.document.mode='plain'"); h.events.keydown(event); assert.equal(h.run('pageIndex'),1);
});
test('Ctrl+S stays on the token; Ctrl+Enter requests Save & Next', () => {
  const h=harness(); h.context.calls=[]; h.run('save=(...args)=>calls.push(args)');
  h.events.keydown({key:'s',ctrlKey:true,target:{tagName:'INPUT'},preventDefault(){}});
  h.events.keydown({key:'Enter',ctrlKey:true,target:{tagName:'INPUT'},preventDefault(){}});
  assert.deepEqual(Array.from(h.context.calls[0]),[false,false]); assert.deepEqual(Array.from(h.context.calls[1]),[false]);
});
test('Save & Next persists a later token and advances to its successor', async () => {
  const h=harness(); h.elements.reviewer.value='QA'; h.elements.remedy.value='corrected'; h.elements.rubric.value='Fear';
  h.elements.rank.value='3';
  h.run("selectedId='p0-150'; dirty=true; api=async(url,options)=>{ if(options?.method==='PATCH') { const d=JSON.parse(options.body); Object.assign(fixture.document.pages[0].tokens[150],d,{status:'reviewed'}); return {}; } return fixture; }");
  await h.run('save()'); assert.equal(h.run('selectedId'),'p0-151'); assert.equal(h.run('dirty'),false);
  assert.equal(h.fixture.document.pages[0].tokens[150].remedy,'corrected'); assert.equal(h.run('queuePageIndex'),3);
});
test('a page without extracted tokens still offers Add missing token', () => {
  const h=harness(); h.fixture.document.pages[0].tokens=[]; h.run('renderInspector()');
  assert.equal(h.elements.tokenPanel.hidden,true); assert.equal(h.elements.addToken.disabled,false);
  assert.equal(h.elements.splitToken.disabled,true);
});
test('full structured render updates progress, panels, and a bounded queue', async () => {
  const h=harness(); h.fixture.stats.reviewed_percent=25;
  h.run("api=async()=>({valid:true,row_count:333,incomplete_count:333,errors:[]}); fullRender()");
  await Promise.resolve();
  assert.equal(h.elements.queue.children.length,50); assert.equal(h.elements.progressTrack.attributes['aria-valuenow'],25);
  assert.equal(h.elements.mobileTabs.children[0].attributes['aria-pressed'],'true');
});
test('app input dialog accepts text and Cancel preserves the original operation', async () => {
  const h=harness(); const first=h.run("promptValue('New name','Existing')");
  assert.equal(h.elements.inputDialog.open,true); assert.equal(h.elements.inputDialogValue.value,'Existing');
  h.elements.inputDialogValue.value='Renamed'; h.elements.inputDialogForm.onsubmit({preventDefault(){}});
  assert.equal(await first,'Renamed'); assert.equal(h.elements.inputDialog.open,false);
  const second=h.run("promptValue('Split remedies','A;B')"); h.elements.inputDialogCancel.onclick();
  assert.equal(await second,null);
});
test('delete confirmation identifies the document and Cancel makes no request', () => {
  const h=harness(); h.context.calls=[];
  h.run("api=async(...args)=>calls.push(args); requestDeleteDocument('qa')");
  assert.equal(h.elements.deleteDocumentName.textContent,'QA'); assert.equal(h.elements.deleteDialog.open,true);
  h.elements.cancelDelete.onclick(); assert.equal(h.elements.deleteDialog.open,false); assert.equal(h.context.calls.length,0);
});
test('deleting another library document preserves the current unsaved editor', async () => {
  const h=harness(); h.context.other={id:'other',title:'Other document',status:'ready'}; h.context.calls=[];
  h.elements.remedy.value='unsaved';
  h.run("libraryItems=[fixture,other]; selectedId='p0-0'; dirty=true; api=async(url,options)=>{calls.push({url,method:options.method})}; requestDeleteDocument('other')");
  await h.run('confirmDeleteDocument()');
  assert.equal(h.context.calls[0].url,'/api/jobs/other'); assert.equal(h.context.calls[0].method,'DELETE');
  assert.equal(h.run('job.id'),'qa'); assert.equal(h.run('dirty'),true); assert.equal(h.elements.remedy.value,'unsaved');
});
test('failed deletion keeps the document and reports the error inside the dialog', async () => {
  const h=harness(); h.run("api=async()=>{throw Error('Deletion failed')}; requestDeleteDocument('qa')");
  await h.run('confirmDeleteDocument()');
  assert.equal(h.run('job.id'),'qa'); assert.equal(h.elements.deleteDialog.open,true);
  assert.equal(h.elements.deleteDialogError.textContent,'Deletion failed'); assert.equal(h.elements.deleteDialogError.hidden,false);
  assert.equal(h.elements.confirmDelete.disabled,false);
});
test('mobile delete is available again when document loading finishes', () => {
  const h=harness(); h.run('setPending(true)'); assert.equal(h.elements.deleteSelectedDocument.disabled,true);
  h.run('setPending(false)'); assert.equal(h.elements.deleteSelectedDocument.disabled,false);
  h.run('job=null; setPending(false)'); assert.equal(h.elements.deleteSelectedDocument.disabled,true);
});
