'use strict';
let setupToken = '', setupData = null, fetching = false, timer = null, lastPhase = null;
const byId = id => document.getElementById(id);
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function renderChecks(items, target) {
  byId(target).replaceChildren(...items.map(item => {
    const card = node('article', undefined, 'check'), heading = node('div', undefined, 'check-top');
    heading.append(node('strong', item.name), node('span', {ready:'Ready',warning:'Needs attention',error:'Missing / repair',unchecked:'Not checked'}[item.status] || 'Unknown', `badge ${item.status}`));
    card.append(heading, node('p', item.detail));
    if (item.path) {
      const details = node('details'); details.append(node('summary', 'Location'), node('code', item.path)); card.append(details);
    }
    return card;
  }));
}
function renderSetup(data) {
  setupData = data; setupToken = data.token || '';
  const checks = data.checks || [];
  renderChecks(checks.filter(c => !['tesseract','eng','hin'].includes(c.id) && !c.id.endsWith('.pkl')), 'pythonChecks');
  renderChecks(checks.filter(c => ['tesseract','eng','hin'].includes(c.id)), 'ocrChecks');
  renderChecks(checks.filter(c => c.id.endsWith('.pkl')), 'modelChecks');
  byId('statusHeading').textContent = data.ready ? 'Ready for English Text OCR' : 'Setup needs attention';
  byId('summary').textContent = data.ready
    ? `Required components are working. ${data.hindi_ready ? 'Hindi OCR is also ready.' : 'Install Hindi language data for Hindi scans.'} ${data.models_present ? 'Format-aware model files are present.' : 'Format-aware model files are optional and currently missing.'}`
    : 'Resolve the required Python, package, Tesseract and English language items below. Optional models do not prevent Text OCR.';
  byId('overview').classList.toggle('warning', !data.ready);
  byId('checkedAt').textContent = `Checked ${new Date(data.checked_at).toLocaleString()} · ${data.platform}`;
  const fromRunningApp = data.environment_source === 'running_app';
  byId('environmentNote').hidden = !data.environment_source;
  byId('environmentTitle').textContent = fromRunningApp ? 'Checking the environment used by your running app' : 'Checking this folder’s local Python environment';
  byId('environmentDetail').textContent = data.environment_warning || (fromRunningApp
    ? data.local_environment?.exists
      ? 'The cards below describe the Python environment currently used by Folio. A separate local .venv is also present; it is not checked in this view.'
      : 'Folio is using an existing Python environment and the cards below show its actual dependency status. This folder’s separate .venv has not been created. That is a portable setup option, not evidence that dependencies are missing from this computer.'
    : data.local_environment?.exists
      ? 'The cards below check this app’s .venv. Dependencies installed in other Python environments do not automatically become available here.'
      : 'Python is available to run this setup. This folder’s .venv has not been created yet, so its package checks are marked Not checked. Use Install / repair packages to prepare it for independent startup.');
  byId('checkedEnvironment').textContent = data.python || '';
  byId('localEnvironment').textContent = data.local_environment?.path || data.python || '';
  byId('readOnly').hidden = !data.read_only; byId('returnLink').hidden = !data.read_only;
  byId('activeApp').hidden = data.read_only || !data.app_running; byId('stopApp').hidden = !data.app_owned;
  const running = data.task?.phase === 'running', blocked = data.read_only || data.app_running || running;
  byId('installPackages').disabled = blocked;
  byId('installTesseract').disabled = blocked || !data.winget_available || data.platform !== 'Windows';
  byId('installLanguages').disabled = blocked || !checks.some(c => c.id === 'tesseract' && c.status === 'ready');
  byId('installTesseract').title = !data.winget_available ? 'winget is unavailable. Use the installer link.' : '';
  byId('startApp').hidden = data.read_only || data.app_running; byId('startApp').disabled = blocked || !data.ready;
  byId('openApp').hidden = !data.app_running || data.read_only; byId('openApp').href = data.app_url || '/';
  byId('startHelp').textContent = data.read_only ? 'Dependency status belongs to your currently running Folio instance.' :
    data.app_running ? 'Folio is running. Use Open Folio to go to your documents.' :
    data.ready ? 'Start Folio here, or close setup and double-click run_app.bat.' : 'Resolve the required items above to start Folio.';
  byId('recheck').disabled = running; byId('stopApp').disabled = running;
  const task = data.task; byId('taskPanel').hidden = !task || task.phase === 'idle';
  if (task) {
    byId('taskMessage').textContent = task.message; byId('taskProgress').hidden = !running;
    byId('taskLog').textContent = (task.log || []).join('\n');
    byId('taskMessage').classList.toggle('error', task.phase === 'failed');
    if (running && lastPhase !== 'running') byId('taskPanel').scrollIntoView({behavior:'smooth',block:'nearest'});
    lastPhase = task.phase;
  }
}
async function fetchStatus(refresh = false) {
  if (fetching) return;
  fetching = true; byId('recheck').disabled = true;
  try {
    const response = await fetch(`/api/setup/status${refresh ? '?refresh=1' : ''}`);
    if (!response.ok) throw Error(`Dependency check failed (${response.status}).`);
    renderSetup(await response.json()); byId('requestError').hidden = true;
  } catch (error) {
    byId('requestError').textContent = `${error.message} Keep the setup/server window open, then retry.`;
    byId('requestError').hidden = false;
  } finally {
    fetching = false; byId('recheck').disabled = setupData?.task?.phase === 'running'; clearTimeout(timer);
    if (!setupData?.read_only) timer = setTimeout(() => fetchStatus(), setupData?.task?.phase === 'running' ? 1200 : 6000);
  }
}
async function setupAction(action) {
  if (!setupData || setupData.read_only || setupData.task?.phase === 'running') return;
  document.querySelectorAll('[data-action]').forEach(button => {button.disabled = true;});
  try {
    const response = await fetch('/api/setup/action', {method:'POST',headers:{'Content-Type':'application/json','X-Folio-Setup':setupToken},body:JSON.stringify({action})});
    const result = await response.json(); if (!response.ok) throw Error(result.detail || 'Setup action failed.');
    await fetchStatus();
  } catch (error) {
    byId('requestError').textContent = error.message; byId('requestError').hidden = false;
    if (setupData) renderSetup(setupData);
  }
}
byId('recheck').onclick = () => fetchStatus(true);
document.querySelectorAll('[data-action]').forEach(button => {button.onclick = () => setupAction(button.dataset.action);});
byId('stopApp').onclick = () => byId('stopDialog').showModal();
byId('cancelStop').onclick = () => byId('stopDialog').close();
byId('confirmStop').onclick = () => { byId('stopDialog').close(); setupAction('stop'); };
fetchStatus();
