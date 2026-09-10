/* Scenario materials are data, never fetched URLs or executable instructions. */
const scenarioMaterials = { draft: null, generation: 0, busy: false, loading: false, dirty: false, account: null };
const librarySources = {};
let projectSources;

function checkedSourceValues(sources) {
  if (sources.length > 20) throw new Error('Use at most 20 reference documents.');
  let total = 0;
  const names = new Set();
  return sources.map(source => {
    const filename = source.filename.trim(), text = source.text, url = (source.url || '').trim();
    if (filename.length > 120 || !/^[A-Za-z0-9][A-Za-z0-9_. -]{0,116}\.(txt|md|pdf)$/.test(filename)) throw new Error('Give each source a simple, distinct .txt, .md or .pdf filename.');
    if (names.has(filename.toLowerCase())) throw new Error('Each reference needs a distinct filename.');
    names.add(filename.toLowerCase());
    if (!text.trim() || [...text].length > 250000) throw new Error('Each reference needs text, up to 250,000 characters.');
    total += new TextEncoder().encode(text).length;
    if (total > 750000) throw new Error('Reference text exceeds 750 KB in total. Use relevant excerpts or summaries.');
    if (url) {
      let parsed;
      try { parsed = new URL(url); } catch (_) { throw new Error('Source links must be complete HTTPS URLs.'); }
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error('Use HTTPS source links without embedded credentials.');
    }
    return { filename, text, ...(url ? { url } : {}) };
  });
}

class SourceEditor {
  constructor(host, changed) {
    this.host = host; this.changed = changed; this.sources = [];
    this.generation = 0; this.busy = false; this.editable = true;
    this.metadata = new Map(); this.editing = null; this.editDirty = false;
  }
  reset(sources = [], editable = true, preserveMetadata = false) {
    this.generation++; this.busy = false; this.editable = editable;
    if (!preserveMetadata) this.metadata.clear();
    this.sources = structuredClone(sources); this.editing = null; this.editDirty = false; this.render();
  }
  value() {
    if (this.busy) throw new Error('Wait for document extraction to finish.');
    if (this.editDirty) throw new Error('Use Keep document or Cancel in the document form before saving the scenario.');
    return checkedSourceValues(this.sources);
  }
  warnings() { return [...this.metadata.values()].flatMap(metadata => metadata.warnings || []); }
  retainedBytes() { return this.sources.reduce((total, source) => total + new TextEncoder().encode(source.text).length, 0); }
  render() {
    const prefix = this.host.id;
    this.host.classList.add('authoring-sources');
    this.host.innerHTML = this.sources.length ? `<div class="authoring-document-scroll"><table class="authoring-documents"><caption class="visually-hidden">Reference documents retained in this draft</caption><thead><tr><th scope="col">Document</th><th scope="col">Retained text</th><th scope="col">Actions</th></tr></thead><tbody>${this.sources.map((source, index) => {
      const bytes = new TextEncoder().encode(source.text).length, metadata = this.metadata.get(source.filename);
      const type = source.filename.split('.').pop().toUpperCase();
      return `<tr data-source-row="${index}"><th scope="row">${escapeHtml(source.filename)}<small>${escapeHtml(type)}${type === 'PDF' ? ' extracted text' : ''}${metadata?.page_count ? ', ' + metadata.page_count + ' pages in uploaded file' : ''}</small></th>
        <td>${[...source.text].length.toLocaleString()} characters<small>${(bytes / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })} KB UTF-8</small></td>
        <td><div class="authoring-source-actions"><button type="button" class="btn btn-small" data-open-source="${index}" aria-label="Open ${escapeAttr(source.filename)}">Open</button>${this.editable ? `<button type="button" class="btn btn-small" data-replace-source="${index}" aria-label="Replace ${escapeAttr(source.filename)}">Replace</button><button type="button" class="btn btn-small" data-remove-source="${index}" aria-label="Remove ${escapeAttr(source.filename)}">Remove</button>` : ''}</div></td></tr>`;
    }).join('')}</tbody></table></div>` : '<p class="authoring-empty">No reference documents attached.</p>';
    const total = this.retainedBytes();
    this.host.insertAdjacentHTML('beforeend', `<div class="authoring-source-capacity"><label for="${prefix}-capacity">${(total / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })} KB of 750 KB of reference text</label><meter id="${prefix}-capacity" min="0" max="750000" value="${Math.min(total, 750000)}">${total} of 750000 bytes</meter></div>` + (this.editable ? `
      <div class="form-field"><label for="${prefix}-upload">Add documents (.txt, .md or .pdf)</label><input id="${prefix}-upload" type="file" accept=".txt,.md,.pdf" multiple></div>
      <input id="${prefix}-replace" type="file" accept=".txt,.md,.pdf" hidden aria-label="Replacement document">
      <button class="btn btn-small" type="button" data-paste-source>Paste document text</button>
      <p class="scenario-hint">${this.sources.length}/20 documents. Upload limit: 1 MB per file and 40 PDF pages. Only extracted text is retained. Original PDFs are not stored. Citation URLs are not fetched.</p>` : '') +
      '<div class="authoring-source-form" hidden></div><div class="source-status workspace-status" role="status" aria-live="polite"></div>');
    for (const button of this.host.querySelectorAll('[data-open-source]')) button.onclick = () => this.open(Number(button.dataset.openSource));
    for (const button of this.host.querySelectorAll('[data-remove-source]')) button.onclick = () => {
      if (!this.canEdit() || !this.finishEditing()) return;
      const index = Number(button.dataset.removeSource); this.metadata.delete(this.sources[index].filename);
      this.sources.splice(index, 1); this.generation++; this.render(); this.changed(); this.message('Document removed from this draft.');
    };
    const replacement = this.host.querySelector('#' + CSS.escape(prefix + '-replace'));
    for (const button of this.host.querySelectorAll('[data-replace-source]')) button.onclick = () => {
      if (!this.canEdit() || !this.finishEditing()) return;
      replacement.dataset.index = button.dataset.replaceSource; replacement.value = ''; replacement.click();
    };
    replacement?.addEventListener('change', event => this.upload([...event.target.files], Number(replacement.dataset.index)));
    this.host.querySelector('#' + CSS.escape(prefix + '-upload'))?.addEventListener('change', event => this.upload([...event.target.files]));
    this.host.querySelector('[data-paste-source]')?.addEventListener('click', () => {
      if (!this.canEdit() || !this.finishEditing()) return;
      if (this.sources.length >= 20) { this.message('Use at most 20 reference documents.'); return; }
      let number = 1;
      while (this.sources.some(source => source.filename === 'reference-' + number + '.txt')) number++;
      this.editDocument({ filename: 'reference-' + number + '.txt', text: '' }, null);
    });
    this.controls();
  }
  canEdit() { return this.editable && !this.busy && state.authSession.authenticated && !scenarioLibrary.busy && !scenarioLibrary.reading && !scenarioMaterials.busy; }
  finishEditing() {
    if (this.editDirty) { this.message('Keep or cancel the current document edit first.'); this.host.querySelector('.authoring-source-form textarea')?.focus(); return false; }
    return true;
  }
  async open(index) {
    if (this.busy || !this.finishEditing()) return;
    const source = this.sources[index], generation = this.generation, account = state.authSession.user?.id;
    if (typeof openSourcesReader !== 'function') { this.message('The document reader is unavailable.'); return; }
    await openSourcesReader({ sources: structuredClone(this.sources), title: 'Draft reference documents', selectedSource: source.filename,
      ...(this.editable && this.canEdit() ? { onEditSource: edited => {
        if (generation !== this.generation || account !== state.authSession.user?.id || !this.canEdit()) return;
        const current = this.sources.findIndex(item => item.filename === edited.filename);
        if (current >= 0) this.editDocument(edited, current);
      } } : {}) });
  }
  editDocument(source, index) {
    this.editing = { index, source: structuredClone(source) }; this.editDirty = index === null;
    const prefix = this.host.id, form = this.host.querySelector('.authoring-source-form'); form.hidden = false;
    form.innerHTML = `<h4>${index === null ? 'Paste document text' : 'Edit extracted text'}</h4>
      <div class="form-field"><label for="${prefix}-edit-name">Citation filename</label><input id="${prefix}-edit-name" data-source-field="filename" maxlength="120" value="${escapeAttr(source.filename)}"></div>
      <div class="form-field"><label for="${prefix}-edit-text">Document text</label><textarea id="${prefix}-edit-text" data-source-field="text" rows="8" maxlength="500000">${escapeHtml(source.text)}</textarea></div>
      <div class="form-field"><label for="${prefix}-edit-url">Source URL <span class="optional-label">optional, citation only</span></label><input id="${prefix}-edit-url" data-source-field="url" type="url" maxlength="2000" placeholder="https://..." value="${escapeAttr(source.url || '')}"></div>
      <div class="authoring-source-actions"><button type="button" class="btn btn-primary" data-keep-source>Keep document</button><button type="button" class="btn" data-cancel-source>Cancel document edit</button></div>`;
    form.oninput = event => { if (!event.target.dataset.sourceField || !this.editing) return;
      this.editing.source[event.target.dataset.sourceField] = event.target.value; this.editDirty = true; this.changed(); };
    form.querySelector('[data-keep-source]').onclick = () => {
      if (!this.canEdit() || !this.editing) return;
      try {
        const next = [...this.sources], { source: edited, index: position } = this.editing;
        if (position === null) next.push(edited); else next[position] = edited;
        const previous = position === null ? null : this.sources[position].filename;
        this.sources = checkedSourceValues(next);
        if (previous && previous !== edited.filename) { const metadata = this.metadata.get(previous); this.metadata.delete(previous); if (metadata) this.metadata.set(edited.filename, metadata); }
        this.generation++; this.editing = null; this.editDirty = false; this.render(); this.changed(); this.message('Document kept in this draft. Save the scenario to keep it in the project.');
      } catch (error) { this.message(error.message); }
    };
    form.querySelector('[data-cancel-source]').onclick = () => { this.editing = null; this.editDirty = false; form.hidden = true; form.replaceChildren(); this.host.querySelector('[data-paste-source]')?.focus(); };
    if (this.editDirty) this.changed();
    form.querySelector('textarea').focus(); this.controls();
  }
  message(text) { this.host.querySelector('.source-status').textContent = text; }
  controls() {
    const disabled = !this.canEdit();
    for (const input of this.host.querySelectorAll('input,textarea,button')) input.disabled = disabled;
    for (const open of this.host.querySelectorAll('[data-open-source]')) open.disabled = this.busy || scenarioLibrary.busy || scenarioLibrary.reading;
  }
  async upload(files, replacing = null) {
    if (!files.length || !this.canEdit() || !this.finishEditing()) return;
    const generation = this.generation, account = state.authSession.user?.id;
    this.busy = true; this.controls(); this.changed();
    const messages = [];
    try {
      if (this.sources.length + files.length - (replacing === null ? 0 : 1) > 20) throw new Error('Use at most 20 reference documents.');
      const next = [...this.sources], metadata = [];
      for (const [index, file] of files.entries()) {
        if (file.size > 1000000) throw new Error('Each reference document must be at most 1 MB.');
        this.message('Checking ' + (index + 1) + ' of ' + files.length + ': ' + file.name + ' (' + (file.size / 1000).toFixed(1) + ' KB upload)...');
        const result = await previewSourceUpload(file);
        if (generation !== this.generation || state.authSession.user?.id !== account) return;
        if (replacing === null) next.push(result.source); else next[replacing] = result.source;
        metadata.push([result.source.filename, { warnings: result.warnings || [], upload_bytes: file.size,
          ...(Number.isInteger(result.page_count) && result.page_count > 0 ? { page_count: result.page_count } : {}) }]);
        messages.push(...(result.warnings || []));
      }
      const validated = checkedSourceValues(next);
      if (replacing !== null) this.metadata.delete(this.sources[replacing].filename);
      this.sources = validated;
      for (const [name, receipt] of metadata) this.metadata.set(name, receipt);
      messages.push('Documents loaded into this draft. Open each document to review the retained text before saving.');
    } catch (error) { messages.push(error.message + ' Existing documents are unchanged.'); }
    finally {
      if (generation === this.generation && state.authSession.user?.id === account) {
        this.busy = false; this.render(); this.message(messages.join('\n')); this.changed();
      }
    }
  }
}

async function readMaterialText(file, limit) {
  if (!file) return null;
  if (file.size > limit) throw new Error(`Choose a UTF-8 text file smaller than ${limit / 1000} KB.`);
  try { return new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); }
  catch (_) { throw new Error('Save the file as UTF-8 text before loading.'); }
}

function initScenarioMaterials() {
  const host = byId('scenario-source-editor');
  const element = document.createElement('div'); element.id = 'library-sources-new'; host.append(element);
  librarySources.new = new SourceEditor(element, scenarioDraftChanged);
  librarySources.new.reset();
  projectSources = new SourceEditor(byId('materials-source-editor'), () => { scenarioMaterials.dirty = true; renderMaterialAccess(); });
  byId('materials-save').addEventListener('click', saveScenarioMaterials);
  byId('materials-glossary').addEventListener('input', () => { scenarioMaterials.dirty = true; });
  byId('materials-glossary-file').addEventListener('change', async event => {
    const generation = scenarioMaterials.generation;
    scenarioMaterials.loading = true; renderMaterialAccess();
    try {
      const text = await readMaterialText(event.target.files[0], 200000);
      if (text !== null && generation === scenarioMaterials.generation) { byId('materials-glossary').value = text; scenarioMaterials.dirty = true; }
    } catch (error) { if (generation === scenarioMaterials.generation) setWorkspaceStatus('materials-status', error.message, 'error'); }
    finally { if (generation === scenarioMaterials.generation) { scenarioMaterials.loading = false; renderMaterialAccess(); } }
  });
}

function renderMaterialAccess() {
  const account = state.authSession.authenticated ? state.authSession.user?.id : null;
  if (scenarioMaterials.account !== account) {
    scenarioMaterials.account = account;
    clearScenarioMaterials();
  }
  for (const editor of Object.values(librarySources)) editor.controls();
  if (!projectSources) return;
  projectSources.controls();
  const editable = !!scenarioMaterials.draft?.project;
  byId('materials-save').hidden = !editable;
  byId('materials-save').disabled = scenarioMaterials.busy || scenarioMaterials.loading || projectSources.busy;
  byId('materials-glossary').readOnly = !editable || scenarioMaterials.busy || scenarioMaterials.loading;
  byId('materials-glossary-file').disabled = scenarioMaterials.busy || scenarioMaterials.loading;
  byId('materials-glossary-upload').hidden = !editable;
}

function clearScenarioMaterials() {
  scenarioLibrary.busy = false; scenarioLibrary.reading = false;
  scenarioMaterials.generation++; scenarioMaterials.draft = null; scenarioMaterials.dirty = false;
  scenarioMaterials.loading = false;
  closeModal('modal-scenario-materials');
  byId('materials-glossary').value = ''; byId('materials-glossary-file').value = '';
  byId('materials-scenario-title').textContent = ''; byId('materials-bundled').textContent = '';
  byId('materials-access-note').textContent = ''; setWorkspaceStatus('materials-status');
  projectSources?.reset();
  for (const editor of Object.values(librarySources)) editor.reset();
  resetScenarioBuilder(); scenarioLibrary.dirty = false;
}

function closeScenarioMaterials() {
  if (scenarioMaterials.busy) return;
  if ((scenarioMaterials.dirty || projectSources.busy) && !window.confirm('Discard unsaved glossary and reference changes?')) return;
  scenarioMaterials.generation++; scenarioMaterials.draft = null; scenarioMaterials.dirty = false;
  scenarioMaterials.loading = false;
  projectSources.reset(); byId('materials-glossary').value = ''; byId('materials-glossary-file').value = '';
  closeModal('modal-scenario-materials');
}

function glossaryText(scenario) {
  const entries = [];
  for (const section of ['facts', 'assumptions', 'propositions', 'conclusions', 'rules']) {
    for (const [id, item] of Object.entries(scenario[section] || {})) {
      if (section !== 'rules') entries.push(`${id} = ${JSON.stringify(item.description || id)}`);
      if (item.negated_description) entries.push(`-${id} = ${JSON.stringify(item.negated_description)}`);
    }
  }
  return entries.join('\n');
}

async function openScenarioMaterials() {
  if (state.activeProject) { await openPrivateScenarioEditor(); return; }
  if (!state.bundle || hasPendingStateRequest() || state.projectSavePending) { showGlobalStatus('Wait for the current change to finish.', 'info'); return; }
  if (state.activeProject && state.diff_ops.length) {
    const projectId = state.activeProject.id;
    if (!window.confirm('Save current rule changes before editing sources and glossary?')) return;
    if (!await saveProjectChanges() || state.activeProject?.id !== projectId) return;
  }
  scenarioMaterials.generation++; scenarioMaterials.dirty = false;
  scenarioMaterials.draft = { scenario: structuredClone(state.bundle.scenario), project: state.activeProject,
    bundle: state.bundle, account: state.authSession.user?.id };
  const { scenario, project } = scenarioMaterials.draft;
  byId('materials-scenario-title').textContent = project?.name || scenario.title;
  byId('materials-access-note').textContent = project
    ? 'Edits are saved to this private project. Existing shared links will include the updated materials. Published examples keep their separate snapshot.'
    : 'Read-only materials for this scenario. To change them, first save a private copy from Manage projects.';
  byId('materials-glossary').value = glossaryText(scenario);
  byId('materials-bundled').textContent = scenario.corpus?.length
    ? `Bundled references: ${scenario.corpus.join(', ')}. These stay linked to the original example. Additional documents appear below.`
    : 'References provide AI context without adding facts or rules. Review PDF extraction and paste corrections when needed.';
  projectSources.reset(scenario.sources || [], !!project);
  setWorkspaceStatus('materials-status'); renderMaterialAccess();
  openModal('modal-scenario-materials', '#materials-glossary');
}

async function saveScenarioMaterials() {
  const draft = scenarioMaterials.draft;
  if (!draft?.project || scenarioMaterials.busy || scenarioMaterials.loading || projectSources.busy) return;
  if (state.activeProject !== draft.project || state.bundle !== draft.bundle || hasPendingStateRequest()
      || state.projectSavePending || state.authSession.user?.id !== draft.account) {
    setWorkspaceStatus('materials-status', 'The current view changed. Close and reopen Edit scenario before saving.', 'error'); return;
  }
  const generation = scenarioMaterials.generation;
  let scenario;
  try { scenario = { ...draft.scenario, sources: projectSources.value() }; }
  catch (error) { setWorkspaceStatus('materials-status', error.message, 'error'); return; }
  scenarioMaterials.busy = true; state.projectSavePending = true; renderMaterialAccess();
  setWorkspaceStatus('materials-status', 'Checking glossary and saving materials...', 'info');
  try {
    const preview = await apiRequest('/api/projects/materials/glossary-preview', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario, glossary: byId('materials-glossary').value }) });
    if (generation !== scenarioMaterials.generation || state.authSession.user?.id !== draft.account) return;
    const project = await apiRequest(`/api/projects/${encodeURIComponent(draft.project.id)}`, { method: 'PUT',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_version: draft.project.version, scenario: preview.scenario }) });
    if (generation !== scenarioMaterials.generation || state.authSession.user?.id !== draft.account) return;
    scenarioMaterials.dirty = false;
    if (state.activeProject === draft.project && state.bundle === draft.bundle) {
      state.activeProject = project; state.baseline = project.scenario; state.diff_ops = [];
      setBundle({ scenario: project.scenario, af: project.af }); resetChatConversation(); indexBundle(); populateScenarioSelect(); renderAll();
    }
    scenarioMaterials.busy = false; closeScenarioMaterials();
    showGlobalStatus(`Saved sources and glossary to "${project.name}".`, 'success');
    await refreshProjects({ quiet: true });
  } catch (error) {
    if (generation === scenarioMaterials.generation) setWorkspaceStatus('materials-status', error.code === 'project_version_conflict'
      ? 'This project changed elsewhere. Reopen it before saving; your draft has not replaced newer work.' : error.message, 'error');
  } finally { scenarioMaterials.busy = false; state.projectSavePending = false; renderMaterialAccess(); }
}

async function previewSourceUpload(file) {
  if (file.size > 1000000) throw new Error('Each reference document must be at most 1 MB.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return apiRequest('/api/projects/materials/source-preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name, data_base64: btoa(binary) }),
  });
}
