/* One private scenario draft, with guided and textual views of the same rules. */
const scenarioLibrary = {
  tab: 'new', mode: 'guided', statements: [], rules: [], nextId: 1,
  base: {}, sourceId: null, target: null, targetBundle: null, preview: null, generation: 0,
  busy: false, reading: false, dirty: false, rawChanged: false, files: [],
};
const SCENARIO_FILE_LIMIT = 1000000;
const STATEMENT_SECTIONS = { fact: 'facts', assumption: 'assumptions', proposition: 'propositions', conclusion: 'conclusions' };

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

function symbolRenameShortcut(id) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'btn btn-small scenario-rename-shortcut'; button.textContent = 'Rename';
  button.setAttribute('aria-label', 'Rename symbol ' + id);
  button.addEventListener('click', () => openSymbolRename(id));
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
    const renamed = renameScenarioSymbol(scenarioFromBuilder(false), from, to);
    scenarioLibrary.base = renamed;
    scenarioLibrary.statements = Object.entries(STATEMENT_SECTIONS).flatMap(([kind, section]) =>
      Object.entries(renamed[section]).map(([id, data]) => ({ id, kind, ...data })));
    scenarioLibrary.rules = Object.entries(renamed.rules).map(([id, data]) => ({ id, ...data }));
    scenarioLibrary.generation++;
    byId('scenario-rule-text').value = scenarioRuleText(renamed);
    renderBuilderStatements(); renderBuilderRules(); renderSymbolChoices(to);
    byId('scenario-rename-to').removeAttribute('aria-invalid');
    scenarioDraftChanged();
    setWorkspaceStatus('scenario-library-status', 'Renamed ' + from + ' to ' + to + '. Logical references and meanings were preserved. Preview again before saving.', 'success');
    byId('scenario-rename-to').focus();
  } catch (error) {
    byId('scenario-rename-to').setAttribute('aria-invalid', 'true');
    setWorkspaceStatus('scenario-library-status', error.message, 'error');
    byId('scenario-rename-to').focus();
  }
}

function scenarioDraftChanged() {
  scenarioLibrary.dirty = true;
  scenarioLibrary.preview = null;
  byId('scenario-editor-preview').hidden = true;
  renderScenarioLibraryAccess();
}

function initScenarioLibrary() {
  initCurationUI();
  initScenarioMaterials();
  byId('scenario-library-btn').addEventListener('click', openScenarioLibrary);
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
    if (!event.target.closest('#scenario-symbol-renamer')) scenarioDraftChanged();
  });
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
  byId('scenario-load-files').addEventListener('click', loadScenarioFiles);
  const dropZone = byId('scenario-drop-zone');
  dropZone.addEventListener('dragover', event => { event.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', event => {
    event.preventDefault(); dropZone.classList.remove('drag-over');
    queueScenarioFiles([...event.dataTransfer.files]);
  });
  byId('scenario-glossary-file').addEventListener('change', async event => {
    if (scenarioLibrary.busy || scenarioLibrary.reading) return;
    const generation = scenarioLibrary.generation;
    scenarioLibrary.reading = true; renderScenarioLibraryAccess();
    try {
      const text = await readMaterialText(event.target.files[0], 200000);
      if (text !== null && generation === scenarioLibrary.generation) {
        byId('scenario-glossary-text').value = text; scenarioDraftChanged();
      }
    } catch (error) { if (generation === scenarioLibrary.generation) setWorkspaceStatus('scenario-library-status', error.message, 'error'); }
    finally { if (generation === scenarioLibrary.generation) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); } }
  });
  byId('scenario-apply-glossary').addEventListener('click', () => previewScenarioDraft(false));
  byId('scenario-download-current').addEventListener('click', downloadCurrentScenario);
  byId('scenario-template-btn').addEventListener('click', async () => {
    try { await downloadScenarioFile(scenarioStarter(), null); }
    catch (error) { setWorkspaceStatus('scenario-library-status', error.message, 'error'); }
  });
  resetScenarioBuilder();
  window.addEventListener('beforeunload', event => {
    if (!scenarioLibrary.dirty || !state.authSession.authenticated) return;
    event.preventDefault(); event.returnValue = '';
  });
}

function openScenarioLibrary() {
  renderScenarioLibraryAccess();
  openModal('modal-scenario-library', state.authSession.authenticated ? '#scenario-builder-title' : '#scenario-signin-btn');
}

function renderScenarioLibraryAccess() {
  const disabled = !state.authSession.authenticated || scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new?.busy;
  const pendingRename = pendingSymbolRename();
  const uncheckedText = scenarioLibrary.rawChanged || !!byId('scenario-glossary-text').value.trim();
  byId('scenario-signin-required').hidden = state.authSession.authenticated;
  byId('scenario-builder-fields').disabled = disabled;
  for (const id of ['scenario-file-input', 'scenario-load-files', 'scenario-preview-btn', 'scenario-starter-btn', 'scenario-reset-btn']) byId(id).disabled = disabled;
  for (const input of byId('scenario-import-files').querySelectorAll('select,button')) input.disabled = disabled;
  byId('scenario-mode-guided').disabled = disabled || pendingRename || !guidedEditorAvailable();
  byId('scenario-mode-text').disabled = disabled || pendingRename;
  byId('scenario-preview-btn').disabled = disabled || pendingRename;
  byId('scenario-library-submit').disabled = disabled || pendingRename || !scenarioLibrary.preview;
  byId('scenario-rename-from').disabled = disabled || uncheckedText;
  byId('scenario-rename-to').disabled = disabled || uncheckedText || !byId('scenario-rename-from').value;
  byId('scenario-rename-apply').disabled = disabled || uncheckedText || !pendingRename;
  byId('scenario-rename-cancel').disabled = disabled || !pendingRename;
  byId('scenario-rename-note').textContent = uncheckedText
    ? 'Preview changed rule text or Apply meanings from the pasted glossary before renaming.'
    : 'Renaming updates every logical reference, including negation and rule undercuts. Meanings and reference documents are preserved.';
  for (const id of ['scenario-rule-text', 'scenario-glossary-text', 'scenario-glossary-file', 'scenario-apply-glossary'])
    byId(id).disabled = disabled || pendingRename;
  byId('scenario-library-submit').textContent = scenarioLibrary.busy ? 'Saving...' : 'Save & open';
  byId('scenario-preview-btn').textContent = scenarioLibrary.reading ? 'Checking...' : 'Preview';
  byId('scenario-editor-heading').textContent = scenarioLibrary.target ? 'Edit private scenario' : 'Your scenario';
  byId('scenario-download-current').disabled = !state.bundle || hasPendingStateRequest();
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
}

async function switchScenarioMode(mode) {
  if (scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || mode === scenarioLibrary.mode) return;
  if (mode === 'guided' && scenarioLibrary.rawChanged && !await previewScenarioDraft(false)) return;
  if (mode === 'text') {
    const empty = scenarioLibrary.statements.every(item => !item.description.trim())
      && scenarioLibrary.rules.every(rule => !rule.conclusion && rule.premises.every(p => !p));
    if (empty) {
      const scenario = { ...scenarioLibrary.base, title: byId('scenario-builder-title').value,
        description: byId('scenario-builder-description').value, sources: structuredClone(librarySources.new.sources),
        facts: {}, assumptions: {}, propositions: {}, conclusions: {}, rules: {} };
      loadScenarioDraft(scenario, scenarioLibrary.sourceId, scenarioLibrary.target);
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
  scenarioLibrary.generation++; scenarioLibrary.reading = false; scenarioLibrary.preview = null;
  byId('scenario-editor-preview').hidden = true;
}

function loadScenarioDraft(scenario, sourceId = null, target = null) {
  scenarioLibrary.generation++;
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
  byId('scenario-rule-text').value = scenarioRuleText(scenario);
  byId('scenario-glossary-text').value = ''; byId('scenario-glossary-file').value = '';
  byId('scenario-symbol-renamer').open = false;
  byId('scenario-rename-from').replaceChildren(); byId('scenario-rename-to').value = '';
  byId('scenario-rename-to').removeAttribute('aria-invalid');
  byId('scenario-bundled-references').textContent = scenario.corpus?.length
    ? 'Included with this example: ' + scenario.corpus.join(', ') + '. Export embeds their content.' : '';
  librarySources.new.reset(scenario.sources || []);
  scenarioLibrary.preview = null; scenarioLibrary.rawChanged = false;
  byId('scenario-editor-preview').hidden = true;
  renderBuilderStatements(); renderBuilderRules();
}

function resetScenarioBuilder() {
  loadScenarioDraft({ title: '', facts: {}, conclusions: {}, rules: {} });
  scenarioLibrary.files = []; byId('scenario-import-files').replaceChildren();
  byId('scenario-file-input').value = ''; byId('scenario-load-files').hidden = true;
  setScenarioMode('guided');
  addBuilderStatement('fact', '', false); addBuilderStatement('conclusion', '', false); addBuilderRule(false);
  scenarioLibrary.dirty = false;
}

function nextScenarioId(prefix) {
  const ids = new Set([...scenarioLibrary.statements, ...scenarioLibrary.rules].map(item => item.id));
  let id;
  do { id = prefix + '_' + scenarioLibrary.nextId++; } while (ids.has(id));
  return id;
}

function addBuilderStatement(kind = 'fact', description = '', focus = true) {
  if (scenarioLibrary.statements.length >= 100) {
    setWorkspaceStatus('scenario-library-status', 'Use at most 100 statements in the guided editor.', 'info'); return;
  }
  scenarioLibrary.statements.push({ id: nextScenarioId('statement'), kind, description });
  renderBuilderStatements(); refreshBuilderChoices();
  if (focus) { scenarioDraftChanged(); byId('scenario-statements').lastElementChild.querySelector('input').focus(); }
}

function renderBuilderStatements() {
  const list = byId('scenario-statements'); list.replaceChildren();
  if (!guidedEditorAvailable()) {
    list.textContent = 'This knowledge base is too large for the guided editor. Use Rule text or edit its portable JSON file.';
    return;
  }
  scenarioLibrary.statements.forEach((item, index) => {
    const row = document.createElement('div'); row.className = 'scenario-statement-card'; row.dataset.statementId = item.id;
    row.innerHTML = '<div class="scenario-statement-row"><label class="visually-hidden">Statement kind</label><select aria-label="Statement ' + (index + 1) + ' kind">' +
      '<option value="fact">Fact</option><option value="assumption">Assumption</option><option value="proposition">Claim</option></select>' +
      '<input type="text" required maxlength="2000" aria-label="Statement ' + (index + 1) + '">' +
      '<button class="btn btn-small" type="button" aria-label="Remove statement ' + (index + 1) + '">×</button></div>' +
      '<label class="scenario-key"><input type="checkbox"> Key conclusion</label>' +
      '<details class="scenario-statement-details"><summary>Symbol & details</summary><div class="scenario-hint"></div>' +
      '<label>Meaning of its negation<input class="scenario-negation" maxlength="2000" placeholder="Optional explicit wording"></label>' +
      '<div class="scenario-assumption-settings"></div></details>';
    const input = row.querySelector('input[type=text]'), select = row.querySelector('select'), key = row.querySelector('input[type=checkbox]');
    input.id = item.id + '-text'; select.id = item.id + '-kind';
    input.value = item.description; input.placeholder = 'Write this statement in plain English';
    select.value = item.kind === 'conclusion' ? 'proposition' : item.kind;
    key.checked = item.kind === 'conclusion'; key.parentElement.hidden = !['conclusion', 'proposition'].includes(item.kind);
    row.querySelector('.scenario-hint').textContent = 'Symbol: ' + item.id + (item.category ? ' | Category: ' + item.category : '') + (item.source ? ' | Source: ' + item.source : '');
    row.querySelector('.scenario-hint').append(symbolRenameShortcut(item.id));
    const negation = row.querySelector('.scenario-negation'); negation.value = item.negated_description || '';
    negation.addEventListener('input', () => { item.negated_description = negation.value || undefined; refreshBuilderChoices(); });
    if (item.kind === 'assumption') addPreferenceControls(row.querySelector('.scenario-assumption-settings'), item);
    input.addEventListener('input', () => { item.description = input.value; refreshBuilderChoices(); });
    select.addEventListener('change', () => {
      item.kind = select.value;
      renderBuilderStatements(); scenarioDraftChanged();
    });
    key.addEventListener('change', () => { item.kind = key.checked ? 'conclusion' : 'proposition'; scenarioDraftChanged(); });
    row.querySelector('button').addEventListener('click', () => {
      scenarioLibrary.statements.splice(index, 1); renderBuilderStatements(); refreshBuilderChoices(); scenarioDraftChanged();
      byId('scenario-add-statement').focus();
    });
    list.append(row);
  });
  renderSymbolChoices();
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
  scenarioLibrary.rules.push({ id: nextScenarioId('rule'), premises: [''], conclusion: '', type: 'defeasible', block: 1, active: true });
  renderBuilderRules();
  if (focus) { scenarioDraftChanged(); byId('scenario-builder-rules').lastElementChild.querySelector('select').focus(); }
}

function builderChoice(select, selected) {
  select.replaceChildren(new Option('Choose a statement', ''));
  for (const item of scenarioLibrary.statements) {
    if (!item.description.trim()) continue;
    select.add(new Option(item.description, item.id));
    select.add(new Option(item.negated_description || 'Not: ' + item.description, '-' + item.id));
  }
  for (const item of scenarioLibrary.rules.filter(rule => rule.type === 'defeasible')) {
    select.add(new Option(item.negated_description || 'Undercut rule: ' + item.id, '-' + item.id));
    if (selected === item.id) select.add(new Option('Rule: ' + item.id, item.id));
  }
  if (selected && ![...select.options].some(option => option.value === selected))
    select.add(new Option('Statement removed or empty, choose again', selected));
  select.value = selected;
}

function refreshBuilderChoices() {
  for (const select of document.querySelectorAll('#scenario-builder-rules [data-literal]')) builderChoice(select, select.value);
  renderSymbolChoices();
}

function renderBuilderRules() {
  const list = byId('scenario-builder-rules'); list.replaceChildren();
  renderSymbolChoices();
  if (!guidedEditorAvailable()) return;
  scenarioLibrary.rules.forEach((rule, index) => {
    const card = document.createElement('fieldset'); card.className = 'scenario-rule-card';
    const legend = document.createElement('legend'); legend.textContent = 'Rule ' + (index + 1); card.append(legend);
    const choose = (label, value, setter) => {
      const field = document.createElement('label'); field.className = 'scenario-rule-field';
      const span = document.createElement('span'); span.textContent = label;
      const select = document.createElement('select'); select.dataset.literal = ''; select.required = true;
      builderChoice(select, value); select.addEventListener('change', () => { setter(select.value); scenarioDraftChanged(); });
      field.append(span, select); card.append(field); return field;
    };
    rule.premises.forEach((premise, position) => {
      choose(position ? 'And' : 'If', premise, value => { rule.premises[position] = value; });
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-small'; remove.textContent = 'Remove condition';
      remove.setAttribute('aria-label', 'Remove condition ' + (position + 1) + ' from rule ' + (index + 1));
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
    card.append(add, strength); choose('Conclude', rule.conclusion, value => { rule.conclusion = value; });
    const details = document.createElement('details'); details.className = 'scenario-rule-details';
    const summary = document.createElement('summary'); summary.textContent = 'Priority & details (' + rule.id + ')'; details.append(summary);
    details.append(symbolRenameShortcut(rule.id));
    if (rule.type === 'defeasible') addPreferenceControls(details, rule);
    if (rule.category || rule.source) {
      const note = document.createElement('p'); note.textContent = [rule.category, rule.source].filter(Boolean).join(' | '); details.append(note);
    }
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-small'; remove.textContent = 'Remove rule';
    remove.setAttribute('aria-label', 'Remove rule ' + (index + 1));
    remove.onclick = () => { scenarioLibrary.rules.splice(index, 1); renderBuilderRules(); scenarioDraftChanged(); byId('scenario-add-rule').focus(); };
    card.append(details, remove); list.append(card);
  });
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

function scenarioFromBuilder(validate = true) {
  const result = { ...structuredClone(scenarioLibrary.base), title: byId('scenario-builder-title').value.trim(),
    description: byId('scenario-builder-description').value, facts: {}, assumptions: {}, propositions: {}, conclusions: {}, rules: {} };
  if (validate && !result.title) throw new Error('Give your scenario a title.');
  for (const item of scenarioLibrary.statements) {
    if (validate && !item.description.trim()) throw new Error('Write a statement in each row, or remove the empty row.');
    const { id, kind, ...data } = item;
    if (kind !== 'fact' && kind !== 'assumption') delete data.source;
    if (kind !== 'assumption') { delete data.active; delete data.block; }
    result[STATEMENT_SECTIONS[kind]][id] = data;
  }
  const ids = new Set([...scenarioLibrary.statements, ...scenarioLibrary.rules].map(item => item.id));
  for (const [index, item] of scenarioLibrary.rules.entries()) {
    if (validate && ![...item.premises, item.conclusion].every(lit => ids.has(lit.replace(/^-/, ''))))
      throw new Error('Choose an existing statement for every condition and conclusion in rule ' + (index + 1) + '.');
    const { id, ...rule } = item;
    if (rule.type === 'strict') delete rule.active;
    result.rules[id] = structuredClone(rule);
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
  const generation = scenarioLibrary.generation, account = state.authSession.user?.id;
  let completionGeneration = generation;
  scenarioLibrary.reading = true; renderScenarioLibraryAccess();
  setWorkspaceStatus('scenario-library-status', 'Checking rules and computing the argumentation preview...', 'info');
  try {
    const scenario = scenarioFromBuilder(!scenarioLibrary.rawChanged);
    scenario.sources = librarySources.new.value();
    const result = await apiRequest('/api/projects/editor/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario, source_scenario_id: scenarioLibrary.sourceId,
        rules: scenarioLibrary.rawChanged ? byId('scenario-rule-text').value : null, glossary: byId('scenario-glossary-text').value }) });
    if (generation !== scenarioLibrary.generation || account !== state.authSession.user?.id) return null;
    loadScenarioDraft(result.scenario, result.source_scenario_id, scenarioLibrary.target);
    completionGeneration = scenarioLibrary.generation;
    scenarioLibrary.preview = showPreview ? result : null; scenarioLibrary.dirty = true;
    if (showPreview) renderScenarioPreview(result);
    setWorkspaceStatus('scenario-library-status', showPreview ? 'Preview ready. Save when the scenario looks right.' : 'The same draft is updated. Nothing has been saved yet.', 'success');
    return result;
  } catch (error) {
    if (generation === scenarioLibrary.generation) setWorkspaceStatus('scenario-library-status', error.message, 'error');
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
  const atoms = Object.assign({}, ...Object.values(STATEMENT_SECTIONS).map(section => scenario[section]));
  const words = literal => {
    const id = literal.replace(/^-/, ''), item = atoms[id] || scenario.rules[id];
    return literal.startsWith('-') ? item?.negated_description || 'Not: ' + (item?.description || id) : item?.description || id;
  };
  const conclusions = Object.entries(scenario.conclusions || {});
  const heading = document.createElement('h4'); heading.textContent = 'Key conclusions'; host.append(heading);
  if (!conclusions.length) { const note = document.createElement('p'); note.textContent = 'No key conclusions selected. All statements remain available in the explorer.'; host.append(note); }
  for (const [id, item] of conclusions) {
    const row = document.createElement('p'); row.className = 'scenario-preview-claim';
    const label = document.createElement('span'); label.className = 'scenario-preview-label';
    label.textContent = result.af.labels_by_proposition[id] || 'unsupported';
    row.append(document.createTextNode(item.description), label); host.append(row);
  }
  const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Review rules in plain language'; details.append(summary);
  const list = document.createElement('ol');
  for (const rule of Object.values(scenario.rules || {})) {
    const item = document.createElement('li');
    item.textContent = (rule.active === false ? 'Suspended. ' : '') + (rule.premises.length ? 'If ' + rule.premises.map(words).join(' and ') + ', ' : '') +
      (rule.type === 'strict' ? 'then ' : 'usually ') + words(rule.conclusion) + (rule.type === 'strict' ? '.' : '. Priority ' + (rule.block ?? 1) + '.');
    list.append(item);
  }
  details.append(list); host.append(details);
  const sources = document.createElement('p'); sources.className = 'scenario-hint';
  sources.textContent = 'Reference documents: ' + [...(scenario.corpus || []), ...(scenario.sources || []).map(source => source.filename)].join(', ');
  host.append(sources);
  byId('scenario-file-warnings').textContent = result.warnings.join('\n');
  byId('scenario-editor-preview').hidden = false;
  byId('scenario-editor-preview').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function queueScenarioFiles(files) {
  if (scenarioLibrary.busy || scenarioLibrary.reading || !state.authSession.authenticated) return;
  if (!files.length) return;
  if (files.length > 22 || files.some(file => file.size > SCENARIO_FILE_LIMIT)) {
    setWorkspaceStatus('scenario-library-status', 'Choose up to 22 files, each at most 1 MB.', 'error'); return;
  }
  scenarioLibrary.files = files.map(file => ({ file, role: /\.aspic$/i.test(file.name) ? 'rules'
    : /glossary/i.test(file.name) ? 'glossary' : /\.(json|ya?ml)$/i.test(file.name) ? 'scenario'
    : /\.(pdf|md)$/i.test(file.name) ? 'source' : '' }));
  const host = byId('scenario-import-files'); host.replaceChildren();
  scenarioLibrary.files.forEach((entry, index) => {
    const label = document.createElement('label'); label.className = 'scenario-import-row';
    const name = document.createElement('span'); name.textContent = entry.file.name;
    const select = document.createElement('select'); select.setAttribute('aria-label', 'File role: ' + entry.file.name);
    for (const [value, text] of [['', 'Choose file role'], ['scenario', 'Complete scenario'], ['rules', 'ASPIC- rules'], ['glossary', 'Glossary'], ['source', 'Reference document']])
      select.add(new Option(text, value));
    select.value = entry.role; select.onchange = () => { scenarioLibrary.files[index].role = select.value; };
    label.append(name, select); host.append(label);
  });
  byId('scenario-load-files').hidden = false;
  setWorkspaceStatus('scenario-library-status', 'Check file roles, then load them into the common editor. Your draft is unchanged until all files pass.', 'info');
}

async function loadScenarioFiles() {
  if (scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || !state.authSession.authenticated) return;
  const entries = scenarioLibrary.files;
  if (!entries.length || entries.some(entry => !entry.role)) { setWorkspaceStatus('scenario-library-status', 'Choose a role for every file.', 'error'); return; }
  const byRole = role => entries.filter(entry => entry.role === role);
  if (byRole('scenario').length + byRole('rules').length > 1 || byRole('glossary').length > 1) {
    setWorkspaceStatus('scenario-library-status', 'Choose one knowledge base (complete scenario or rule text), and at most one glossary.', 'error'); return;
  }
  if ((byRole('scenario').length || byRole('rules').length) && scenarioLibrary.dirty
      && !window.confirm('Replace the current draft with these files? Nothing is saved until Save & open.')) return;
  const generation = scenarioLibrary.generation, account = state.authSession.user?.id;
  let completionGeneration = generation;
  scenarioLibrary.reading = true; renderScenarioLibraryAccess();
  try {
    let candidate = scenarioFromBuilder(false), sourceId = scenarioLibrary.sourceId, glossary = '', rawRules = null;
    const warnings = [];
    if (byRole('scenario').length) {
      const text = await readMaterialText(byRole('scenario')[0].file, SCENARIO_FILE_LIMIT);
      const result = await apiRequest('/api/projects/import/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
      candidate = result.scenario; sourceId = result.source_scenario_id; warnings.push(...result.warnings);
    } else if (byRole('rules').length) {
      const file = byRole('rules')[0].file;
      rawRules = await readMaterialText(file, 100000);
      candidate = { title: file.name.replace(/\.[^.]+$/, '').slice(0, 120), facts: {}, rules: {} }; sourceId = null;
    } else candidate.sources = librarySources.new.value();
    if (byRole('glossary').length) glossary = await readMaterialText(byRole('glossary')[0].file, 200000);
    candidate.sources = [...(candidate.sources || [])];
    for (const entry of byRole('source')) {
      const result = await previewSourceUpload(entry.file);
      candidate.sources.push(result.source); warnings.push(...result.warnings);
      if (generation !== scenarioLibrary.generation || account !== state.authSession.user?.id) return;
    }
    const result = await apiRequest('/api/projects/editor/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: candidate, source_scenario_id: sourceId, rules: rawRules, glossary }) });
    if (generation !== scenarioLibrary.generation || account !== state.authSession.user?.id) return;
    loadScenarioDraft(result.scenario, sourceId, null); setScenarioMode('guided'); scenarioLibrary.dirty = true;
    completionGeneration = scenarioLibrary.generation;
    scenarioLibrary.files = []; byId('scenario-import-files').replaceChildren(); byId('scenario-load-files').hidden = true; byId('scenario-file-input').value = '';
    setWorkspaceStatus('scenario-library-status', 'Materials loaded together. Review the editor, then Preview and Save & open. ' + [...warnings, ...result.warnings].join(' '), 'success');
  } catch (error) {
    if (generation === scenarioLibrary.generation) setWorkspaceStatus('scenario-library-status', error.message + ' Your previous draft is unchanged.', 'error');
  } finally { if (completionGeneration === scenarioLibrary.generation && account === state.authSession.user?.id) { scenarioLibrary.reading = false; renderScenarioLibraryAccess(); } }
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
  if (!scenarioLibrary.preview || scenarioLibrary.busy || scenarioLibrary.reading || librarySources.new.busy || !state.authSession.authenticated || pendingSymbolRename()) return;
  if (hasPendingStateRequest() || state.projectSavePending) { setWorkspaceStatus('scenario-library-status', 'Wait for the current change or save to finish.', 'info'); return; }
  const target = scenarioLibrary.target, scenario = scenarioLibrary.preview.scenario;
  if (!target && hasUnsavedChanges() && !window.confirm('Open the new project and discard unsaved edits in the current view? Download or save them first if you want to keep them.')) return;
  const previousBundle = state.bundle, previousOps = state.diff_ops, previousProject = state.activeProject;
  const previousUser = state.authSession.user?.id, previousRequest = currentRequest, generation = scenarioLibrary.generation;
  if (target && (state.activeProject !== target || state.bundle !== scenarioLibrary.targetBundle)) { setWorkspaceStatus('scenario-library-status', 'The project changed elsewhere. Reopen its editor before saving. Your draft is preserved.', 'error'); return; }
  scenarioLibrary.busy = true; renderScenarioLibraryAccess();
  try {
    const project = await apiRequest(target ? '/api/projects/' + encodeURIComponent(target.id) : '/api/projects/import', {
      method: target ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(target ? { expected_version: target.version, name: scenario.title, description: scenario.description.slice(0, 4000), scenario }
        : { name: scenario.title, description: scenario.description.slice(0, 4000), source_scenario_id: scenarioLibrary.sourceId, scenario }),
    });
    if (state.authSession.user?.id !== previousUser || generation !== scenarioLibrary.generation) return;
    resetScenarioBuilder();
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
    setWorkspaceStatus('scenario-library-status', error.code === 'project_version_conflict'
      ? 'This project changed elsewhere. Your draft has not replaced newer work. Reopen the project before saving.' : error.message, 'error');
  } finally { scenarioLibrary.busy = false; renderScenarioLibraryAccess(); }
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
  if (!state.bundle || hasPendingStateRequest()) {
    setWorkspaceStatus('scenario-library-status', 'Wait for the current scenario to finish loading.', 'info');
    return;
  }
  const example = state.scenarios.find(item => item.id === state.scenario_id);
  const exampleSource = example?.category === 'community' ? example.source_scenario_id : state.scenario_id;
  const sourceId = state.activeProject?.source_scenario_id || state.sharedProject?.source_scenario_id
    || (state.viewKind === 'example' ? exampleSource : null);
  const scenario = structuredClone(state.bundle.scenario);
  const account = state.authSession.user?.id;
  setWorkspaceStatus('scenario-library-status', 'Preparing a self-contained file with complete reference text...', 'info');
  try {
    await downloadScenarioFile(scenario, sourceId);
    if (account === state.authSession.user?.id) setWorkspaceStatus('scenario-library-status', 'Downloaded all rules, meanings and reference text. Import scenario can reopen this file without the original server. PDFs use extracted text, not the original page layout.', 'success');
  } catch (error) { if (account === state.authSession.user?.id) setWorkspaceStatus('scenario-library-status', error.message, 'error'); }
}
