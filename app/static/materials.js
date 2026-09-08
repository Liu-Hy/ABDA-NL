/* Scenario materials are data, never fetched URLs or executable instructions. */
const scenarioMaterials = { draft: null, generation: 0, busy: false, loading: false, dirty: false, account: null };
const librarySources = {};
let projectSources;
let aspicPreview = null;
let aspicGeneration = 0;

class SourceEditor {
  constructor(host, changed) {
    this.host = host; this.changed = changed; this.sources = [];
    this.generation = 0; this.busy = false; this.editable = true;
  }
  reset(sources = [], editable = true) {
    this.generation++; this.busy = false; this.editable = editable;
    this.sources = structuredClone(sources); this.render();
  }
  value() {
    if (this.busy) throw new Error('Wait for document extraction to finish.');
    let total = 0;
    const names = new Set();
    return this.sources.map(source => {
      const filename = source.filename.trim(), text = source.text.trim(), url = (source.url || '').trim();
      if (!/^[A-Za-z0-9][A-Za-z0-9_. -]*\.(txt|md|pdf)$/.test(filename) || filename.length > 120) throw new Error('Give each source a simple, distinct .txt, .md or .pdf filename.');
      if (names.has(filename.toLowerCase())) throw new Error('Each reference needs a distinct filename.');
      names.add(filename.toLowerCase());
      if (!text || text.length > 100000) throw new Error('Each reference needs text, up to 100,000 characters.');
      total += new TextEncoder().encode(text).length;
      if (total > 400000) throw new Error('Reference text exceeds 400 KB in total. Use relevant excerpts or summaries.');
      if (url) {
        let parsed;
        try { parsed = new URL(url); } catch (_) { throw new Error('Source links must be complete HTTPS URLs.'); }
        if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error('Use HTTPS source links without embedded credentials.');
      }
      return { filename, text, ...(url ? { url } : {}) };
    });
  }
  render() {
    const prefix = this.host.id;
    this.host.innerHTML = this.sources.map((source, i) => `
      <details class="source-card" ${this.editable ? 'open' : ''}>
        <summary>${escapeHtml(source.filename || 'Untitled document')}</summary>
        ${this.editable ? `<div class="form-field"><label for="${prefix}-name-${i}">Citation filename</label><input id="${prefix}-name-${i}" data-source-index="${i}" data-source-field="filename" maxlength="120" value="${escapeAttr(source.filename)}"></div>
          <div class="form-field"><label for="${prefix}-text-${i}">Document text</label><textarea id="${prefix}-text-${i}" data-source-index="${i}" data-source-field="text" rows="5" maxlength="100000">${escapeHtml(source.text)}</textarea></div>
          <div class="form-field"><label for="${prefix}-url-${i}">Source URL <span class="optional-label">optional, citation only</span></label><input id="${prefix}-url-${i}" data-source-index="${i}" data-source-field="url" type="url" maxlength="2000" placeholder="https://..." value="${escapeAttr(source.url || '')}"></div>
          <button class="btn btn-small" type="button" data-remove-source="${i}">Remove document</button>`
        : `<p class="scenario-hint">${escapeHtml(source.url || '')}</p><pre tabindex="0">${escapeHtml(source.text)}</pre>`}
      </details>`).join('') + (this.editable ? `
      <div class="form-field"><label for="${prefix}-upload">Add documents (.txt, .md or .pdf)</label><input id="${prefix}-upload" type="file" accept=".txt,.md,.pdf" multiple></div>
      <button class="btn btn-small" type="button" data-paste-source>+ Paste document text</button>
      <p class="scenario-hint">${this.sources.length}/10 documents. Up to 1 MB per file, 40 PDF pages, and 400 KB of extracted text in total. URLs are not fetched. Original PDFs are not stored.</p>`
      : this.sources.length ? '' : '<p class="scenario-hint">No uploaded reference documents.</p>') +
      '<div class="source-status workspace-status" role="status" aria-live="polite"></div>';
    this.host.oninput = event => {
      const field = event.target.dataset.sourceField;
      if (!field) return;
      this.sources[Number(event.target.dataset.sourceIndex)][field] = event.target.value;
      this.changed();
    };
    this.host.onclick = event => {
      if (this.busy || !this.editable) return;
      const remove = event.target.closest('[data-remove-source]');
      if (remove) { this.sources.splice(Number(remove.dataset.removeSource), 1); this.render(); this.changed(); }
      if (event.target.closest('[data-paste-source]')) {
        if (this.sources.length >= 10) { this.message('Use at most 10 reference documents.'); return; }
        let number = 1;
        while (this.sources.some(s => s.filename === `reference-${number}.txt`)) number++;
        this.sources.push({ filename: `reference-${number}.txt`, text: '' });
        this.render(); this.changed();
        this.host.querySelectorAll('textarea')[this.sources.length - 1]?.focus();
      }
    };
    this.host.querySelector('input[type=file]')?.addEventListener('change', event => this.upload([...event.target.files]));
    this.controls();
  }
  message(text) { this.host.querySelector('.source-status').textContent = text; }
  controls() {
    const disabled = !this.editable || this.busy || !state.authSession.authenticated
      || scenarioLibrary.busy || scenarioMaterials.busy;
    for (const input of this.host.querySelectorAll('input,textarea,button')) input.disabled = disabled;
  }
  async upload(files) {
    if (this.busy || !this.editable || !state.authSession.authenticated) return;
    const generation = this.generation, account = state.authSession.user?.id;
    this.busy = true; this.controls(); this.changed();
    const messages = [];
    try {
      if (this.sources.length + files.length > 10) throw new Error('Use at most 10 reference documents.');
      for (const file of files) {
        if (file.size > 1000000) throw new Error('Each reference document must be at most 1 MB.');
        this.message(`Checking ${file.name}...`);
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (generation !== this.generation || state.authSession.user?.id !== account) return;
        let binary = '';
        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        const result = await apiRequest('/api/projects/materials/source-preview', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name, data_base64: btoa(binary) }),
        });
        if (generation !== this.generation || state.authSession.user?.id !== account) return;
        this.sources.push(result.source);
        messages.push(...result.warnings);
      }
      messages.push('Review the text below before saving. Nothing has been saved yet.');
    } catch (error) { messages.push(error.message); }
    finally {
      if (generation === this.generation) {
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

function invalidateAspic() {
  aspicPreview = null; aspicGeneration++;
  byId('aspic-import-result').textContent = '';
  scenarioLibrary.dirty = true;
  // The footer is updated by the next access render or after validation.
  if (scenarioLibrary.tab === 'aspic') byId('scenario-library-submit').textContent = 'Check & preview';
}

function initScenarioMaterials() {
  const host = byId('scenario-source-editor');
  for (const tab of ['new', 'file', 'aspic']) {
    const element = document.createElement('div'); element.id = `library-sources-${tab}`;
    element.hidden = tab !== scenarioLibrary.tab; host.append(element);
    librarySources[tab] = new SourceEditor(element, () => { scenarioLibrary.dirty = true; renderScenarioLibraryAccess(); });
    librarySources[tab].reset();
  }
  projectSources = new SourceEditor(byId('materials-source-editor'), () => { scenarioMaterials.dirty = true; renderMaterialAccess(); });
  byId('scenario-materials-btn').addEventListener('click', openScenarioMaterials);
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
  byId('scenario-aspic-fields').addEventListener('input', invalidateAspic);
  for (const [fileId, target, limit] of [['aspic-rules-file', 'aspic-import-rules', 100000], ['aspic-glossary-file', 'aspic-import-glossary', 200000]]) {
    byId(fileId).addEventListener('change', async event => {
      invalidateAspic(); const generation = aspicGeneration;
      scenarioLibrary.reading = true; renderScenarioLibraryAccess();
      try {
        const text = await readMaterialText(event.target.files[0], limit);
        if (text !== null && generation === aspicGeneration) byId(target).value = text;
      } catch (error) { if (generation === aspicGeneration) setWorkspaceStatus('scenario-library-status', error.message, 'error'); }
      finally { if (generation === aspicGeneration) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); } }
    });
  }
  byId('aspic-import-preview').addEventListener('click', () => previewAspic());
  byId('aspic-starter').addEventListener('click', () => {
    if (byId('aspic-import-rules').value && !window.confirm('Replace the ASPIC- draft with the small example?')) return;
    byId('aspic-import-title').value = 'Planning a picnic';
    byId('aspic-import-rules').value = '-> sunny\n-> windy\nsunny => outside [sunshine]\nwindy => -outside [wind]';
    byId('aspic-import-glossary').value = 'sunny = The forecast is sunny\nwindy = A strong wind is expected\noutside = We should hold the picnic outside\n-outside = We should not hold the picnic outside';
    byId('aspic-import-conclusions').value = 'outside'; invalidateAspic();
  });
}

async function previewAspic() {
  if (!state.authSession.authenticated || scenarioLibrary.reading) return null;
  const generation = ++aspicGeneration, account = state.authSession.user?.id;
  scenarioLibrary.reading = true; renderScenarioLibraryAccess();
  try {
    const result = await apiRequest('/api/projects/import/aspic', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: byId('aspic-import-title').value, rules: byId('aspic-import-rules').value,
        glossary: byId('aspic-import-glossary').value, conclusions: byId('aspic-import-conclusions').value }),
    });
    if (generation !== aspicGeneration || account !== state.authSession.user?.id) return null;
    aspicPreview = result;
    const scenario = result.scenario;
    byId('aspic-import-result').textContent = `Validated: ${Object.keys(scenario.rules).length} rules. Key conclusions: ${Object.keys(scenario.conclusions).join(', ') || 'none'}.\n${result.warnings.join('\n')}`;
    setWorkspaceStatus('scenario-library-status', 'Rules and glossary validated. Add reference documents below if needed, then import.', 'success');
    return result;
  } catch (error) {
    if (generation === aspicGeneration) { aspicPreview = null; setWorkspaceStatus('scenario-library-status', error.message, 'error'); }
    return null;
  } finally {
    if (generation === aspicGeneration) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); }
  }
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
  scenarioMaterials.generation++; scenarioMaterials.draft = null; scenarioMaterials.dirty = false;
  scenarioMaterials.loading = false;
  closeModal('modal-scenario-materials');
  byId('materials-glossary').value = ''; byId('materials-glossary-file').value = '';
  byId('materials-scenario-title').textContent = ''; byId('materials-bundled').textContent = '';
  byId('materials-access-note').textContent = ''; setWorkspaceStatus('materials-status');
  projectSources?.reset();
  for (const editor of Object.values(librarySources)) editor.reset();
  for (const input of byId('scenario-aspic-fields').querySelectorAll('input,textarea')) input.value = '';
  invalidateAspic(); scenarioLibrary.dirty = false;
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
    : 'Read-only materials for this scenario. To change them, first save a private copy from Workspace > Projects.';
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
    setWorkspaceStatus('materials-status', 'The current view changed. Close and reopen Sources & glossary before saving.', 'error'); return;
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
