/* One private scenario draft, with guided and textual views of the same rules. */
const scenarioLibrary = {
  tab: 'new', mode: 'guided', statements: [], rules: [], nextId: 1,
  base: {}, sourceId: null, target: null, targetBundle: null, preview: null, generation: 0,
  busy: false, reading: false, dirty: false, rawChanged: false, files: [],
  entryScenario: null, previewShown: false, importWarnings: [], problems: [],
};
const SCENARIO_FILE_LIMIT = 1000000;
const STATEMENT_SECTIONS = { fact: 'facts', assumption: 'assumptions', proposition: 'propositions', conclusion: 'conclusions' };
const pendingReadableIds = new WeakSet();
const expandedBuilderRows = new Set();
let builderControlNumber = 0;

function renameScenarioSymbol(scenario, from, to) {
  if (typeof to !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(to) || /\s/.test(to))
    throw new Error('Use 1 to 100 letters, digits or underscores, starting with a letter or underscore. Do not include a minus sign.');
  if (Object.hasOwn(Object.prototype, to) || to === 'prototype')
    throw new Error('This symbol is reserved. Choose a different name.');
  const sections = [...Object.values(STATEMENT_SECTIONS), 'rules'];
  const owners = sections.filter(section => Object.hasOwn(scenario[section] || {}, from));
  if (owners.length !== 1) throw new Error('Choose one existing statement or rule to rename.');
  if (to !== from && sections.some(section => Object.hasOwn(scenario[section] || {}, to)))
    throw new Error('That symbol is already used by a statement or rule. Choose a distinct name.');
  const result = structuredClone(scenario);
  result[owners[0]] = Object.fromEntries(Object.entries(result[owners[0]]).map(([id, value]) => [id === from ? to : id, value]));
  const literal = value => value === from ? to : value === '-' + from ? '-' + to : value;
  for (const rule of Object.values(result.rules || {})) {
    rule.premises = rule.premises.map(literal);
    rule.conclusion = literal(rule.conclusion);
  }
  return result;
}

function pendingSymbolRename() {
  const select = byId('scenario-rename-from'), input = byId('scenario-rename-to');
  return !!select?.value && input.value !== select.value;
}

function renderSymbolChoices(preferred = null) {
  const select = byId('scenario-rename-from'), input = byId('scenario-rename-to');
  const previous = select.value, candidate = input.value;
  select.replaceChildren();
  for (const item of [...scenarioLibrary.statements, ...scenarioLibrary.rules]) {
    const kind = item.kind === 'conclusion' ? 'key conclusion' : item.kind || 'rule';
    select.add(new Option(item.id + ' (' + kind + ')' + (item.description ? ': ' + item.description.slice(0, 70) : ''), item.id));
  }
  const desired = preferred || previous;
  if ([...select.options].some(option => option.value === desired)) select.value = desired;
  input.value = !preferred && previous === select.value ? candidate : select.value;
}

function openSymbolRename(id) {
  if (!state.authSession.authenticated || scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy) return;
  if (pendingSymbolRename() && byId('scenario-rename-from').value !== id) {
    setWorkspaceStatus('scenario-library-status', 'Rename or cancel the current symbol change first.', 'info');
  } else { renderSymbolChoices(id); }
  byId('scenario-symbol-renamer').open = true;
  renderScenarioLibraryAccess();
  byId('scenario-rename-to').focus(); byId('scenario-rename-to').select();
}

function symbolRenameShortcut(item) {
  const getId = () => typeof item === 'string' ? item : item.id;
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'btn btn-small scenario-rename-shortcut'; button.textContent = 'Rename';
  button.setAttribute('aria-label', 'Rename symbol ' + getId());
  button.addEventListener('click', () => openSymbolRename(getId()));
  return button;
}

function cancelSymbolRename() {
  byId('scenario-rename-to').value = byId('scenario-rename-from').value;
  byId('scenario-rename-to').removeAttribute('aria-invalid');
  setWorkspaceStatus('scenario-library-status'); renderScenarioLibraryAccess();
}

function commitSymbolRename() {
  if (!state.authSession.authenticated || scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy) return;
  if (scenarioLibrary.rawChanged || byId('scenario-glossary-text').value.trim()) {
    setWorkspaceStatus('scenario-library-status', 'Cancel this rename, then Preview rule text or Apply meanings before renaming.', 'info'); return;
  }
  const from = byId('scenario-rename-from').value, to = byId('scenario-rename-to').value;
  if (from === to) return;
  try {
    // Work on a copy, so rejected names never partly update the draft. Sources
    // and pending document fields remain untouched in their existing editor.
    const pendingIds = new Set([...scenarioLibrary.statements, ...scenarioLibrary.rules].filter(item => pendingReadableIds.has(item) && item.id !== from).map(item => item.id));
    const renamed = renameScenarioSymbol(scenarioFromBuilder(false), from, to);
    scenarioLibrary.base = renamed;
    scenarioLibrary.statements = Object.entries(STATEMENT_SECTIONS).flatMap(([kind, section]) =>
      Object.entries(renamed[section]).map(([id, data]) => ({ id, kind, ...data })));
    scenarioLibrary.rules = Object.entries(renamed.rules).map(([id, data]) => ({ id, ...data }));
    for (const item of [...scenarioLibrary.statements, ...scenarioLibrary.rules]) if (pendingIds.has(item.id)) pendingReadableIds.add(item);
    clearScenarioProblems();
    scenarioLibrary.generation++;
    byId('scenario-rule-text').value = scenarioRuleText(renamed);
    renderBuilderStatements(); renderBuilderRules(); renderSymbolChoices(to);
    byId('scenario-rename-to').removeAttribute('aria-invalid');
    scenarioDraftChanged();
    setWorkspaceStatus('scenario-library-status', 'Renamed ' + from + ' to ' + to + '. Logical references and meanings were preserved. Use Check & save when ready.', 'success');
    byId('scenario-rename-to').focus();
  } catch (error) {
    byId('scenario-rename-to').setAttribute('aria-invalid', 'true');
    setWorkspaceStatus('scenario-library-status', error.message, 'error');
    byId('scenario-rename-to').focus();
  }
}

function scenarioDraftChanged() {
  scenarioLibrary.generation++;
  scenarioLibrary.dirty = true;
  scenarioLibrary.preview = null;
  scenarioLibrary.previewShown = false;
  byId('scenario-editor-preview').hidden = true;
  renderScenarioLibraryAccess();
}

function initScenarioLibrary() {
  initCurationUI();
  initScenarioMaterials();
  byId('scenario-library-btn')?.addEventListener('click', () => openScenarioLibrary('new'));
  byId('scenario-library-cancel').addEventListener('click', () => requestCloseModal('modal-scenario-library'));
  byId('scenario-my-projects').addEventListener('click', () => {
    requestCloseModal('modal-scenario-library'); openWorkspace('projects');
  });
  byId('scenario-signin-btn').addEventListener('click', () => {
    requestCloseModal('modal-scenario-library'); openWorkspace('account');
  });
  for (const tab of document.querySelectorAll('[data-scenario-tab]')) {
    tab.addEventListener('click', () => switchScenarioLibraryTab(tab.dataset.scenarioTab));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 'new' : event.key === 'End' ? 'file'
        : scenarioLibrary.tab === 'new' ? 'file' : 'new';
      switchScenarioLibraryTab(next); byId('scenario-tab-' + next).focus();
    });
  }
  byId('scenario-add-statement').addEventListener('click', () => addBuilderStatement());
  byId('scenario-add-rule').addEventListener('click', () => addBuilderRule());
  byId('scenario-starter-btn').addEventListener('click', useScenarioStarter);
  byId('scenario-reset-btn').addEventListener('click', () => {
    if (scenarioLibrary.dirty && !window.confirm('Discard this draft and start a new scenario?')) return;
    resetScenarioBuilder(); renderScenarioLibraryAccess();
  });
  byId('scenario-builder-form').addEventListener('submit', event => { event.preventDefault(); previewScenarioDraft(); });
  byId('scenario-builder-form').addEventListener('input', event => {
    if (!event.target.closest('#scenario-symbol-renamer') && !event.target.matches('[data-authoring-filter]')) {
      clearEditorProblem(event.target.dataset.editorField);
      scenarioDraftChanged();
    }
  });
  byId('scenario-builder-filter').addEventListener('input', filterBuilderRows);
  byId('scenario-discard-changes').addEventListener('click', discardEditorChanges);
  byId('scenario-rename-from').addEventListener('change', cancelSymbolRename);
  byId('scenario-rename-to').addEventListener('input', () => {
    byId('scenario-rename-to').removeAttribute('aria-invalid');
    if (pendingSymbolRename()) scenarioLibrary.dirty = true;
    renderScenarioLibraryAccess();
  });
  byId('scenario-rename-to').addEventListener('keydown', event => {
    if (!['Enter', 'Escape'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    if (event.key === 'Enter') commitSymbolRename(); else cancelSymbolRename();
  });
  byId('scenario-rename-apply').addEventListener('click', commitSymbolRename);
  byId('scenario-rename-cancel').addEventListener('click', cancelSymbolRename);
  byId('scenario-preview-btn').addEventListener('click', () => previewScenarioDraft());
  byId('scenario-library-submit').addEventListener('click', submitScenarioLibrary);
  byId('scenario-mode-guided').addEventListener('click', () => switchScenarioMode('guided'));
  byId('scenario-mode-text').addEventListener('click', () => switchScenarioMode('text'));
  byId('scenario-rule-text').addEventListener('input', () => { scenarioLibrary.rawChanged = true; });
  byId('scenario-file-input').addEventListener('change', event => queueScenarioFiles([...event.target.files]));
  byId('scenario-load-files').addEventListener('click', () => loadScenarioFiles());
  byId('scenario-open-file-project').addEventListener('click', () => loadScenarioFiles(true));
  const dropZone = byId('scenario-drop-zone');
  dropZone.addEventListener('dragover', event => { event.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', event => {
    event.preventDefault(); dropZone.classList.remove('drag-over');
    queueScenarioFiles([...event.dataTransfer.files]);
  });
  byId('scenario-glossary-file').addEventListener('change', async event => {
    if (scenarioLibrary.busy || scenarioLibrary.reading) return;
    const generation = scenarioLibrary.generation, account = state.authSession.user?.id;
    let completionGeneration = generation;
    scenarioLibrary.reading = true; renderScenarioLibraryAccess();
    try {
      const text = await readMaterialText(event.target.files[0], 200000);
      if (text !== null && generation === scenarioLibrary.generation && account === state.authSession.user?.id) {
        byId('scenario-glossary-text').value = text; scenarioDraftChanged(); completionGeneration = scenarioLibrary.generation;
      }
    } catch (error) { if (generation === scenarioLibrary.generation) setWorkspaceStatus('scenario-library-status', error.message, 'error'); }
    finally { if (completionGeneration === scenarioLibrary.generation && account === state.authSession.user?.id) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); } }
  });
  byId('scenario-apply-glossary').addEventListener('click', () => previewScenarioDraft(false));
  resetScenarioBuilder();
  window.addEventListener('beforeunload', event => {
    if (!scenarioLibrary.dirty || !state.authSession.authenticated) return;
    event.preventDefault(); event.returnValue = '';
  });
}

function openScenarioLibrary(tab = null) {
  if (['new', 'file'].includes(tab)) {
    if (scenarioLibrary.target) {
      if (scenarioLibrary.dirty && !window.confirm('Discard this editor draft and start a new scenario?')) return;
      resetScenarioBuilder();
    }
    switchScenarioLibraryTab(tab);
  }
  renderScenarioLibraryAccess();
  openModal('modal-scenario-library', state.authSession.authenticated
    ? scenarioLibrary.tab === 'file' && !scenarioLibrary.target ? '#scenario-file-input' : '#scenario-builder-title'
    : '#scenario-signin-btn');
}

function renderScenarioLibraryAccess() {
  const disabled = !state.authSession.authenticated || scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new?.busy;
  const pendingRename = pendingSymbolRename();
  const uncheckedText = scenarioLibrary.rawChanged || !!byId('scenario-glossary-text').value.trim();
  byId('scenario-signin-required').hidden = state.authSession.authenticated;
  byId('scenario-builder-fields').disabled = disabled;
  for (const id of ['scenario-file-input', 'scenario-load-files', 'scenario-preview-btn', 'scenario-starter-btn', 'scenario-reset-btn']) byId(id).disabled = disabled;
  for (const input of byId('scenario-import-files').querySelectorAll('select,button,input')) input.disabled = disabled;
  byId('scenario-mode-guided').disabled = disabled || pendingRename || !guidedEditorAvailable();
  byId('scenario-mode-text').disabled = disabled || pendingRename;
  byId('scenario-preview-btn').disabled = disabled || pendingRename;
  const staleProject = scenarioLibrary.target && (state.readOnly || state.activeProject !== scenarioLibrary.target
    || state.bundle !== scenarioLibrary.targetBundle);
  const waiting = hasPendingStateRequest() || state.projectSavePending;
  byId('scenario-library-submit').disabled = disabled || pendingRename || waiting || Boolean(staleProject);
  byId('scenario-rename-from').disabled = disabled || uncheckedText;
  byId('scenario-rename-to').disabled = disabled || uncheckedText || !byId('scenario-rename-from').value;
  byId('scenario-rename-apply').disabled = disabled || uncheckedText || !pendingRename;
  byId('scenario-rename-cancel').disabled = disabled || !pendingRename;
  byId('scenario-rename-note').textContent = uncheckedText
    ? 'Preview changed rule text or Apply meanings from the pasted glossary before renaming.'
    : 'Renaming updates every logical reference, including negation and rule undercuts. Meanings and reference documents are preserved.';
  for (const id of ['scenario-rule-text', 'scenario-glossary-text', 'scenario-glossary-file', 'scenario-apply-glossary'])
    byId(id).disabled = disabled || pendingRename;
  byId('scenario-library-submit').textContent = scenarioLibrary.busy ? 'Saving...' : scenarioLibrary.reading ? 'Checking...'
    : !scenarioLibrary.preview ? 'Check & save' : scenarioLibrary.target ? 'Save changes' : 'Save & open';
  byId('scenario-preview-btn').textContent = scenarioLibrary.reading ? 'Checking...' : 'Preview';
  byId('scenario-editor-heading').textContent = scenarioLibrary.target ? 'Edit: ' + scenarioLibrary.target.name
    : scenarioLibrary.tab === 'file' ? 'Import scenario' : 'New scenario';
  byId('scenario-editor-outcome').textContent = scenarioLibrary.target
    ? 'Updates this project (version ' + scenarioLibrary.target.version + ')' : 'Saves as a private project';
  byId('scenario-editor-navigation').hidden = Boolean(scenarioLibrary.target);
  byId('scenario-start-actions').hidden = Boolean(scenarioLibrary.target);
  byId('scenario-panel-file').hidden = Boolean(scenarioLibrary.target) || scenarioLibrary.tab !== 'file';
  byId('scenario-discard-changes').hidden = !scenarioLibrary.target;
  byId('scenario-discard-changes').disabled = disabled || !scenarioLibrary.dirty;
  byId('scenario-open-file-project').disabled = disabled;
  byId('scenario-save-note').textContent = !state.authSession.authenticated ? 'Sign in to save a private project. No AI credit or key is needed.'
    : staleProject ? 'The open project changed. Reopen its editor before saving; this draft is preserved.'
    : pendingRename ? 'Rename or cancel the pending symbol change before saving.'
    : waiting || disabled ? 'Wait for the current check or save to finish.'
    : scenarioLibrary.preview?.warnings?.length ? 'Review the warnings above, then choose Save to continue.'
    : 'Checks the scenario before saving. No AI call is needed.';
  byId('scenario-sources-summary').textContent = (librarySources.new?.sources.length || 0) + ' attached documents';
  renderMaterialAccess();
}

function switchScenarioLibraryTab(tab) {
  if (scenarioLibrary.busy || scenarioLibrary.reading) return;
  scenarioLibrary.tab = tab;
  for (const name of ['new', 'file']) {
    const active = name === tab, button = byId('scenario-tab-' + name);
    button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1; byId('scenario-panel-' + name).hidden = !active;
  }
  // Entry points never discard or fork the common draft.
  renderScenarioLibraryAccess();
}

function setScenarioMode(mode) {
  if (mode === 'guided' && !guidedEditorAvailable()) mode = 'text';
  scenarioLibrary.mode = mode;
  byId('scenario-guided').hidden = mode !== 'guided';
  byId('scenario-rule-text-panel').hidden = mode !== 'text';
  for (const name of ['guided', 'text']) byId('scenario-mode-' + name).setAttribute('aria-pressed', String(name === mode));
  byId('scenario-guided-limit').hidden = guidedEditorAvailable();
  byId('scenario-guided-limit').textContent = 'This scenario exceeds the Guided limit (100 statements, 100 rules or 200 conditions). Rule text, glossary, reference documents, Preview and saving remain available. No content was removed.';
}

async function switchScenarioMode(mode) {
  if (scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || mode === scenarioLibrary.mode) return;
  if (mode === 'guided' && scenarioLibrary.rawChanged && !await previewScenarioDraft(false)) return;
  if (mode === 'text') {
    commitPendingReadableIds();
    const empty = scenarioLibrary.statements.every(item => !item.description.trim())
      && scenarioLibrary.rules.every(rule => !rule.conclusion && rule.premises.every(p => !p));
    if (empty) {
      const scenario = { ...scenarioLibrary.base, title: byId('scenario-builder-title').value,
        description: byId('scenario-builder-description').value, sources: structuredClone(librarySources.new.sources),
        facts: {}, assumptions: {}, propositions: {}, conclusions: {}, rules: {} };
      loadScenarioDraft(scenario, scenarioLibrary.sourceId, scenarioLibrary.target, true);
      byId('scenario-rule-text').value = '';
    } else {
      try {
        const candidate = scenarioFromBuilder(true);
        byId('scenario-rule-text').value = scenarioRuleText(candidate);
      } catch (error) { setWorkspaceStatus('scenario-library-status', error.message, 'error'); return; }
    }
  }
  setScenarioMode(mode);
  byId(mode === 'text' ? 'scenario-rule-text' : 'scenario-add-statement').focus();
}

function guidedEditorAvailable() {
  return scenarioLibrary.statements.length <= 100 && scenarioLibrary.rules.length <= 100
    && scenarioLibrary.rules.reduce((count, rule) => count + rule.premises.length, 0) <= 200;
}

function clearScenarioPreview() {
  scenarioLibrary.generation++; scenarioLibrary.reading = false; scenarioLibrary.preview = null; scenarioLibrary.previewShown = false;
  byId('scenario-editor-preview').hidden = true;
}

function loadScenarioDraft(scenario, sourceId = null, target = null, preserveUI = false) {
  scenarioLibrary.generation++;
  clearScenarioProblems();
  if (!preserveUI) {
    scenarioLibrary.entryScenario = target ? structuredClone(scenario) : null;
    scenarioLibrary.importWarnings = [];
    expandedBuilderRows.clear();
    byId('scenario-builder-filter').value = '';
  }
  scenarioLibrary.base = structuredClone(scenario);
  scenarioLibrary.sourceId = sourceId;
  if (target !== scenarioLibrary.target) scenarioLibrary.targetBundle = target ? state.bundle : null;
  scenarioLibrary.target = target;
  scenarioLibrary.statements = []; scenarioLibrary.rules = []; scenarioLibrary.nextId = 1;
  for (const [kind, section] of Object.entries(STATEMENT_SECTIONS)) {
    for (const [id, item] of Object.entries(scenario[section] || {}))
      scenarioLibrary.statements.push({ id, kind, ...structuredClone(item) });
  }
  for (const [id, rule] of Object.entries(scenario.rules || {}))
    scenarioLibrary.rules.push({ id, ...structuredClone(rule) });
  byId('scenario-builder-title').value = scenario.title || '';
  byId('scenario-builder-description').value = scenario.description || '';
  byId('scenario-background-details').open = Boolean(scenario.description);
  byId('scenario-rule-text').value = scenarioRuleText(scenario);
  byId('scenario-glossary-text').value = ''; byId('scenario-glossary-file').value = '';
  byId('scenario-symbol-renamer').open = false;
  byId('scenario-rename-from').replaceChildren(); byId('scenario-rename-to').value = '';
  byId('scenario-rename-to').removeAttribute('aria-invalid');
  byId('scenario-bundled-references').textContent = scenario.corpus?.length
    ? 'Included with this example: ' + scenario.corpus.join(', ') + '. Export embeds their content.' : '';
  librarySources.new.reset(scenario.sources || [], true, preserveUI);
  scenarioLibrary.preview = null; scenarioLibrary.previewShown = false; scenarioLibrary.rawChanged = false;
  byId('scenario-editor-preview').hidden = true;
  renderBuilderStatements(); renderBuilderRules(); setScenarioMode(scenarioLibrary.mode);
}

function resetScenarioBuilder() {
  loadScenarioDraft({ title: '', facts: {}, conclusions: {}, rules: {} });
  scenarioLibrary.files = []; byId('scenario-import-files').replaceChildren();
  byId('scenario-file-input').value = ''; byId('scenario-load-files').hidden = true;
  byId('scenario-open-file-project').hidden = true;
  setWorkspaceStatus('scenario-import-status');
  setScenarioMode('guided');
  scenarioLibrary.dirty = false;
}

function discardEditorChanges() {
  if (!scenarioLibrary.target || scenarioLibrary.busy || scenarioLibrary.reading) return;
  if (scenarioLibrary.dirty && !window.confirm('Discard changes made in this editor? The open exploration will stay unchanged.')) return;
  loadScenarioDraft(scenarioLibrary.entryScenario, scenarioLibrary.sourceId, scenarioLibrary.target);
  scenarioLibrary.dirty = false; renderScenarioLibraryAccess();
  setWorkspaceStatus('scenario-library-status', 'Editor changes discarded. The open exploration is unchanged.', 'info');
  byId('scenario-builder-title').focus();
}

function nextScenarioId(prefix) {
  const ids = new Set([...scenarioLibrary.statements, ...scenarioLibrary.rules].map(item => item.id));
  let id;
  do { id = prefix + '_' + scenarioLibrary.nextId++; } while (ids.has(id));
  return id;
}

function proposeReadableId(item) {
  if (!pendingReadableIds.has(item) || pendingSymbolRename()) return false;
  if (item.kind && !item.description.trim()) return false;
  if (!item.kind && (!item.conclusion || item.premises.some(literal => !literal))) return false;
  const description = item.kind ? item.description
    : builderLiteralDescription(item.premises[0] || item.conclusion);
  const common = new Set(['a', 'an', 'the', 'is', 'are', 'be', 'it', 'we', 'should', 'to', 'of']);
  const words = description.normalize('NFKD').toLowerCase().replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/).filter(word => word && !common.has(word)).slice(0, 4);
  const stem = (item.kind ? '' : 'rule_') + (words.join('_') || (item.kind || 'inference'));
  const base = (/^[a-z_]/.test(stem) ? stem : 'item_' + stem).slice(0, 88);
  const ids = new Set([...scenarioLibrary.statements, ...scenarioLibrary.rules].filter(other => other !== item).map(other => other.id));
  let next = base, suffix = 2;
  while (ids.has(next) || Object.hasOwn(Object.prototype, next) || next === 'prototype') next = base + '_' + suffix++;
  const previous = item.id;
  item.id = next; pendingReadableIds.delete(item);
  for (const rule of scenarioLibrary.rules) {
    const rename = literal => literal === previous ? next : literal === '-' + previous ? '-' + next : literal;
    rule.premises = rule.premises.map(rename); rule.conclusion = rename(rule.conclusion);
  }
  if (expandedBuilderRows.delete(previous)) expandedBuilderRows.add(next);
  for (const row of document.querySelectorAll('[data-statement-id], [data-builder-rule-id]')) {
    if (row.dataset.statementId === previous) row.dataset.statementId = next;
    if (row.dataset.builderRuleId === previous) row.dataset.builderRuleId = next;
    for (const field of row.querySelectorAll('[data-editor-field]')) {
      field.dataset.editorField = field.dataset.editorField.replace(':' + previous + ':', ':' + next + ':');
    }
  }
  updateBuilderSummaries(); refreshBuilderChoices(); scenarioDraftChanged();
  return true;
}

function commitPendingReadableIds() {
  // Removing a focused input need not fire blur in every browser. Commit new
  // names before rebuilding rows or serializing; imported and explicit IDs
  // never enter the pending set, and a generated name is proposed only once.
  for (const item of [...scenarioLibrary.statements, ...scenarioLibrary.rules]) proposeReadableId(item);
}

function builderLiteralDescription(literal) {
  if (!literal) return 'choose a statement';
  const negative = literal.startsWith('-'), id = negative ? literal.slice(1) : literal;
  const item = scenarioLibrary.statements.find(statement => statement.id === id)
    || scenarioLibrary.rules.find(rule => rule.id === id);
  if (negative) return item?.negated_description || (item?.premises ? 'Rule does not apply: ' + id : 'Not: ' + (item?.description || id));
  return item?.description || id;
}

function builderRuleSentence(rule) {
  return (rule.premises.length ? 'If ' + rule.premises.map(builderLiteralDescription).join(' and ') + ' then ' : '')
    + (rule.type === 'strict' ? 'necessarily ' : 'normally ') + builderLiteralDescription(rule.conclusion);
}

function updateBuilderSummaries() {
  const draft = scenarioLibrary.rules.length ? scenarioFromBuilder(false) : null;
  for (const item of scenarioLibrary.statements) {
    const row = document.querySelector('[data-statement-id="' + CSS.escape(item.id) + '"]');
    if (!row) continue;
    row.querySelector('.authoring-row-description').textContent = item.description || 'New statement';
    row.querySelector('.authoring-row-symbol').textContent = item.id;
    row.querySelector('.scenario-symbol-label').textContent = 'Symbol: ' + item.id;
    row.querySelector('.scenario-rename-shortcut').setAttribute('aria-label', 'Rename symbol ' + item.id);
    row.dataset.search = [item.id, item.description, item.negated_description, item.category].filter(Boolean).join(' ').toLowerCase();
  }
  for (const rule of scenarioLibrary.rules) {
    const row = document.querySelector('[data-builder-rule-id="' + CSS.escape(rule.id) + '"]');
    if (!row) continue;
    row.querySelector('.authoring-row-symbol').textContent = rule.id;
    row.querySelector('.authoring-row-description').textContent = builderRuleSentence(rule);
    row.querySelector('.scenario-symbol-label').textContent = 'Symbol: ' + rule.id;
    row.querySelector('.authoring-rule-preview').innerHTML = renderRuleText(rule.id, rule, draft);
    row.querySelector('.scenario-rename-shortcut').setAttribute('aria-label', 'Rename symbol ' + rule.id);
    row.dataset.search = [rule.id, builderRuleSentence(rule), rule.category].filter(Boolean).join(' ').toLowerCase();
  }
  filterBuilderRows();
}

function filterBuilderRows() {
  const query = byId('scenario-builder-filter').value.trim().toLowerCase();
  for (const row of document.querySelectorAll('[data-statement-id], [data-builder-rule-id]')) row.hidden = query && !row.dataset.search?.includes(query);
  for (const group of document.querySelectorAll('.authoring-statement-group')) {
    const rows = [...group.querySelectorAll('[data-statement-id]')];
    group.hidden = rows.every(row => row.hidden);
    if (query && !group.hidden) group.open = true;
  }
}

function addBuilderStatement(kind = 'fact', description = '', focus = true) {
  if (scenarioLibrary.statements.length >= 100) {
    setWorkspaceStatus('scenario-library-status', 'Use at most 100 statements in the guided editor.', 'info'); return;
  }
  const item = { id: nextScenarioId('statement'), kind, description };
  pendingReadableIds.add(item); scenarioLibrary.statements.push(item); expandedBuilderRows.add(item.id);
  renderBuilderStatements(); refreshBuilderChoices();
  if (description.trim()) proposeReadableId(item);
  if (focus) { scenarioDraftChanged(); document.querySelector('[data-statement-id="' + CSS.escape(item.id) + '"] input[type=text]').focus(); }
}

function renderBuilderStatements() {
  commitPendingReadableIds();
  const list = byId('scenario-statements'); list.replaceChildren();
  if (!guidedEditorAvailable()) {
    list.textContent = 'This knowledge base is too large for the guided editor. Use Rule text or edit its portable JSON file.';
    return;
  }
  if (!scenarioLibrary.statements.length) {
    const empty = document.createElement('p'); empty.className = 'authoring-empty';
    empty.textContent = 'No statements yet. Add a statement, or try the picnic example.'; list.append(empty);
  }
  const groups = new Map();
  for (const [kind, label] of [['fact', 'Facts'], ['assumption', 'Assumptions'], ['claim', 'Claims']]) {
    const count = scenarioLibrary.statements.filter(item => kind === 'claim' ? ['proposition', 'conclusion'].includes(item.kind) : item.kind === kind).length;
    if (!count) continue;
    const group = document.createElement('details'); group.className = 'authoring-statement-group'; group.open = true;
    const summary = document.createElement('summary'); summary.textContent = label + ' (' + count + ')'; group.append(summary);
    groups.set(kind, group); list.append(group);
  }
  scenarioLibrary.statements.forEach((item, index) => {
    const row = document.createElement('details'); row.className = 'scenario-statement-card'; row.dataset.statementId = item.id;
    row.open = expandedBuilderRows.has(item.id);
    row.addEventListener('toggle', () => { if (row.open) expandedBuilderRows.add(item.id); else expandedBuilderRows.delete(item.id); });
    row.innerHTML = '<summary class="authoring-row-summary"><span class="authoring-row-kind">' + (item.kind === 'conclusion' ? 'Key conclusion' : item.kind === 'proposition' ? 'Claim' : item.kind) + '</span><span class="authoring-row-description"></span><span class="authoring-row-symbol"></span></summary>' +
      '<div class="scenario-statement-row"><label class="visually-hidden">Statement kind</label><select aria-label="Statement ' + (index + 1) + ' kind">' +
      '<option value="fact">Fact</option><option value="assumption">Assumption</option><option value="proposition">Claim</option></select>' +
      '<input type="text" required maxlength="2000" aria-label="Statement ' + (index + 1) + '">' +
      '<button class="btn btn-small" type="button" aria-label="Remove statement ' + (index + 1) + '">×</button></div>' +
      '<label class="scenario-key"><input type="checkbox"> Key conclusion</label>' +
      '<div class="scenario-hint authoring-symbol-line"></div><details class="scenario-statement-details"><summary>Statement details</summary>' +
      '<label>Meaning of its negation<input class="scenario-negation" maxlength="2000" placeholder="Optional explicit wording"></label>' +
      '<div class="scenario-assumption-settings"></div></details>';
    const input = row.querySelector('input[type=text]'), select = row.querySelector('select'), key = row.querySelector('input[type=checkbox]');
    input.id = item.id + '-text'; select.id = item.id + '-kind';
    input.dataset.editorField = 'statement:' + item.id + ':description';
    input.value = item.description; input.placeholder = 'Write this statement in plain English';
    select.value = item.kind === 'conclusion' ? 'proposition' : item.kind;
    key.checked = item.kind === 'conclusion'; key.parentElement.hidden = !['conclusion', 'proposition'].includes(item.kind);
    const symbol = document.createElement('span'); symbol.className = 'scenario-symbol-label';
    row.querySelector('.scenario-hint').append(symbol, symbolRenameShortcut(item));
    if (item.category || item.source) row.querySelector('.scenario-hint').append(document.createTextNode(' ' + [item.category, item.source].filter(Boolean).join(' | ')));
    const negation = row.querySelector('.scenario-negation'); negation.value = item.negated_description || '';
    negation.addEventListener('input', () => { item.negated_description = negation.value || undefined; refreshBuilderChoices(); });
    if (item.kind === 'assumption') addPreferenceControls(row.querySelector('.scenario-assumption-settings'), item);
    input.addEventListener('input', () => { item.description = input.value; refreshBuilderChoices(); updateBuilderSummaries(); });
    input.addEventListener('blur', () => proposeReadableId(item));
    select.addEventListener('change', () => {
      item.kind = select.value;
      renderBuilderStatements(); scenarioDraftChanged();
    });
    key.addEventListener('change', () => { item.kind = key.checked ? 'conclusion' : 'proposition'; row.querySelector('.authoring-row-kind').textContent = key.checked ? 'Key conclusion' : 'Claim'; scenarioDraftChanged(); });
    row.querySelector('button').addEventListener('click', () => {
      scenarioLibrary.statements.splice(index, 1); renderBuilderStatements(); refreshBuilderChoices(); scenarioDraftChanged();
      byId('scenario-add-statement').focus();
    });
    groups.get(['proposition', 'conclusion'].includes(item.kind) ? 'claim' : item.kind).append(row);
  });
  renderSymbolChoices(); updateBuilderSummaries();
}

function addPreferenceControls(host, item) {
  const block = document.createElement('label'); block.textContent = 'Priority (higher is stronger)';
  const number = document.createElement('input'); number.type = 'number'; number.min = '1'; number.max = '1000';
  number.value = item.block ?? 1; block.append(number);
  number.addEventListener('input', () => { item.block = Number(number.value); scenarioDraftChanged(); });
  const active = document.createElement('label'), check = document.createElement('input');
  check.type = 'checkbox'; check.checked = item.active !== false;
  active.append(check, document.createTextNode(' Active'));
  check.addEventListener('change', () => { item.active = check.checked; scenarioDraftChanged(); });
  host.append(block, active);
}

function addBuilderRule(focus = true) {
  if (scenarioLibrary.rules.length >= 100) {
    setWorkspaceStatus('scenario-library-status', 'Use at most 100 rules in the guided editor.', 'info'); return;
  }
  const rule = { id: nextScenarioId('rule'), premises: [''], conclusion: '', type: 'defeasible', block: 1, active: true };
  pendingReadableIds.add(rule); scenarioLibrary.rules.push(rule); expandedBuilderRows.add(rule.id);
  renderBuilderRules();
  if (focus) { scenarioDraftChanged(); byId('scenario-builder-rules').lastElementChild.querySelector('[role=combobox]').focus(); }
}

function builderLiteralOptions(selected) {
  const options = [];
  for (const item of scenarioLibrary.statements) {
    if (!item.description.trim()) continue;
    options.push({ label: item.description, id: item.id, group: 'Statements' });
    options.push({ label: item.negated_description || 'Not: ' + item.description, id: '-' + item.id, group: 'Negated' });
  }
  for (const item of scenarioLibrary.rules.filter(rule => rule.type === 'defeasible')) {
    options.push({ label: item.negated_description || 'Rule does not apply: ' + item.id, id: '-' + item.id, group: 'Rule does not apply' });
    if (selected === item.id) options.push({ label: 'Rule: ' + item.id, id: item.id, group: 'Statements' });
  }
  return options;
}

function createLiteralPicker(label, rule, getValue, setValue, fieldKey) {
  const wrapper = document.createElement('div'); wrapper.className = 'scenario-rule-field authoring-literal-picker'; wrapper.dataset.literal = '';
  const number = ++builderControlNumber, inputId = 'builder-literal-' + number, listId = inputId + '-options';
  wrapper.innerHTML = `<label for="${inputId}">${escapeHtml(label)}</label>
    <div class="authoring-literal-selection" hidden><button type="button" class="authoring-literal-chip"></button>
      <label class="authoring-literal-not"><input type="checkbox"> not</label><button type="button" class="btn btn-small authoring-literal-clear" aria-label="Clear ${escapeAttr(label.toLowerCase())}">Clear</button></div>
    <input id="${inputId}" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${listId}" aria-required="true" autocomplete="off" placeholder="Search statements or symbols">
    <div class="authoring-literal-options" id="${listId}" role="listbox" aria-label="${escapeAttr(label)} choices" hidden></div>
    <p class="scenario-hint visually-hidden authoring-literal-status" role="status"></p>`;
  const input = wrapper.querySelector('[role=combobox]'), list = wrapper.querySelector('[role=listbox]');
  const status = wrapper.querySelector('.authoring-literal-status');
  const selected = wrapper.querySelector('.authoring-literal-selection'), chip = wrapper.querySelector('.authoring-literal-chip');
  const not = wrapper.querySelector('.authoring-literal-not input');
  input.dataset.editorField = fieldKey;
  let visibleOptions = [], active = -1, opened = false;
  const close = () => { opened = false; list.hidden = true; status.classList.add('visually-hidden'); input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); };
  const highlight = index => {
    active = index;
    [...list.querySelectorAll('[role=option]')].forEach((option, position) => option.setAttribute('aria-selected', String(position === active)));
    const option = list.querySelectorAll('[role=option]')[active];
    if (option) { input.setAttribute('aria-activedescendant', option.id); option.scrollIntoView({ block: 'nearest' }); }
    else input.removeAttribute('aria-activedescendant');
  };
  const refreshSelected = () => {
    const value = getValue(), base = value.replace(/^-/, '');
    selected.hidden = !value; input.hidden = Boolean(value);
    chip.textContent = builderLiteralDescription(value) + (value && ![...scenarioLibrary.statements, ...scenarioLibrary.rules].some(item => item.id === base) ? ' (missing statement)' : '');
    chip.setAttribute('aria-label', label + ': ' + builderLiteralDescription(value) + '. Choose another statement.');
    not.checked = value.startsWith('-');
    not.parentElement.hidden = !scenarioLibrary.statements.some(item => item.id === base);
    not.setAttribute('aria-label', 'Negate ' + label.toLowerCase());
    if (value) input.value = '';
  };
  const change = value => {
    setValue(value); clearEditorProblem(input.dataset.editorField); scenarioDraftChanged();
    proposeReadableId(rule); updateBuilderSummaries();
  };
  const choose = value => { change(value); close(); refreshSelected(); chip.focus(); };
  const showOptions = () => {
    const query = input.value.trim().toLowerCase();
    visibleOptions = builderLiteralOptions(getValue()).filter(option => (option.label + ' ' + option.id).toLowerCase().includes(query));
    list.replaceChildren();
    for (const group of ['Statements', 'Negated', 'Rule does not apply']) {
      const choices = visibleOptions.filter(option => option.group === group);
      if (!choices.length) continue;
      const section = document.createElement('div'); section.setAttribute('role', 'group'); section.setAttribute('aria-label', group);
      const heading = document.createElement('div'); heading.className = 'authoring-option-group'; heading.setAttribute('aria-hidden', 'true'); heading.textContent = group; section.append(heading);
      for (const option of choices) {
        const element = document.createElement('div'); element.setAttribute('role', 'option'); element.setAttribute('aria-selected', 'false');
        element.id = listId + '-' + visibleOptions.indexOf(option); element.textContent = option.label + ' [' + option.id + ']';
        element.addEventListener('mousedown', event => event.preventDefault());
        element.addEventListener('click', () => choose(option.id)); section.append(element);
      }
      list.append(section);
    }
    // Match keyboard order to the rendered groups, not the source array order.
    visibleOptions = ['Statements', 'Negated', 'Rule does not apply'].flatMap(group => visibleOptions.filter(option => option.group === group));
    opened = true; list.hidden = !visibleOptions.length;
    input.setAttribute('aria-expanded', String(!list.hidden)); highlight(-1);
    status.classList.toggle('visually-hidden', Boolean(visibleOptions.length));
    status.textContent = visibleOptions.length ? visibleOptions.length + ' choices'
      : 'No matching statements. Add one above, or change the search.';
  };
  wrapper.openPicker = () => { selected.hidden = true; input.hidden = false; input.value = ''; input.focus(); showOptions(); };
  chip.onclick = wrapper.openPicker;
  wrapper.querySelector('.authoring-literal-clear').onclick = () => { change(''); refreshSelected(); wrapper.openPicker(); };
  not.onchange = () => { const base = getValue().replace(/^-/, ''); change((not.checked ? '-' : '') + base); refreshSelected(); };
  input.addEventListener('focus', showOptions);
  input.addEventListener('input', () => { change(''); showOptions(); });
  input.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); event.stopPropagation(); if (list.hidden) showOptions();
      if (visibleOptions.length) highlight(active < 0 ? (event.key === 'ArrowDown' ? 0 : visibleOptions.length - 1)
        : (active + (event.key === 'ArrowDown' ? 1 : -1) + visibleOptions.length) % visibleOptions.length);
    } else if (event.key === 'Enter' && opened) {
      event.preventDefault(); event.stopPropagation(); if (active >= 0) choose(visibleOptions[active].id);
    } else if (event.key === 'Escape' && opened) { event.preventDefault(); event.stopPropagation(); close(); if (getValue()) { refreshSelected(); chip.focus(); } }
    else if (event.key === 'Tab') close();
  });
  input.addEventListener('blur', () => { close(); if (getValue()) refreshSelected(); });
  wrapper.refreshChoices = () => { if (document.activeElement !== input) refreshSelected(); if (opened) showOptions(); };
  refreshSelected(); return wrapper;
}

function refreshBuilderChoices() {
  for (const picker of document.querySelectorAll('#scenario-builder-rules [data-literal]')) picker.refreshChoices?.();
  renderSymbolChoices();
}

function renderBuilderRules() {
  const list = byId('scenario-builder-rules'); list.replaceChildren();
  renderSymbolChoices();
  if (!guidedEditorAvailable()) return;
  if (!scenarioLibrary.rules.length) { const empty = document.createElement('p'); empty.className = 'authoring-empty'; empty.textContent = 'No rules yet. Add a rule to connect your statements.'; list.append(empty); }
  scenarioLibrary.rules.forEach((rule, index) => {
    const card = document.createElement('details'); card.className = 'scenario-rule-card'; card.dataset.builderRuleId = rule.id;
    card.open = expandedBuilderRows.has(rule.id);
    card.addEventListener('toggle', () => { if (card.open) expandedBuilderRows.add(rule.id); else expandedBuilderRows.delete(rule.id); });
    card.innerHTML = '<summary class="authoring-row-summary"><span class="authoring-row-symbol"></span><span class="authoring-row-description"></span></summary><p class="authoring-rule-preview"></p>';
    const choose = (label, getter, setter, key) => {
      const field = createLiteralPicker(label, rule, getter, setter, 'rule:' + rule.id + ':' + key);
      card.append(field); return field;
    };
    rule.premises.forEach((premise, position) => {
      choose(position ? 'And' : 'If', () => rule.premises[position], value => { rule.premises[position] = value; }, 'premise:' + position);
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-small'; remove.textContent = 'Remove condition';
      remove.setAttribute('aria-label', 'Remove condition ' + (position + 1) + ' from rule ' + rule.id);
      remove.onclick = () => { rule.premises.splice(position, 1); renderBuilderRules(); scenarioDraftChanged(); };
      card.append(remove);
    });
    if (!rule.premises.length) { const note = document.createElement('p'); note.className = 'scenario-hint'; note.textContent = 'No conditions, this rule has an empty premise.'; card.append(note); }
    const add = document.createElement('button'); add.type = 'button'; add.className = 'btn btn-small'; add.textContent = '+ Condition';
    add.disabled = rule.premises.length >= 50;
    add.onclick = () => { rule.premises.push(''); renderBuilderRules(); scenarioDraftChanged(); };
    const strength = document.createElement('label'); strength.className = 'scenario-rule-field';
    strength.innerHTML = '<span>Then</span><select aria-label="Rule strength"><option value="defeasible">Usually (defeasible)</option><option value="strict">Always (strict)</option></select>';
    const select = strength.querySelector('select'); select.value = rule.type;
    select.onchange = () => { rule.type = select.value; renderBuilderRules(); scenarioDraftChanged(); };
    card.append(add, strength); choose('Conclude', () => rule.conclusion, value => { rule.conclusion = value; }, 'conclusion');
    const details = document.createElement('details'); details.className = 'scenario-rule-details';
    const summary = document.createElement('summary'); summary.textContent = 'Priority & details (' + rule.id + ')'; details.append(summary);
    const symbolLine = document.createElement('div'); symbolLine.className = 'scenario-hint authoring-symbol-line';
    const symbol = document.createElement('span'); symbol.className = 'scenario-symbol-label'; symbol.textContent = 'Symbol: ' + rule.id;
    symbolLine.append(symbol, symbolRenameShortcut(rule)); card.append(symbolLine);
    if (rule.type === 'defeasible') addPreferenceControls(details, rule);
    if (rule.category || rule.source) {
      const note = document.createElement('p'); note.textContent = [rule.category, rule.source].filter(Boolean).join(' | '); details.append(note);
    }
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-small'; remove.textContent = 'Remove rule';
    remove.setAttribute('aria-label', 'Remove rule ' + rule.id);
    remove.onclick = () => { scenarioLibrary.rules.splice(index, 1); renderBuilderRules(); scenarioDraftChanged(); byId('scenario-add-rule').focus(); };
    card.append(details, remove); list.append(card);
  });
  updateBuilderSummaries();
}

function scenarioStarter() {
  return { title: 'Planning a picnic', description: 'Compare two reasons for and against an outdoor picnic.',
    facts: { sunny: { description: 'The forecast is sunny' }, windy: { description: 'A strong wind is expected' } },
    conclusions: { outside: { description: 'We should hold the picnic outside', negated_description: 'We should not hold the picnic outside' } },
    rules: { sunshine: { type: 'defeasible', premises: ['sunny'], conclusion: 'outside', block: 1 },
      wind: { type: 'defeasible', premises: ['windy'], conclusion: '-outside', block: 1 } } };
}

function useScenarioStarter() {
  if (scenarioLibrary.dirty && !window.confirm('Replace this unfinished draft with the small example?')) return;
  loadScenarioDraft(scenarioStarter()); setScenarioMode('guided'); scenarioDraftChanged();
  setWorkspaceStatus('scenario-library-status', 'A starting point. Edit the words, rules or documents, then Preview.', 'info');
  byId('scenario-builder-title').focus();
}

function editorProblemField(key) {
  return [...byId('scenario-builder-form').querySelectorAll('[data-editor-field]')].find(field => field.dataset.editorField === key);
}

function clearScenarioProblems() {
  scenarioLibrary.problems = [];
  for (const error of byId('scenario-builder-form').querySelectorAll('.authoring-field-error')) error.remove();
  for (const field of byId('scenario-builder-form').querySelectorAll('[data-editor-field]')) {
    field.removeAttribute('aria-invalid');
    const described = (field.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && !id.startsWith('authoring-error-'));
    if (described.length) field.setAttribute('aria-describedby', described.join(' ')); else field.removeAttribute('aria-describedby');
  }
  byId('scenario-error-summary').replaceChildren(); byId('scenario-error-summary').hidden = true;
}

function goToEditorProblem(key) {
  const field = editorProblemField(key);
  if (!field) return;
  byId('scenario-builder-filter').value = ''; filterBuilderRows();
  if (key === 'rule-text') setScenarioMode('text');
  for (let parent = field.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
  if (field.hidden) field.closest('[data-literal]')?.openPicker();
  field.scrollIntoView({ block: 'center' }); field.focus();
}

function showScenarioProblems(problems) {
  clearScenarioProblems(); scenarioLibrary.problems = problems;
  const summary = byId('scenario-error-summary'); summary.hidden = false;
  const count = document.createElement('span'); count.textContent = problems.length + (problems.length === 1 ? ' problem' : ' problems'); summary.append(count);
  for (const [index, problem] of problems.entries()) {
    const field = editorProblemField(problem.field);
    if (!field) continue;
    const error = document.createElement('p'); error.className = 'authoring-field-error'; error.id = 'authoring-error-' + index;
    error.textContent = problem.message; field.setAttribute('aria-invalid', 'true');
    field.setAttribute('aria-describedby', [field.getAttribute('aria-describedby'), error.id].filter(Boolean).join(' '));
    field.insertAdjacentElement('afterend', error);
    for (let parent = field.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
    const link = document.createElement('button'); link.type = 'button'; link.className = 'btn btn-small';
    link.textContent = index ? 'Problem ' + (index + 1) : 'Go to problem';
    link.setAttribute('aria-label', 'Go to problem: ' + problem.message);
    link.onclick = () => goToEditorProblem(problem.field); summary.append(link);
  }
}

function clearEditorProblem(key) {
  if (!key || !scenarioLibrary.problems.some(problem => problem.field === key)) return;
  const remaining = scenarioLibrary.problems.filter(problem => problem.field !== key);
  if (remaining.length) showScenarioProblems(remaining); else clearScenarioProblems();
}

function scenarioFromBuilder(validate = true) {
  const result = { ...structuredClone(scenarioLibrary.base), title: byId('scenario-builder-title').value.trim(),
    description: byId('scenario-builder-description').value, facts: {}, assumptions: {}, propositions: {}, conclusions: {}, rules: {} };
  const problems = [];
  if (!result.title) problems.push({ field: 'title', message: 'Give your scenario a title.' });
  for (const item of scenarioLibrary.statements) {
    if (!item.description.trim()) problems.push({ field: 'statement:' + item.id + ':description', message: 'Write this statement, or remove its empty row.' });
    const { id, kind, ...data } = item;
    if (kind !== 'fact' && kind !== 'assumption') delete data.source;
    if (kind !== 'assumption') { delete data.active; delete data.block; }
    result[STATEMENT_SECTIONS[kind]][id] = data;
  }
  const ids = new Set([...scenarioLibrary.statements, ...scenarioLibrary.rules].map(item => item.id));
  for (const item of scenarioLibrary.rules) {
    for (const [index, literal] of item.premises.entries()) if (!ids.has(literal.replace(/^-/, '')))
      problems.push({ field: 'rule:' + item.id + ':premise:' + index, message: 'Choose an existing statement for this condition.' });
    if (!ids.has(item.conclusion.replace(/^-/, '')))
      problems.push({ field: 'rule:' + item.id + ':conclusion', message: 'Choose an existing statement for this conclusion.' });
    const { id, ...rule } = item;
    if (rule.type === 'strict') delete rule.active;
    result.rules[id] = structuredClone(rule);
  }
  if (validate && problems.length) {
    const error = new Error(problems.length + (problems.length === 1 ? ' problem needs attention.' : ' problems need attention.'));
    error.editorProblems = problems; throw error;
  }
  return result;
}

function scenarioRuleText(scenario) {
  const lines = ['# ABDA-NL rule text', '# Block 1'];
  for (const id of Object.keys(scenario.facts || {})) lines.push('-> ' + id);
  const blocks = new Map();
  const add = (block, line) => { if (!blocks.has(block)) blocks.set(block, []); blocks.get(block).push(line); };
  for (const [id, item] of Object.entries(scenario.assumptions || {}))
    add(item.block ?? 1, (item.active === false ? '# [suspended] ' : '') + '=> ' + id + ' [' + id + ']');
  for (const [id, rule] of Object.entries(scenario.rules || {}))
    add(rule.block ?? 1, (rule.type === 'defeasible' && rule.active === false ? '# [suspended] ' : '') +
      (rule.premises.length ? rule.premises.join(', ') + ' ' : '') + (rule.type === 'strict' ? '-> ' : '=> ') + rule.conclusion + ' [' + id + ']');
  for (const block of [...blocks.keys()].sort((a, b) => a - b)) lines.push('', '# Block ' + block, ...blocks.get(block));
  return lines.join('\n');
}

async function previewScenarioDraft(showPreview = true) {
  if (scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || !state.authSession.authenticated) return null;
  if (pendingSymbolRename()) { setWorkspaceStatus('scenario-library-status', 'Rename or cancel the pending symbol change before previewing.', 'info'); return null; }
  if (!scenarioLibrary.rawChanged) commitPendingReadableIds();
  const generation = scenarioLibrary.generation, account = state.authSession.user?.id;
  let completionGeneration = generation;
  scenarioLibrary.reading = true; renderScenarioLibraryAccess();
  setWorkspaceStatus('scenario-library-status', 'Checking rules and computing the argumentation preview...', 'info');
  try {
    clearScenarioProblems();
    const scenario = scenarioFromBuilder(!scenarioLibrary.rawChanged);
    if (!scenario.title) { const error = new Error('Give your scenario a title.'); error.editorProblems = [{ field: 'title', message: error.message }]; throw error; }
    try { scenario.sources = librarySources.new.value(); }
    catch (error) { error.editorProblems = [{ field: 'sources', message: error.message }]; throw error; }
    const result = await apiRequest('/api/projects/editor/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, source_scenario_id: scenarioLibrary.sourceId,
        rules: scenarioLibrary.rawChanged ? byId('scenario-rule-text').value : null, glossary: byId('scenario-glossary-text').value }) });
    if (generation !== scenarioLibrary.generation || account !== state.authSession.user?.id) return null;
    const warnings = [...new Set([...scenarioLibrary.importWarnings, ...librarySources.new.warnings(), ...(result.warnings || [])])];
    result.warnings = warnings;
    loadScenarioDraft(result.scenario, result.source_scenario_id, scenarioLibrary.target, true);
    completionGeneration = scenarioLibrary.generation;
    scenarioLibrary.preview = result; scenarioLibrary.dirty = true;
    if (showPreview) renderScenarioPreview(result);
    setWorkspaceStatus('scenario-library-status', showPreview ? 'Preview ready. Save when the scenario looks right.' : 'The same draft is updated. Nothing has been saved yet.', 'success');
    return result;
  } catch (error) {
    if (generation === scenarioLibrary.generation && account === state.authSession.user?.id) {
      showScenarioProblems(error.editorProblems || [{ field: scenarioLibrary.rawChanged ? 'rule-text' : 'knowledge-base', message: error.message }]);
      setWorkspaceStatus('scenario-library-status', error.message, 'error');
    }
    return null;
  } finally {
    // loadScenarioDraft advances the generation, but only synchronously after success.
    if (completionGeneration === scenarioLibrary.generation && account === state.authSession.user?.id) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); }
  }
}

function renderScenarioPreview(result) {
  const scenario = result.scenario, host = byId('scenario-preview-results'); host.replaceChildren();
  byId('scenario-file-counts').replaceChildren();
  for (const section of ['facts', 'assumptions', 'propositions', 'conclusions', 'rules']) {
    const span = document.createElement('span'); span.textContent = Object.keys(scenario[section] || {}).length + ' ' + section;
    byId('scenario-file-counts').append(span);
  }
  const conclusions = Object.entries(scenario.conclusions || {});
  const heading = document.createElement('h4'); heading.textContent = 'Key conclusions'; host.append(heading);
  if (!conclusions.length) { const note = document.createElement('p'); note.textContent = 'No key conclusions selected. All statements remain available in the explorer.'; host.append(note); }
  for (const [id, item] of conclusions) {
    const row = document.createElement('p'); row.className = 'scenario-preview-claim';
    const label = document.createElement('span'), status = result.af.labels_by_proposition[id] || 'absent';
    label.className = 'conclusion-status-bar status-' + status;
    label.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    row.append(document.createTextNode(item.description), label); host.append(row);
  }
  const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Review rules in plain language'; details.append(summary);
  const list = document.createElement('ol');
  for (const [id, rule] of Object.entries(scenario.rules || {})) {
    const item = document.createElement('li');
    item.innerHTML = (rule.active === false ? '<span class="scenario-hint">Suspended. </span>' : '') + renderRuleText(id, rule, scenario);
    list.append(item);
  }
  details.append(list); host.append(details);
  const sources = document.createElement('p'); sources.className = 'scenario-hint';
  sources.textContent = 'Reference documents: ' + [...(scenario.corpus || []), ...(scenario.sources || []).map(source => source.filename)].join(', ');
  host.append(sources);
  byId('scenario-file-warnings').textContent = result.warnings.join('\n');
  scenarioLibrary.previewShown = true;
  byId('scenario-editor-preview').hidden = false;
  byId('scenario-editor-preview').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function suggestScenarioFileRole(file, text) {
  if (/\.pdf$/i.test(file.name)) return { role: 'source', confirmed: true, reason: 'PDF reference document' };
  const content = text.trim();
  try {
    const data = JSON.parse(content);
    if (data && typeof data === 'object' && !Array.isArray(data) && (data.format === 'abda-nl-scenario' || data.scenario || (data.title && (data.facts || data.rules))))
      return { role: 'scenario', confirmed: true, reason: 'JSON scenario structure detected' };
  } catch (_) { /* YAML and plain text are inspected below, then validated on the server. */ }
  if (/^(?:title|format):\s*\S/m.test(content) && /^(?:scenario|facts|rules):(?:\s*$|\s*[{[])/m.test(content))
    return { role: 'scenario', confirmed: true, reason: 'YAML scenario structure detected' };
  const lines = content.split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith('#'));
  const rule = /^(?:(?:-?[A-Za-z_][A-Za-z0-9_]*)(?:\s*,\s*-?[A-Za-z_][A-Za-z0-9_]*)*\s*)?(?:->|=>)\s*-?[A-Za-z_][A-Za-z0-9_]*(?:\s*\[[A-Za-z_][A-Za-z0-9_]*\])?\s*$/;
  if (lines.length && lines.every(line => rule.test(line))) return { role: 'rules', confirmed: true, reason: 'Formal rule lines detected' };
  if (lines.length && lines.every(line => /^-?[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S/.test(line)))
    return { role: 'glossary', confirmed: true, reason: 'Symbol = meaning lines detected' };
  return { role: /\.(txt|md)$/i.test(file.name) ? 'source' : '', confirmed: false,
    reason: /->|=>/.test(content) ? 'Text contains arrows but is not clearly formal rules. Confirm its role.' : 'Text could be a document or scenario material. Confirm its role.' };
}

function renderScenarioImportFiles() {
  const host = byId('scenario-import-files'); host.replaceChildren();
  for (const entry of scenarioLibrary.files) {
    const row = document.createElement('div'); row.className = 'scenario-import-row';
    const info = document.createElement('div'), name = document.createElement('strong'); name.textContent = entry.file.name;
    const size = document.createElement('span'); size.className = 'authoring-import-size'; size.textContent = (entry.file.size / 1000).toFixed(1) + ' KB upload';
    const progress = document.createElement('span'); progress.className = 'authoring-import-progress';
    progress.textContent = entry.status || entry.reason || 'Inspecting file...';
    if (entry.page_count) size.textContent += ', ' + entry.page_count + ' pages';
    info.append(name, size, progress);
    const controls = document.createElement('div'), select = document.createElement('select'); select.setAttribute('aria-label', 'File role: ' + entry.file.name);
    for (const [value, text] of [['', 'Choose file role'], ['scenario', 'Complete scenario'], ['rules', 'ASPIC- rules'], ['glossary', 'Glossary'], ['source', 'Reference document']]) select.add(new Option(text, value));
    select.value = entry.role || '';
    select.onchange = () => { entry.role = select.value; entry.confirmed = Boolean(select.value); entry.loaded = false; entry.status = entry.confirmed ? 'Role selected. Ready to check.' : 'Choose a role.'; renderScenarioImportFiles(); renderScenarioLibraryAccess(); };
    controls.append(select);
    if (entry.role && !entry.confirmed) {
      const label = document.createElement('label'); label.className = 'authoring-import-confirm'; const check = document.createElement('input'); check.type = 'checkbox';
      label.append(check, document.createTextNode('Use the suggested role')); controls.append(label);
      check.onchange = () => { entry.confirmed = check.checked; entry.status = check.checked ? 'Role confirmed. Ready to check.' : 'Confirm this role before loading.'; progress.textContent = entry.status; renderScenarioLibraryAccess(); };
    }
    row.append(info, controls); host.append(row);
  }
  const pending = scenarioLibrary.files.length && !scenarioLibrary.files.every(entry => entry.loaded);
  byId('scenario-load-files').hidden = !pending;
  byId('scenario-open-file-project').hidden = !pending || !scenarioLibrary.files.some(entry => entry.role === 'scenario');
}

async function queueScenarioFiles(files) {
  if (scenarioLibrary.busy || scenarioLibrary.reading || !state.authSession.authenticated || !files.length) return;
  if (files.length > 22 || files.some(file => file.size > SCENARIO_FILE_LIMIT)) {
    setWorkspaceStatus('scenario-import-status', 'Choose up to 22 files, each at most 1 MB.', 'error'); return;
  }
  const generation = scenarioLibrary.generation, account = state.authSession.user?.id;
  scenarioLibrary.files = files.map(file => ({ file, role: '', confirmed: false }));
  scenarioLibrary.reading = true; renderScenarioImportFiles(); renderScenarioLibraryAccess();
  try {
    for (const entry of scenarioLibrary.files) {
      const text = /\.pdf$/i.test(entry.file.name) ? '' : await readMaterialText(entry.file, SCENARIO_FILE_LIMIT);
      if (generation !== scenarioLibrary.generation || account !== state.authSession.user?.id) return;
      Object.assign(entry, suggestScenarioFileRole(entry.file, text));
    }
    renderScenarioImportFiles();
    setWorkspaceStatus('scenario-import-status', 'Check the suggested roles. Confirm ambiguous text or choose a role. The editor stays unchanged until every file passes.', 'info');
  } catch (error) {
    if (generation === scenarioLibrary.generation && account === state.authSession.user?.id) setWorkspaceStatus('scenario-import-status', error.message, 'error');
  } finally {
    if (generation === scenarioLibrary.generation && account === state.authSession.user?.id) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); }
  }
}

async function loadScenarioFiles(openProject = false) {
  if (scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || !state.authSession.authenticated) return;
  const entries = scenarioLibrary.files;
  if (!entries.length || entries.some(entry => !entry.role || !entry.confirmed)) { setWorkspaceStatus('scenario-import-status', 'Choose or confirm a role for every file.', 'error'); return; }
  const byRole = role => entries.filter(entry => entry.role === role);
  if (byRole('scenario').length + byRole('rules').length > 1 || byRole('glossary').length > 1) {
    setWorkspaceStatus('scenario-import-status', 'Choose one knowledge base (complete scenario or rule text), and at most one glossary.', 'error'); return;
  }
  if ((byRole('scenario').length || byRole('rules').length) && scenarioLibrary.dirty
      && !window.confirm('Replace this editor draft with the selected files?')) return;
  const generation = scenarioLibrary.generation, account = state.authSession.user?.id;
  let completionGeneration = generation, activeEntry = null, loaded = false;
  scenarioLibrary.reading = true; renderScenarioLibraryAccess();
  const current = () => generation === scenarioLibrary.generation && account === state.authSession.user?.id;
  const start = entry => { activeEntry = entry; entry.status = 'Checking...'; renderScenarioImportFiles(); renderScenarioLibraryAccess(); setWorkspaceStatus('scenario-import-status', 'Checking ' + entry.file.name + '...', 'info'); };
  const done = entry => { entry.status = 'Checked. Waiting for the complete scenario.'; renderScenarioImportFiles(); renderScenarioLibraryAccess(); };
  try {
    let candidate = scenarioFromBuilder(false), sourceId = scenarioLibrary.sourceId, glossary = '', rawRules = null;
    const keepsDocuments = !byRole('scenario').length && !byRole('rules').length;
    const warnings = keepsDocuments ? [...scenarioLibrary.importWarnings, ...librarySources.new.warnings()] : [];
    const metadata = keepsDocuments ? [...librarySources.new.metadata.entries()] : [];
    if (byRole('scenario').length) {
      const entry = byRole('scenario')[0]; start(entry);
      const text = await readMaterialText(entry.file, SCENARIO_FILE_LIMIT);
      if (!current()) return;
      const result = await apiRequest('/api/projects/import/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
      if (!current()) return;
      candidate = result.scenario; sourceId = result.source_scenario_id; warnings.push(...(result.warnings || [])); done(entry);
    } else if (byRole('rules').length) {
      const entry = byRole('rules')[0]; start(entry);
      rawRules = await readMaterialText(entry.file, 100000); if (!current()) return;
      candidate = { title: entry.file.name.replace(/\.[^.]+$/, '').slice(0, 120), facts: {}, rules: {} }; sourceId = null; done(entry);
    } else candidate.sources = librarySources.new.value();
    if (byRole('glossary').length) { const entry = byRole('glossary')[0]; start(entry); glossary = await readMaterialText(entry.file, 200000); if (!current()) return; done(entry); }
    candidate.sources = [...(candidate.sources || [])];
    for (const entry of byRole('source')) {
      start(entry); const result = await previewSourceUpload(entry.file); if (!current()) return;
      candidate.sources.push(result.source); warnings.push(...(result.warnings || []));
      if (Number.isInteger(result.page_count) && result.page_count > 0) entry.page_count = result.page_count;
      metadata.push([result.source.filename, { warnings: result.warnings || [], ...(entry.page_count ? { page_count: entry.page_count } : {}) }]); done(entry);
    }
    setWorkspaceStatus('scenario-import-status', 'Checking all materials together...', 'info'); activeEntry = null;
    const result = await apiRequest('/api/projects/editor/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: candidate, source_scenario_id: sourceId, rules: rawRules, glossary }) });
    if (!current()) return;
    loadScenarioDraft(result.scenario, sourceId, null); setScenarioMode('guided'); scenarioLibrary.dirty = true;
    scenarioLibrary.importWarnings = [...new Set(warnings)];
    for (const [name, receipt] of metadata) librarySources.new.metadata.set(name, receipt);
    librarySources.new.render();
    result.warnings = [...new Set([...warnings, ...(result.warnings || [])])]; scenarioLibrary.preview = result;
    completionGeneration = scenarioLibrary.generation;
    for (const entry of entries) { entry.loaded = true; entry.status = '✓ Loaded into editor'; }
    renderScenarioImportFiles(); byId('scenario-file-input').value = '';
    if (result.warnings.length) renderScenarioPreview(result);
    setWorkspaceStatus('scenario-import-status', result.warnings.length ? 'Materials loaded. Review the warnings below before saving.' : 'All files loaded and checked. Save when ready.', 'success');
    loaded = true;
  } catch (error) {
    if (current()) {
      if (activeEntry) { activeEntry.status = 'Could not load: ' + error.message; renderScenarioImportFiles(); }
      setWorkspaceStatus('scenario-import-status', error.message + ' Your previous editor draft is unchanged.', 'error');
    }
  } finally { if (completionGeneration === scenarioLibrary.generation && account === state.authSession.user?.id) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); } }
  if (loaded && openProject && !scenarioLibrary.preview.warnings.length) await submitScenarioLibrary();
}

async function openPrivateScenarioEditor() {
  if (!state.activeProject || hasPendingStateRequest() || state.projectSavePending) return;
  if (scenarioLibrary.dirty && !window.confirm('Replace the unfinished editor draft with this private project?')) return;
  loadScenarioDraft(state.bundle.scenario, state.activeProject.source_scenario_id, state.activeProject);
  scenarioLibrary.targetBundle = state.bundle;
  setScenarioMode('guided'); scenarioLibrary.dirty = false; openScenarioLibrary();
  setWorkspaceStatus('scenario-library-status', 'Edits update this private project and its shared links. Published examples keep their separate snapshot.', 'info');
}

async function submitScenarioLibrary() {
  if (scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || !state.authSession.authenticated || pendingSymbolRename()) return;
  if (hasPendingStateRequest() || state.projectSavePending) { setWorkspaceStatus('scenario-library-status', 'Wait for the current change or save to finish.', 'info'); return; }
  if (scenarioLibrary.target && (state.readOnly || state.activeProject !== scenarioLibrary.target || state.bundle !== scenarioLibrary.targetBundle)) { renderScenarioLibraryAccess(); return; }
  if (!scenarioLibrary.preview) {
    const checked = await previewScenarioDraft(false);
    if (!checked) return;
    if (checked.warnings.length) {
      renderScenarioPreview(checked);
      setWorkspaceStatus('scenario-library-status', 'Check the warnings, then choose Save to continue.', 'info');
      return;
    }
  }
  if (scenarioLibrary.preview.warnings.length && !scenarioLibrary.previewShown) { renderScenarioPreview(scenarioLibrary.preview); return; }
  if (!state.authSession.authenticated || hasPendingStateRequest() || state.projectSavePending) { renderScenarioLibraryAccess(); return; }
  const target = scenarioLibrary.target, scenario = scenarioLibrary.preview.scenario;
  if (!target && hasUnsavedChanges() && !window.confirm('Open the new project and discard unsaved edits in the current view? Download or save them first if you want to keep them.')) return;
  const previousBundle = state.bundle, previousOps = state.diff_ops, previousProject = state.activeProject;
  const previousUser = state.authSession.user?.id, previousRequest = currentRequest, generation = scenarioLibrary.generation;
  let completionGeneration = generation;
  if (target && (state.readOnly || state.activeProject !== target || state.bundle !== scenarioLibrary.targetBundle)) { setWorkspaceStatus('scenario-library-status', 'The project changed elsewhere. Reopen its editor before saving. Your draft is preserved.', 'error'); return; }
  scenarioLibrary.busy = true; renderScenarioLibraryAccess();
  try {
    const project = await apiRequest(target ? '/api/projects/' + encodeURIComponent(target.id) : '/api/projects/import', {
      method: target ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(target ? { expected_version: target.version, name: scenario.title, description: (scenario.description || '').slice(0, 4000), scenario }
        : { name: scenario.title, description: (scenario.description || '').slice(0, 4000), source_scenario_id: scenarioLibrary.sourceId, scenario }),
    });
    if (state.authSession.user?.id !== previousUser || generation !== scenarioLibrary.generation) return;
    resetScenarioBuilder(); completionGeneration = scenarioLibrary.generation;
    const changed = state.bundle !== previousBundle || state.diff_ops !== previousOps || state.activeProject !== previousProject || currentRequest !== previousRequest;
    if (!changed) {
      setViewContext('project', project); state.scenario_id = project.source_scenario_id; state.baseline = project.scenario; state.diff_ops = [];
      setBundle({ scenario: project.scenario, af: project.af });
      resetChatConversation(); resetViewFilters(); indexBundle(); populateScenarioSelect(); renderAll();
      if (new URLSearchParams(window.location.hash.slice(1)).has('share')) window.history.replaceState({}, '', window.location.pathname + window.location.search);
      requestCloseModal('modal-scenario-library');
    }
    await refreshProjects({ quiet: true });
    showGlobalStatus(changed ? 'Saved "' + project.name + '". Open it from My projects when ready.'
      : 'Opened "' + project.name + '". Saved privately, ready to explore.', 'success');
    setWorkspaceStatus('scenario-library-status');
  } catch (error) {
    if (state.authSession.user?.id !== previousUser || generation !== scenarioLibrary.generation) return;
    setWorkspaceStatus('scenario-library-status', error.code === 'project_version_conflict'
      ? 'This project changed elsewhere. Your draft has not replaced newer work. Reopen the project before saving.' : error.message, 'error');
  } finally {
    if (completionGeneration === scenarioLibrary.generation && state.authSession.user?.id === previousUser) { scenarioLibrary.busy = false; renderScenarioLibraryAccess(); }
  }
}

async function downloadScenarioFile(scenario, sourceId) {
  const account = state.authSession.user?.id;
  const payload = await apiRequest('/api/scenarios/export', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario, source_scenario_id: sourceId || null }) });
  if (account !== state.authSession.user?.id) throw new Error('Account changed. Reopen the scenario before downloading.');
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload) + '\n'], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  const slug = (scenario.title || 'scenario').normalize('NFKD').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70);
  link.download = `${slug || 'scenario'}.abda.json`;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function downloadCurrentScenario() {
  const status = (message, kind) => byId('modal-scenario-library').classList.contains('visible')
    ? setWorkspaceStatus('scenario-library-status', message, kind) : showGlobalStatus(message, kind);
  if (!state.bundle || hasPendingStateRequest()) {
    status('Wait for the current scenario to finish loading.', 'info');
    return;
  }
  const example = state.scenarios.find(item => item.id === state.scenario_id);
  const exampleSource = example?.category === 'community' ? example.source_scenario_id : state.scenario_id;
  const sourceId = state.activeProject?.source_scenario_id || state.sharedProject?.source_scenario_id
    || (state.viewKind === 'example' ? exampleSource : null);
  const scenario = structuredClone(state.bundle.scenario);
  const account = state.authSession.user?.id;
  status('Preparing a self-contained file with complete reference text...', 'info');
  try {
    await downloadScenarioFile(scenario, sourceId);
    if (account === state.authSession.user?.id) status('Downloaded all rules, meanings and reference text. Import scenario can reopen this file without the original server. PDFs use extracted text, not the original page layout.', 'success');
  } catch (error) { if (account === state.authSession.user?.id) status(error.message, 'error'); }
}
