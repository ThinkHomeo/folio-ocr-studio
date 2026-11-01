const $ = id => document.getElementById(id);

let job = null;
let pageIndex = 0;
let selectedId = null;
let pending = false;
let dirty = false;
let toastTimer;
let libraryItems = [];
let queuePageIndex = 0;
const queuePageSize = 50;
const batchSelection = new Set();
let addTokenMode = false;
let addStart = null;
let activeMobilePanel = 'scan';
let lastExportPreview = null;
let exportPreviewRequest = 0;
let promptResolver = null;
let deleteTarget = null;

const colors = {1: '#b377ce', 2: '#4584c8', 3: '#3e9578', 4: '#cd8b3e', 5: '#c2635c'};

function toast(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').hidden = true, 5500);
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail;
    try {
      detail = await response.json();
    } catch {
      detail = {detail: await response.text()};
    }
    throw Error(typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail));
  }
  if (response.status === 204) return null;
  return response.json();
}

function make(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function promptValue(message, initial = '') {
  if (promptResolver) return Promise.resolve(null);
  $('inputDialogLabel').textContent = message;
  $('inputDialogValue').value = initial;
  return new Promise(resolve => {
    promptResolver = resolve;
    $('inputDialog').showModal();
    $('inputDialogValue').focus();
    $('inputDialogValue').select();
  });
}

function finishPrompt(value) {
  const resolve = promptResolver;
  promptResolver = null;
  $('inputDialog').close();
  resolve?.(value);
}

const page = () => job?.document.pages[pageIndex];
const selected = () => page()?.tokens?.find(token => token.id === selectedId);
const isPlain = () => job?.document?.mode === 'plain';

function setDirty(value) {
  dirty = value;
}

function setPending(value) {
  pending = value;
  $('deleteSelectedDocument').disabled = !job || pending || ['queued', 'running'].includes(job.status);
  if (!job) return;
  if (isPlain()) renderPlainButtons();
  else updateStructuredButtons();
}

function confirmDiscard() {
  if (pending) {
    toast('Wait for the current operation to finish.');
    return false;
  }
  return !dirty || window.confirm('You have unsaved changes. Discard them and continue?');
}

async function library() {
  libraryItems = await api('/api/jobs');
  renderLibrary();
}

function renderLibrary() {
  const query = $('documentSearch').value.trim().toLowerCase();
  const jobs = libraryItems.filter(item => `${item.title} ${item.mode} ${item.language}`.toLowerCase().includes(query));
  $('jobs').replaceChildren();
  $('documentSelect').replaceChildren(new Option('Choose a document…', ''));
  for (const item of jobs) {
    const card = make('article', undefined, `document-item${job?.id === item.id ? ' active' : ''}`);
    const button = make('button', undefined, `job-card${job?.id === item.id ? ' active' : ''}`);
    const unit = item.mode === 'plain' ? 'words' : 'tokens';
    button.append(
      make('strong', item.title),
      make('small', `${item.stats.pages} ${item.stats.pages === 1 ? 'page' : 'pages'} · ${item.stats.tokens} ${unit}`),
      make('small', item.mode === 'plain' ? 'Text OCR' : 'Format-aware OCR', 'job-mode')
    );
    button.onclick = () => openJob(item.id);
    const footer = make('div', undefined, 'document-item-footer');
    const processing = ['queued', 'running'].includes(item.status);
    const completed = item.stats.reviewed_percent === 100;
    footer.append(make('span', processing ? 'Processing' : completed ? '✓ Reviewed' : item.status === 'failed' ? 'OCR failed' : 'OCR complete', `document-state${completed ? ' complete' : ''}`));
    const remove = make('button', 'Delete', 'document-delete');
    remove.type = 'button';
    remove.setAttribute('aria-label', `Delete ${item.title}`);
    remove.disabled = processing;
    remove.onclick = () => requestDeleteDocument(item.id);
    footer.append(remove);
    card.append(button, footer);
    $('jobs').append(card);
    $('documentSelect').append(new Option(`${item.title} · ${item.stats.reviewed_percent}%`, item.id));
  }
  $('documentSelect').value = job?.id || '';
  $('deleteSelectedDocument').disabled = !job || pending || ['queued', 'running'].includes(job.status);
  if (!jobs.length) $('jobs').append(make('p', 'No documents match this search.', 'muted'));
}

async function openJob(id) {
  if (!confirmDiscard()) {
    $('documentSelect').value = job?.id || '';
    return;
  }
  setPending(true);
  try {
  const opened = await api(`/api/jobs/${id}`);
  job = opened;
  pageIndex = 0;
  selectedId = null;
  queuePageIndex = 0;
  batchSelection.clear();
  cancelAddToken();
  $('note').value = '';
  $('plainNote').value = '';
  setDirty(false);
  $('uploadPanel').hidden = true;
  $('work').hidden = false;
  render();
  await library();
  } catch (error) {
    $('documentSelect').value = job?.id || '';
    toast(error.message);
  } finally {
    setPending(false);
    if (job) {
      if (isPlain()) renderPlainButtons();
      else updateStructuredButtons();
    }
  }
}

function setExportFormats() {
  const mode = isPlain() ? 'plain' : 'structured';
  if ($('format').dataset.mode === mode) return;
  const formats = isPlain()
    ? [['txt', 'Plain text'], ['docx', 'Word document'], ['json', 'JSON + evidence']]
    : [['json', 'JSON'], ['csv', 'CSV'], ['sqlite3', 'SQLite'], ['sql', 'SQL']];
  $('format').replaceChildren(...formats.map(([value, label]) => {
    const option = make('option', label);
    option.value = value;
    return option;
  }));
  $('format').dataset.mode = mode;
  $('scope').value = isPlain() && !job.stats.reviewed ? 'draft' : 'reviewed';
}

function render() {
  if (!job) return;
  const plain = isPlain();
  $('jobTitle').textContent = job.title;
  $('jobStatus').textContent = job.status;
  const overlaySource = !plain && job.document.sources?.find(source =>
    /(?:^|[_. -])overlay(?:$|[_. -])/i.test(source.name.replace(/\.[^.]+$/, ''))
  );
  const jobWarning = job.error || (overlaySource
    ? `${overlaySource.name} is a generated box-overlay, not a clean scan. Its OCR is unreliable; upload the original source page again.`
    : '');
  $('jobError').hidden = !jobWarning;
  $('jobError').textContent = jobWarning;
  $('workLabel').textContent = plain ? 'TEXT OCR · PAGE REVIEW' : 'FORMAT-AWARE OCR · ENTRY REVIEW';
  const diagnostics = job.document.diagnostics || [];
  $('jobDiagnostics').hidden = !diagnostics.length;
  $('jobDiagnostics').textContent = diagnostics.join(' ');
  const pages = job.document.pages;
  $('jobRange').textContent = pages.length
    ? `Page ${Math.min(pageIndex + 1, pages.length)} of ${pages.length} · पेज नं. ${pages[0].book_page} से ${pages[pages.length - 1].book_page} तक`
    : 'Your scanned pages will appear here when OCR starts.';
  $('countPages').textContent = job.stats.pages;
  $('countTokens').textContent = plain ? (job.stats.words ?? job.stats.tokens) : job.stats.tokens;
  $('countReview').textContent = job.stats.needs_review;
  $('countDone').textContent = job.stats.reviewed;
  $('reviewPercent').textContent = `${job.stats.reviewed_percent}%`;
  $('progressFill').style.width = `${job.stats.reviewed_percent}%`;
  $('progressTrack').setAttribute('aria-valuenow', job.stats.reviewed_percent);
  $('labelTokens').textContent = plain ? 'words extracted' : 'tokens extracted';
  $('labelReview').textContent = plain ? 'pages need attention' : 'need attention';
  $('labelDone').textContent = plain ? 'pages reviewed' : 'human reviewed';
  $('structuredReview').hidden = plain;
  $('plainReview').hidden = !plain;
  $('montage').hidden = plain;
  $('mobileTabs').querySelector('[data-panel="queue"]').hidden = plain;
  $('mobileTabs').classList.toggle('plain-tabs', plain);
  const current = page();
  if (current) {
    const tokens = current.tokens || [];
    const percent = plain ? (current.status === 'reviewed' ? 100 : 0)
      : tokens.length ? Math.round(tokens.filter(t => ['reviewed', 'excluded'].includes(t.status)).length * 100 / tokens.length) : 100;
    $('jobRange').textContent += ` · this page ${percent}% reviewed`;
  }

  $('pageSelect').replaceChildren();
  for (const currentPage of job.document.pages) {
    const incomplete = plain ? currentPage.status !== 'reviewed' : currentPage.tokens?.some(token => token.status === 'needs_review');
    const option = make('option', `${incomplete ? '⚠' : '✓'} p. ${currentPage.book_page}`);
    option.value = currentPage.index;
    $('pageSelect').append(option);
  }
  $('pageSelect').value = String(pageIndex);
  setExportFormats();
  updateExportPreview();
  showMobilePanel(activeMobilePanel);

  if (plain) renderPlain();
  else renderStructured();
}

function renderStructured() {
  const currentPage = page();
  $('montage').disabled = !currentPage?.tokens?.some(token => token.status === 'needs_review');
  if (!currentPage) {
    $('scan').hidden = true;
    renderInspector();
    renderQueue();
    return;
  }
  $('scan').hidden = false;
  const source = `/api/jobs/${job.id}/pages/${pageIndex}/image`;
  if ($('pageImage').getAttribute('src') !== source) $('pageImage').src = source;
  $('overlay').setAttribute('viewBox', `0 0 ${currentPage.image_size[0]} ${currentPage.image_size[1]}`);
  $('overlay').replaceChildren();
  for (const token of currentPage.tokens) {
    if (token.status === 'excluded') continue;
    const boxes = token.boxes?.length ? token.boxes : [token.bbox];
    for (const box of boxes) {
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      const [x, y, x1, y1] = box;
      const attributes = {
        x, y, width: x1 - x, height: y1 - y,
        stroke: token.status === 'reviewed' ? '#348469' : token.status === 'needs_review' ? '#c2963d' : colors[token.rank]
      };
      for (const [key, value] of Object.entries(attributes)) rect.setAttribute(key, value);
      if (token.status === 'needs_review') rect.setAttribute('stroke-dasharray', '6 4');
      if (token.id === selectedId) rect.classList.add('selected');
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${token.remedy} · grade ${token.rank} · ${token.status}`;
      rect.append(title);
      rect.onclick = () => selectToken(token.id);
      $('overlay').append(rect);
    }
  }
  renderQueue();
  renderInspector();
}

function renderQueue() {
  $('queue').replaceChildren();
  const pageTokens = page()?.tokens || [];
  const reasons = [...new Set(pageTokens.flatMap(token => token.review_reasons || []))].sort();
  const currentReason = $('reasonFilter').value;
  const existingReasons = [...$('reasonFilter').options].slice(1).map(option => option.value);
  if (existingReasons.join('\n') !== reasons.join('\n')) {
    $('reasonFilter').replaceChildren(new Option('All reasons', 'all'),
      ...reasons.map(value => new Option(value.replaceAll('-', ' '), value)));
    $('reasonFilter').value = reasons.includes(currentReason) ? currentReason : 'all';
  }
  const matches = filteredQueueTokens();
  const pageCount = Math.max(1, Math.ceil(matches.length / queuePageSize));
  queuePageIndex = Math.max(0, Math.min(queuePageIndex, pageCount - 1));
  const visible = matches.slice(queuePageIndex * queuePageSize, (queuePageIndex + 1) * queuePageSize);
  for (const token of visible) {
    const row = make('div', undefined, `queue-row${token.id === selectedId ? ' active' : ''}`);
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = batchSelection.has(token.id);
    check.setAttribute('aria-label', `Select ${token.remedy} for batch action`);
    check.onchange = () => check.checked ? batchSelection.add(token.id) : batchSelection.delete(token.id);
    const button = make('button', undefined, token.id === selectedId ? 'active' : '');
    button.append(
      make('span', `${statusIcon(token.status)} ${token.remedy} · grade ${token.rank}`),
      make('small', `${token.rubric || 'Rubric needs assignment'}${token.chapter ? ` · ${token.chapter}` : ''}`),
      make('small', token.status.replaceAll('_', ' '))
    );
    button.onclick = () => selectToken(token.id);
    row.append(check, button);
    $('queue').append(row);
  }
  if (!matches.length) $('queue').append(make('p', 'No tokens in this view.', 'muted'));
  $('queuePage').textContent = matches.length ? `${queuePageIndex * queuePageSize + 1}–${Math.min((queuePageIndex + 1) * queuePageSize, matches.length)} of ${matches.length}` : '0 results';
  $('queuePrevious').disabled = queuePageIndex === 0;
  $('queueNext').disabled = queuePageIndex >= pageCount - 1;
}

function filteredQueueTokens() {
  const filter = $('filter').value;
  const activeReason = $('reasonFilter').value;
  const search = $('search').value.toLowerCase();
  return (page()?.tokens || []).filter(token =>
    (filter === 'all' || token.status === filter) &&
    (activeReason === 'all' || token.review_reasons?.includes(activeReason)) &&
    `${token.remedy} ${token.rubric}`.toLowerCase().includes(search)
  );
}

function revealQueueSelection() {
  const index = filteredQueueTokens().findIndex(token => token.id === selectedId);
  queuePageIndex = index < 0 ? 0 : Math.floor(index / queuePageSize);
}

function statusIcon(status) {
  return {needs_review: '⚠', machine_accepted: '◇', reviewed: '✓', excluded: '⊘'}[status] || '•';
}

function selectToken(id) {
  if (id === selectedId || !confirmDiscard()) return;
  selectedId = id;
  setDirty(false);
  $('note').value = '';
  revealQueueSelection();
  render();
  if (window.matchMedia('(max-width: 850px)').matches) showMobilePanel('inspector');
  const token = selected();
  const currentPage = page();
  if (token && currentPage) {
    const ratio = $('pageImage').clientWidth / currentPage.image_size[0];
    $('scanViewport').scrollTop = Math.max(0, token.bbox[1] * ratio - 170);
  }
  if ($('history').open) history();
}

function renderInspector() {
  const token = selected();
  $('emptyInspector').hidden = !!token;
  $('tokenPanel').hidden = !token;
  updateStructuredButtons();
  if (!token) return;
  for (const id of ['remedy', 'rubric', 'rank']) $(id).value = token[id];
  $('chapter').value = token.chapter || '';
  $('tokenMeta').textContent = `${statusIcon(token.status)} ${token.status.replaceAll('_', ' ')} · ${token.id.slice(0, 8)} · version ${token.version}`;
  const machine = token.machine;
  $('evidence').replaceChildren(
    make('div', `Raw OCR: ${token.raw}`),
    make('div', `Machine grade ${machine.rank ?? 'manual'} · confidence ${Number(machine.confidence || 0).toFixed(2)}`),
    make('div', `Scalar ${machine.scalar_rank ?? '—'} · MLP ${machine.mlp_rank ?? '—'} · Shape ${machine.shape_rank ?? '—'}`),
    make('div', `Weight ${machine.features?.weight ?? '—'} · slant ${machine.features?.slant ?? '—'}°`)
  );
  if (token.review_reasons.length) {
    $('evidence').append(make('div', token.review_reasons.join(' · ').replaceAll('-', ' '), 'reason'));
  }
  drawCrop();
}

function updateStructuredButtons() {
  const unavailable = pending || !page() || ['running', 'queued'].includes(job?.status);
  for (const id of ['save', 'exclude', 'splitToken', 'mergeTokens', 'inheritContext', 'remedy', 'rubric', 'chapter', 'rank', 'note']) {
    $(id).disabled = unavailable || !selected();
  }
  $('addToken').disabled = unavailable;
  $('applyBatch').disabled = unavailable;
}

function drawCrop() {
  const token = selected();
  const image = $('pageImage');
  if (!token || !image.complete || !image.naturalWidth) return;
  const canvas = $('crop');
  const context = canvas.getContext('2d');
  context.fillStyle = '#f7f3e9';
  context.fillRect(0, 0, canvas.width, canvas.height);
  const boxes = token.boxes?.length ? token.boxes : [token.bbox];
  if (boxes.length === 1) {
    const [x, y, x1, y1] = boxes[0];
    const sx = Math.max(0, x - 12);
    const sy = Math.max(0, y - 8);
    const sw = Math.min(image.naturalWidth - sx, x1 - x + 24);
    const sh = Math.min(image.naturalHeight - sy, y1 - y + 16);
    const scale = Math.min((canvas.width - 25) / sw, (canvas.height - 20) / sh, 4);
    context.drawImage(image, sx, sy, sw, sh, (canvas.width - sw * scale) / 2,
      (canvas.height - sh * scale) / 2, sw * scale, sh * scale);
    return;
  }
  const crops = boxes.map(([x, y, x1, y1]) => ({
    sx: Math.max(0, x - 8), sy: Math.max(0, y - 6),
    sw: Math.min(image.naturalWidth - Math.max(0, x - 8), x1 - x + 16),
    sh: Math.min(image.naturalHeight - Math.max(0, y - 6), y1 - y + 12)
  }));
  const totalWidth = crops.reduce((sum, crop) => sum + crop.sw, 0) + (crops.length - 1) * 16;
  const maxHeight = Math.max(...crops.map(crop => crop.sh));
  const scale = Math.min((canvas.width - 30) / totalWidth, (canvas.height - 20) / maxHeight, 3.5);
  let currentX = (canvas.width - totalWidth * scale) / 2;
  for (const crop of crops) {
    const width = crop.sw * scale;
    const height = crop.sh * scale;
    const drawY = (canvas.height - height) / 2;
    context.drawImage(image, crop.sx, crop.sy, crop.sw, crop.sh, currentX, drawY, width, height);
    context.strokeStyle = '#c2bca9';
    context.strokeRect(currentX, drawY, width, height);
    currentX += width + 16 * scale;
  }
}

function nextReviewTarget() {
  const targets = job.document.pages.flatMap((currentPage, index) =>
    (currentPage.tokens || []).map(token => ({page: index, token: token.id, status: token.status})));
  const start = targets.findIndex(target => target.token === selectedId);
  for (let offset = 1; offset <= targets.length; offset += 1) {
    const target = targets[(start + offset) % targets.length];
    if (target.status === 'needs_review') return target;
  }
  return null;
}

function reviewTargets() {
  return job.document.pages.flatMap((currentPage, currentPageIndex) =>
    (currentPage.tokens || []).filter(token => token.status === 'needs_review')
      .map(token => ({page: currentPageIndex, token: token.id})));
}

function moveReview(direction) {
  if (!job || isPlain()) return;
  if (!confirmDiscard()) return;
  const targets = reviewTargets();
  if (!targets.length) return toast('No incomplete tokens remain.');
  let index = targets.findIndex(target => target.page === pageIndex && target.token === selectedId);
  if (index < 0) index = direction > 0 ? -1 : 0;
  const target = targets[(index + direction + targets.length) % targets.length];
  if (pageIndex !== target.page) batchSelection.clear();
  pageIndex = target.page;
  selectedId = target.token;
  revealQueueSelection();
  $('note').value = '';
  cancelAddToken();
  setDirty(false);
  render();
}

function inheritContext() {
  const tokens = page()?.tokens || [];
  const index = tokens.findIndex(token => token.id === selectedId);
  const previous = tokens.slice(0, index).reverse().find(token => token.rubric || token.chapter);
  if (!previous) return toast('No earlier Chapter or Rubric is available on this page.');
  if (previous.rubric) $('rubric').value = previous.rubric;
  if (previous.chapter) $('chapter').value = previous.chapter;
  setDirty(true);
  toast('Previous Chapter and Rubric copied. Save to apply.');
}

async function save(exclude = false, advance = true) {
  const token = selected();
  if (!token || pending || ['running', 'queued'].includes(job.status)) return;
  const reviewer = $('reviewer').value.trim();
  if (!reviewer) {
    $('reviewer').focus();
    toast('Enter your name to record this decision.');
    return;
  }
  if (!exclude && !$('decision').reportValidity()) return;
  const decision = {
    expected_version: token.version,
    rank: Number($('rank').value),
    remedy: $('remedy').value,
    rubric: $('rubric').value,
    chapter: $('chapter').value,
    reviewer,
    note: $('note').value,
    exclude
  };
  setPending(true);
  updateStructuredButtons();
  let saved = false;
  try {
    await api(`/api/jobs/${job.id}/tokens/${token.id}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(decision)
    });
    localStorage.setItem('folio-reviewer', reviewer);
    job = await api(`/api/jobs/${job.id}`);
    const next = advance ? nextReviewTarget() : null;
    if (next) {
      if (pageIndex !== next.page) batchSelection.clear();
      pageIndex = next.page;
      selectedId = next.token;
    }
    revealQueueSelection();
    setDirty(false);
    saved = true;
    $('note').value = '';
    toast(exclude ? 'Token excluded; evidence retained.' : advance && next ? 'Review saved. Moving to the next issue.' : 'Review saved.');
    await library();
  } catch (error) {
    toast(error.message);
  } finally {
    setPending(false);
    if (saved) render();
    else updateStructuredButtons();
    if ($('history').open) history();
  }
}

async function applyBatch() {
  if (!job || !confirmDiscard()) return;
  const reviewer = $('batchReviewer').value.trim() || $('reviewer').value.trim();
  if (!reviewer) return toast('Enter a reviewer name for the batch assignment.');
  const scope = $('batchScope').value;
  let tokenIds = [];
  if (scope === 'selected') tokenIds = [...batchSelection];
  if (scope === 'filtered') {
    tokenIds = filteredQueueTokens().map(token => token.id);
  }
  if (scope !== 'needs_review' && !tokenIds.length) return toast('No tokens selected or matched. Nothing was changed.');
  const payload = {token_ids: tokenIds, reviewer,
    chapter: $('batchChapter').value || undefined, rubric: $('batchRubric').value || undefined};
  if (scope === 'needs_review') payload.status = 'needs_review';
  if (!payload.chapter && !payload.rubric) return toast('Enter a Chapter or Rubric to assign.');
  setPending(true);
  try {
    const result = await api(`/api/jobs/${job.id}/bulk-assign`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    job = await api(`/api/jobs/${job.id}`);
    batchSelection.clear();
    setDirty(false);
    render();
    toast(`Batch assignment updated ${result.changed} tokens.`);
  } catch (error) { toast(error.message); }
  finally { setPending(false); updateStructuredButtons(); }
}

async function splitSelectedToken() {
  const token = selected();
  if (!token || !confirmDiscard()) return;
  const input = await promptValue('Enter remedies separated by semicolons:', token.remedy.replaceAll(',', ';'));
  if (!input) return;
  const remedies = input.split(';').map(value => value.trim()).filter(Boolean);
  if (remedies.length < 2) return toast('Enter at least two remedies separated by semicolons.');
  const reviewer = $('reviewer').value.trim();
  if (!reviewer) return toast('Enter your reviewer name first.');
  setPending(true);
  try {
    const parts = await api(`/api/jobs/${job.id}/tokens/${token.id}/split`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({expected_version: token.version, remedies, reviewer})});
    job = await api(`/api/jobs/${job.id}`);
    selectedId = parts[0].id;
    batchSelection.clear();
    setDirty(false);
    render();
    toast(`Token split into ${parts.length} entries.`);
  } catch (error) { toast(error.message); }
  finally { setPending(false); updateStructuredButtons(); }
}

async function mergeSelectedTokens() {
  if (!job || !confirmDiscard()) return;
  const tokenIds = [...batchSelection];
  if (selectedId && !tokenIds.includes(selectedId)) tokenIds.unshift(selectedId);
  if (tokenIds.length < 2) return toast('Select at least two queue tokens to merge.');
  const tokens = (page()?.tokens || []).filter(token => tokenIds.includes(token.id));
  if (tokens.length !== tokenIds.length) return toast('Merge selections must be on the current page.');
  const remedy = await promptValue('Merged remedy text:', tokens.map(token => token.remedy).join(' '));
  if (!remedy) return;
  const reviewer = $('reviewer').value.trim();
  if (!reviewer) return toast('Enter your reviewer name first.');
  setPending(true);
  try {
    const merged = await api(`/api/jobs/${job.id}/tokens/merge`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token_ids: tokenIds, expected_versions: Object.fromEntries(tokens.map(t => [t.id, t.version])),
        remedy, rubric: tokens[0].rubric, chapter: tokens[0].chapter || '', rank: tokens[0].rank, reviewer})});
    job = await api(`/api/jobs/${job.id}`);
    selectedId = merged.id;
    batchSelection.clear();
    setDirty(false);
    render();
    toast(`${tokenIds.length} tokens merged.`);
  } catch (error) { toast(error.message); }
  finally { setPending(false); updateStructuredButtons(); }
}

function svgPoint(event) {
  const rect = $('overlay').getBoundingClientRect();
  const currentPage = page();
  return [Math.max(0, Math.min(currentPage.image_size[0], Math.round((event.clientX - rect.left) * currentPage.image_size[0] / rect.width))),
    Math.max(0, Math.min(currentPage.image_size[1], Math.round((event.clientY - rect.top) * currentPage.image_size[1] / rect.height)))];
}

function cancelAddToken() {
  addTokenMode = false;
  addStart = null;
  $('overlay').classList.remove('adding-token');
  $('addTokenHint').hidden = true;
}

async function finishAddToken(event) {
  if (!addTokenMode || !addStart) return;
  const end = svgPoint(event);
  const bbox = [Math.min(addStart[0], end[0]), Math.min(addStart[1], end[1]), Math.max(addStart[0], end[0]), Math.max(addStart[1], end[1])];
  cancelAddToken();
  if (!confirmDiscard()) return;
  if (bbox[2] - bbox[0] < 4 || bbox[3] - bbox[1] < 4) return toast('Draw a larger box for the missing token.');
  const remedy = await promptValue('Remedy text for the missing token:', '');
  if (!remedy) return;
  const rubric = await promptValue('Rubric:', $('rubric').value || selected()?.rubric || '');
  if (!rubric) return;
  const reviewer = $('reviewer').value.trim();
  if (!reviewer) return toast('Enter your reviewer name before adding a token.');
  setPending(true);
  try {
    const token = await api(`/api/jobs/${job.id}/pages/${pageIndex}/tokens`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({bbox, remedy, rubric, chapter: $('chapter').value || '', rank: Number($('rank').value || 2), reviewer})});
    job = await api(`/api/jobs/${job.id}`);
    selectedId = token.id;
    setDirty(false);
    render();
    toast('Missing token added and marked reviewed.');
  } catch (error) { toast(error.message); }
  finally { setPending(false); updateStructuredButtons(); }
}

async function history() {
  const token = selected();
  if (!token) return;
  try {
    const events = await api(`/api/jobs/${job.id}/events?token_id=${token.id}`);
    $('historyItems').replaceChildren();
    for (const event of events) {
      $('historyItems').append(make('div',
        `${event.reviewer} · ${new Date(event.at).toLocaleString()} · grade ${event.before_json?.rank ?? 'added'} → ${event.after_json?.rank ?? 'removed'}${event.note ? ` · ${event.note}` : ''}`,
        'history-item'));
    }
    if (!events.length) $('historyItems').append(make('p', 'No human decisions yet.', 'muted'));
  } catch (error) {
    toast(error.message);
  }
}

function renderPlain() {
  const currentPage = page();
  renderPlainButtons();
  if (!currentPage) {
    $('plainText').value = '';
    $('plainPageImage').removeAttribute('src');
    $('plainPageLabel').textContent = 'Waiting for scanned pages…';
    $('plainPageStatus').textContent = '';
    $('plainConfidence').textContent = '';
    $('plainWordCount').textContent = '';
    $('plainReasons').hidden = true;
    return;
  }
  const source = `/api/jobs/${job.id}/pages/${pageIndex}/image`;
  if ($('plainPageImage').getAttribute('src') !== source) $('plainPageImage').src = source;
  $('plainText').value = currentPage.text || '';
  $('plainPageLabel').textContent = `Printed page ${currentPage.book_page}`;
  $('plainPageStatus').textContent = currentPage.status.replaceAll('_', ' ');
  $('plainConfidence').textContent = `OCR confidence ${Math.round((currentPage.ocr_confidence || 0) * 100)}%`;
  $('plainWordCount').textContent = `${countWords(currentPage.text)} words`;
  $('plainReasons').hidden = !currentPage.review_reasons?.length;
  $('plainReasons').textContent = (currentPage.review_reasons || []).join(' · ').replaceAll('-', ' ');
  setDirty(false);
}

function countWords(text) {
  return (text || '').trim() ? (text || '').trim().split(/\s+/).length : 0;
}

function navigatePage(target) {
  if (target < 0 || target >= (job?.document.pages.length || 0)) return;
  if (!confirmDiscard()) {
    $('pageSelect').value = String(pageIndex);
    return;
  }
  pageIndex = target;
  selectedId = null;
  queuePageIndex = 0;
  batchSelection.clear();
  cancelAddToken();
  $('note').value = '';
  $('plainNote').value = '';
  setDirty(false);
  render();
  window.scrollTo({top: 0, behavior: 'smooth'});
  if (isPlain() && $('plainHistory').open) plainHistory();
}

async function savePlain(advance) {
  const currentPage = page();
  if (!currentPage || pending || ['queued', 'running'].includes(job.status)) return;
  const reviewer = $('plainReviewer').value.trim();
  if (!reviewer) {
    $('plainReviewer').focus();
    toast('Enter your name to record this page review.');
    return;
  }
  const decision = {
    expected_version: currentPage.version,
    text: $('plainText').value,
    reviewer,
    note: $('plainNote').value
  };
  setPending(true);
  renderPlainButtons();
  let saved = false;
  try {
    await api(`/api/jobs/${job.id}/pages/${pageIndex}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(decision)
    });
    localStorage.setItem('folio-reviewer', reviewer);
    localStorage.setItem('folio-plain-reviewer', reviewer);
    job = await api(`/api/jobs/${job.id}`);
    if (advance && pageIndex < job.document.pages.length - 1) pageIndex += 1;
    $('plainNote').value = '';
    setDirty(false);
    saved = true;
    toast(advance ? 'Page saved. Moving to the next page.' : 'Page review saved.');
    await library();
  } catch (error) {
    toast(error.message);
  } finally {
    setPending(false);
    if (saved) render();
    else renderPlainButtons();
    if ($('plainHistory').open) plainHistory();
  }
}

function renderPlainButtons() {
  const unavailable = pending || !page() || ['queued', 'running'].includes(job?.status);
  $('plainText').readOnly = unavailable;
  $('plainSave').disabled = unavailable;
  $('plainSaveNext').disabled = unavailable;
  $('plainSkip').disabled = pending || !page() || pageIndex >= (job?.document.pages.length || 0) - 1;
  $('plainPrevious').disabled = pending || pageIndex === 0;
  $('plainNext').disabled = pending || pageIndex >= (job?.document.pages.length || 0) - 1;
}

async function plainHistory() {
  if (!page()) return;
  try {
    const events = await api(`/api/jobs/${job.id}/events?token_id=page:${pageIndex}`);
    $('plainHistoryItems').replaceChildren();
    for (const event of events) {
      const beforeWords = countWords(event.before_json.text);
      const afterWords = countWords(event.after_json.text);
      $('plainHistoryItems').append(make('div',
        `${event.reviewer} · ${new Date(event.at).toLocaleString()} · ${beforeWords} → ${afterWords} words${event.note ? ` · ${event.note}` : ''}`,
        'history-item'));
    }
    if (!events.length) $('plainHistoryItems').append(make('p', 'No page edits yet.', 'muted'));
  } catch (error) {
    toast(error.message);
  }
}

function updateUploadMode() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const plain = mode === 'plain';
  $('plainFields').hidden = !plain;
  $('structuredFields').hidden = plain;
  $('profileNote').textContent = plain
    ? 'TXT · Word (.docx) · JSON'
    : 'JSON · CSV · SQLite · SQL';
}

function nextIncompletePage() {
  if (!job || pending) return;
  const pages = job.document.pages;
  for (let offset = 1; offset <= pages.length; offset += 1) {
    const candidate = (pageIndex + offset) % pages.length;
    const incomplete = isPlain() ? pages[candidate].status !== 'reviewed'
      : pages[candidate].tokens?.some(token => token.status === 'needs_review');
    if (incomplete) return navigatePage(candidate);
  }
  toast('All pages are complete.');
}

async function updateExportPreview() {
  const request = ++exportPreviewRequest;
  lastExportPreview = null;
  $('export').disabled = true;
  if (!job || !job.stats.pages) {
    $('exportPreview').textContent = 'Export becomes available after OCR finds pages.';
    $('export').disabled = true;
    return;
  }
  try {
    const preview = await api(`/api/jobs/${job.id}/export-preview?format=${$('format').value}&scope=${$('scope').value}`);
    if (request !== exportPreviewRequest) return;
    lastExportPreview = preview;
    const message = `${lastExportPreview.valid ? '✓' : '⚠'} Estimated ${lastExportPreview.row_count} rows` +
      (lastExportPreview.incomplete_count ? ` · ${lastExportPreview.incomplete_count} incomplete` : '') +
      (lastExportPreview.errors.length ? ` · ${lastExportPreview.errors.join(' ')}` : ' · combination ready');
    $('exportPreview').textContent = message;
    $('exportPreview').classList.toggle('invalid', !lastExportPreview.valid);
    $('export').disabled = !lastExportPreview.valid || ['queued', 'running'].includes(job.status);
  } catch (error) {
    if (request !== exportPreviewRequest) return;
    $('exportPreview').textContent = `⚠ ${error.message}`;
    $('export').disabled = true;
  }
}

function showMobilePanel(panel) {
  activeMobilePanel = isPlain() && panel === 'queue' ? 'inspector' : panel;
  for (const button of $('mobileTabs').querySelectorAll('button')) {
    button.classList.toggle('active', button.dataset.panel === activeMobilePanel);
    button.setAttribute('aria-pressed', String(button.dataset.panel === activeMobilePanel));
  }
  for (const element of document.querySelectorAll('.review-panel')) element.classList.toggle('mobile-active', element.dataset.panel === activeMobilePanel);
}

async function renameCurrentJob() {
  if (!job || !confirmDiscard()) return;
  const title = await promptValue('New unique document name:', job.title);
  if (!title || title.trim() === job.title) return;
  setPending(true);
  try {
    job = await api(`/api/jobs/${job.id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title})});
    setDirty(false);
    await library();
    render();
    toast(`Renamed to “${job.title}”.`);
  } catch (error) { toast(error.message); }
  finally { setPending(false); if (isPlain()) renderPlainButtons(); else updateStructuredButtons(); }
}

async function deleteCurrentJob() {
  if (job) requestDeleteDocument(job.id);
}

function requestDeleteDocument(id) {
  if (pending || (job?.id === id && !confirmDiscard())) return;
  const item = libraryItems.find(item => item.id === id) || (job?.id === id ? job : null);
  if (!item || ['queued', 'running'].includes(item.status)) return;
  deleteTarget = item;
  $('deleteDocumentName').textContent = item.title;
  $('deleteDialogError').hidden = true;
  $('deleteDialog').showModal();
  $('cancelDelete').focus();
}

function cancelDeleteDocument() {
  if (pending) return;
  deleteTarget = null;
  $('deleteDialog').close();
}

async function confirmDeleteDocument() {
  if (!deleteTarget || pending) return;
  const id = deleteTarget.id;
  setPending(true);
  $('confirmDelete').disabled = true;
  $('cancelDelete').disabled = true;
  $('deleteDialogError').hidden = true;
  try {
    await api(`/api/jobs/${id}`, {method: 'DELETE'});
    if (job?.id === id) {
    job = null;
    selectedId = null;
    setDirty(false);
    batchSelection.clear();
    cancelAddToken();
    $('work').hidden = true;
    $('uploadPanel').hidden = false;
    }
    await library();
    deleteTarget = null;
    $('deleteDialog').close();
    toast('Document deleted.');
  } catch (error) {
    $('deleteDialogError').textContent = error.message;
    $('deleteDialogError').hidden = false;
  } finally {
    setPending(false);
    $('confirmDelete').disabled = false;
    $('cancelDelete').disabled = false;
    $('deleteSelectedDocument').disabled = !job || ['queued', 'running'].includes(job.status);
  }
}

$('newJob').onclick = () => {
  if (!confirmDiscard()) return;
  setDirty(false);
  job = null;
  selectedId = null;
  batchSelection.clear();
  cancelAddToken();
  $('documentSelect').value = '';
  $('work').hidden = true;
  $('uploadPanel').hidden = false;
  renderLibrary();
  $('uploadPanel').scrollIntoView({behavior: 'smooth'});
  $('documentTitle').focus({preventScroll: true});
};

function updatePageRange() {
  const start = Number($('startPage').value);
  const endValue = $('endPage').value;
  $('endPage').min = String(start);
  $('endPage').setCustomValidity(endValue !== '' && Number(endValue) < start
    ? 'The last page must be the same as or greater than the first page.' : '');
  const files = [...$('files').files];
  const singlePages = files.length && files.every(file => /\.(png|jpe?g|webp|jp2)$/i.test(file.name));
  $('endPage').placeholder = singlePages ? String(start + files.length - 1) : 'Automatic';
  const totalMB = files.reduce((total, file) => total + file.size, 0) / (1024 * 1024);
  $('files').setCustomValidity(files.length > 100 ? 'Select up to 100 files.'
    : totalMB > 500 ? 'Total upload exceeds 500 MB.' : '');
  const heading = files.length ? `${files.length} ${files.length === 1 ? 'file' : 'files'} ready to upload` : 'No files added';
  const detail = files.length ? `${totalMB.toFixed(1)} MB · ${singlePages
    ? `Pages ${start}–${start + files.length - 1}` : 'PDF and TIFF page counts are calculated during OCR.'}`
    : 'Select at least one scan or PDF to begin.';
  $('fileSummary').replaceChildren(make('strong', heading), make('span', detail));
}

$('upload').onsubmit = async event => {
  event.preventDefault();
  updatePageRange();
  if (!event.target.reportValidity()) return;
  if (!confirmDiscard()) return;
  setDirty(false);
  const mode = new FormData(event.target).get('mode');
  if (mode === 'structured' && !$('uploadChapter').value.trim() &&
      !window.confirm('Chapter is empty. You can continue and batch-assign it later; structured exports will keep Chapter blank until then. Continue?')) return;
  const generatedOverlay = [...$('files').files].find(file => /(?:^|[_. -])overlay(?:$|[_. -])/i.test(file.name.replace(/\.[^.]+$/, '')));
  if (mode === 'structured' && generatedOverlay) {
    toast(`${generatedOverlay.name} is an annotated OCR overlay. Choose the original clean scan instead.`);
    return;
  }
  $('uploadButton').disabled = true;
  $('uploadButton').textContent = 'Uploading…';
  try {
    const data = new FormData(event.target);
    if (data.get('end_page') === '') data.delete('end_page');
    const created = await api('/api/jobs', {method: 'POST', body: data});
    await openJob(created.id);
  } catch (error) {
    toast(error.message);
  } finally {
    $('uploadButton').disabled = false;
    $('uploadButton').textContent = 'Start OCR';
  }
};

for (const radio of document.querySelectorAll('input[name="mode"]')) radio.onchange = updateUploadMode;
for (const id of ['startPage', 'endPage']) $(id).oninput = updatePageRange;
$('files').onchange = updatePageRange;
$('pageSelect').onchange = event => navigatePage(Number(event.target.value));
$('pageImage').onload = drawCrop;
$('filter').onchange = () => { queuePageIndex = 0; renderQueue(); };
$('reasonFilter').onchange = () => { queuePageIndex = 0; renderQueue(); };
$('search').oninput = () => { queuePageIndex = 0; renderQueue(); };
$('decision').onsubmit = event => { event.preventDefault(); save(); };
$('exclude').onclick = () => save(true);
$('previousToken').onclick = () => moveReview(-1);
$('skipToken').onclick = () => moveReview(1);
$('inheritContext').onclick = inheritContext;
$('queuePrevious').onclick = () => { queuePageIndex -= 1; renderQueue(); };
$('queueNext').onclick = () => { queuePageIndex += 1; renderQueue(); };
$('applyBatch').onclick = applyBatch;
$('splitToken').onclick = splitSelectedToken;
$('mergeTokens').onclick = mergeSelectedTokens;
$('addToken').onclick = async () => {
  if (!job || !page() || pending || ['running', 'queued'].includes(job.status)) return;
  if (!$('reviewer').value.trim()) {
    const reviewer = await promptValue('Reviewer name for the missing token:', '');
    if (!reviewer?.trim()) return;
    $('reviewer').value = reviewer.trim();
  }
  addTokenMode = true;
  $('overlay').classList.add('adding-token');
  $('addTokenHint').hidden = false;
  showMobilePanel('scan');
  toast('Drag a box over the missing token on the scan.');
};
$('overlay').addEventListener('pointerdown', event => {
  if (!addTokenMode) return;
  event.preventDefault();
  $('overlay').setPointerCapture(event.pointerId);
  addStart = svgPoint(event);
});
$('overlay').addEventListener('pointerup', finishAddToken);
$('overlay').addEventListener('pointercancel', cancelAddToken);
$('history').ontoggle = () => { if ($('history').open) history(); };
$('plainHistory').ontoggle = () => { if ($('plainHistory').open) plainHistory(); };
$('montage').onclick = () => window.open(`/api/jobs/${job.id}/pages/${pageIndex}/montage`, '_blank', 'noopener');

for (const id of ['remedy', 'rubric', 'chapter', 'rank', 'note']) {
  $(id).addEventListener('input', () => setDirty(true));
}
$('plainText').addEventListener('input', () => {
  setDirty(true);
  $('plainWordCount').textContent = `${countWords($('plainText').value)} words · unsaved`;
});
$('plainNote').addEventListener('input', () => setDirty(true));
$('plainPrevious').onclick = () => navigatePage(pageIndex - 1);
$('plainNext').onclick = () => navigatePage(pageIndex + 1);
$('plainSkip').onclick = () => navigatePage(Math.min(pageIndex + 1, job.document.pages.length - 1));
$('plainSave').onclick = () => savePlain(false);
$('plainSaveNext').onclick = () => savePlain(true);
$('nextIncomplete').onclick = nextIncompletePage;
$('renameJob').onclick = renameCurrentJob;
$('deleteJob').onclick = deleteCurrentJob;
$('deleteSelectedDocument').onclick = deleteCurrentJob;
$('cancelDelete').onclick = cancelDeleteDocument;
$('confirmDelete').onclick = confirmDeleteDocument;
$('deleteDialog').addEventListener('cancel', event => { event.preventDefault(); cancelDeleteDocument(); });
$('documentSearch').oninput = renderLibrary;
$('documentSelect').onchange = event => { if (event.target.value) openJob(event.target.value); };
for (const button of $('mobileTabs').querySelectorAll('button')) button.onclick = () => showMobilePanel(button.dataset.panel);
$('scope').onchange = updateExportPreview;
$('format').onchange = updateExportPreview;

$('export').onclick = async () => {
  if (!job || pending) return;
  try {
    await updateExportPreview();
    if (!lastExportPreview?.valid) throw Error(lastExportPreview?.errors?.join(' ') || 'This export combination is not ready.');
    const format = $('format').value;
    const scope = $('scope').value;
    const response = await fetch(`/api/jobs/${job.id}/export?format=${format}&scope=${scope}`);
    if (!response.ok) {
      const detail = await response.json();
      throw Error(detail.detail);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = make('a');
    anchor.href = url;
    anchor.download = `folio-${scope}.${format}`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    toast(error.message);
  }
};

window.addEventListener('beforeunload', event => {
  if (!dirty) return;
  event.preventDefault();
  event.returnValue = '';
});

document.addEventListener('keydown', event => {
  if ($('inputDialog').open || $('deleteDialog').open) return;
  if (!job) return;
  const editing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName);
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && job) {
    event.preventDefault();
    if (isPlain()) savePlain(false);
    else save(false, false);
  }
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && job) {
    event.preventDefault();
    if (isPlain()) savePlain(true);
    else save(false);
  }
  if (event.altKey && ['ArrowRight', 'ArrowLeft'].includes(event.key)) {
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    if (isPlain()) navigatePage(pageIndex + direction);
    else moveReview(direction);
  }
  if (!editing && event.key.toLowerCase() === 's' && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    if (isPlain()) navigatePage(pageIndex + 1);
    else moveReview(1);
  }
  if (event.key === 'Escape') cancelAddToken();
});

$('reviewer').value = localStorage.getItem('folio-reviewer') || '';
$('plainReviewer').value = localStorage.getItem('folio-plain-reviewer') || localStorage.getItem('folio-reviewer') || '';

$('inputDialogForm').onsubmit = event => {
  event.preventDefault();
  finishPrompt($('inputDialogValue').value);
};
$('inputDialogCancel').onclick = () => finishPrompt(null);
$('inputDialog').addEventListener('cancel', event => {
  event.preventDefault();
  finishPrompt(null);
});

async function init() {
  updateUploadMode();
  updatePageRange();
  try {
    const health = await api('/api/health');
    $('health').textContent = health.tesseract_available ? 'Local · ready' : 'Tesseract missing';
    await library();
  } catch (error) {
    $('health').textContent = 'Connection unavailable';
    toast(error.message);
  }
}

setInterval(async () => {
  if (!job || !['queued', 'running'].includes(job.status)) return;
  try {
    job = await api(`/api/jobs/${job.id}`);
    render();
    await library();
  } catch (error) {
    toast(error.message);
  }
}, 2500);

init();
