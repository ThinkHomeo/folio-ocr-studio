const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const directory = path.join(__dirname,'..','formatocr','static');
const html = fs.readFileSync(path.join(directory,'setup.html'),'utf8');
const js = fs.readFileSync(path.join(directory,'setup.js'),'utf8').replace(/\nfetchStatus\(\);\s*$/, '');
class Element {
  constructor(){this.children=[];this.classList={toggle(){}};this.dataset={};this.hidden=false;this.disabled=false;this.textContent='';}
  append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;} scrollIntoView(){}
}
function harness(){
  const elements={};
  for(const match of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)) elements[match[1]]=new Element();
  const context=vm.createContext({document:{getElementById:id=>elements[id],createElement:()=>new Element(),querySelectorAll:()=>[]},
    window:{confirm:()=>false},setTimeout(){},clearTimeout(){},fetch(){throw Error('offline')}});
  vm.runInContext(js,context);
  return {elements,context,run:code=>vm.runInContext(code,context)};
}
function report(overrides={}){return {ready:true,hindi_ready:true,models_present:false,platform:'Windows',winget_available:true,checked_at:'2026-11-01T10:00:00Z',token:'nonce',checks:[{id:'tesseract',name:'Tesseract',status:'ready',detail:'5.4'}],...overrides};}
test('running app status disables every installation and start action',()=>{
  const h=harness();h.context.data=report({read_only:true,app_running:true});h.run('renderSetup(data)');
  for(const id of ['installPackages','installTesseract','installLanguages','startApp'])assert.equal(h.elements[id].disabled,true);
  assert.equal(h.elements.readOnly.hidden,false);assert.equal(h.elements.startApp.hidden,true);
});
test('missing core dependencies block starting but allow package repair',()=>{
  const h=harness();h.context.data=report({ready:false});h.run('renderSetup(data)');
  assert.equal(h.elements.startApp.disabled,true);assert.equal(h.elements.installPackages.disabled,false);
});
test('optional missing models do not block Text OCR',()=>{
  const h=harness();h.context.data=report();h.run('renderSetup(data)');
  assert.equal(h.elements.startApp.disabled,false);assert.match(h.elements.summary.textContent,/optional/);
});
test('installation progress locks controls and failed operation shows its log',()=>{
  const h=harness();h.context.data=report({task:{phase:'running',message:'Downloading',log:['Fetching']}});h.run('renderSetup(data)');
  assert.equal(h.elements.installPackages.disabled,true);assert.equal(h.elements.taskProgress.hidden,false);
  h.context.data.task={phase:'failed',message:'Download failed',log:['connection lost']};h.run('renderSetup(data)');
  assert.equal(h.elements.installPackages.disabled,false);assert.equal(h.elements.taskProgress.hidden,true);
  assert.equal(h.elements.taskLog.textContent,'connection lost');
});
test('a disconnected status request remains retryable',async()=>{
  const h=harness();await h.run('fetchStatus()');
  assert.equal(h.elements.requestError.hidden,false);assert.equal(h.elements.recheck.disabled,false);
  assert.match(h.elements.requestError.textContent,/retry/);
});

test('running environment is ready while the optional local environment is uncreated',()=>{
  const h=harness();h.context.data=report({app_running:true,environment_source:'running_app',local_environment:{exists:false,path:'project/.venv/python'},python:'existing/python'});h.run('renderSetup(data)');
  assert.equal(h.elements.statusHeading.textContent,'Ready for English Text OCR');
  assert.match(h.elements.environmentDetail.textContent,/not evidence that dependencies are missing/);
  assert.equal(h.elements.checkedEnvironment.textContent,'existing/python');
  assert.equal(h.elements.localEnvironment.textContent,'project/.venv/python');
});
