/* New scenarios, validated file import, and portable, credential-free exports. */

const scenarioLibrary = {
  tab: 'new', statements: [], rules: [], nextId: 1,
  preview: null, fileGeneration: 0, fileController: null,
  busy: false, reading: false, dirty: false,
};
const SCENARIO_FILE_LIMIT = 1000000;

function initScenarioLibrary() {
  initCurationUI();
  initScenarioMaterials();
  byId('scenario-library-btn').addEventListener('click', openScenarioLibrary);
  byId('scenario-library-cancel').addEventListener('click', () => requestCloseModal('modal-scenario-library'));
  byId('scenario-my-projects').addEventListener('click', () => {
    requestCloseModal('modal-scenario-library');
    openWorkspace('projects');
  });
  byId('scenario-signin-btn').addEventListener('click', () => {
    requestCloseModal('modal-scenario-library');
    openWorkspace('account');
  });
  for (const tab of document.querySelectorAll('[data-scenario-tab]')) {
    tab.addEventListener('click', () => switchScenarioLibraryTab(tab.dataset.scenarioTab));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const tabs = ['new', 'file', 'aspic'];
      const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[2]
        : tabs[(tabs.indexOf(scenarioLibrary.tab) + (event.key === 'ArrowLeft' ? 2 : 1)) % 3];
      switchScenarioLibraryTab(next);
      byId(`scenario-tab-${next}`).focus();
    });
  }
  byId('scenario-add-statement').addEventListener('click', () => addBuilderStatement());
  byId('scenario-add-rule').addEventListener('click', () => addBuilderRule());
  byId('scenario-starter-btn').addEventListener('click', useScenarioStarter);
  byId('scenario-builder-form').addEventListener('submit', event => {
    event.preventDefault();
    submitScenarioLibrary();
  });
  byId('scenario-builder-form').addEventListener('input', () => { scenarioLibrary.dirty = true; });
  byId('scenario-library-submit').addEventListener('click', submitScenarioLibrary);
  byId('scenario-file-input').addEventListener('change', event => previewScenarioFile(event.target.files[0]));
  const dropZone = byId('scenario-drop-zone');
  dropZone.addEventListener('dragover', event => {
    event.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', event => {
    event.preventDefault();
    dropZone.classList.remove('drag-over');
    if (event.dataTransfer.files.length !== 1) {
      clearScenarioPreview();
      setWorkspaceStatus('scenario-library-status', 'Choose one scenario file at a time.', 'error');
      return;
    }
    previewScenarioFile(event.dataTransfer.files[0]);
  });
  byId('scenario-download-current').addEventListener('click', downloadCurrentScenario);
  byId('scenario-template-btn').addEventListener('click', () => {
    downloadScenarioFile(scenarioStarter(), null);
  });
  resetScenarioBuilder();
  window.addEventListener('beforeunload', event => {
    if (!scenarioLibrary.dirty || !state.authSession.authenticated) return;
    event.preventDefault();
    event.returnValue = '';
  });
}

function openScenarioLibrary() {
  renderScenarioLibraryAccess();
  openModal('modal-scenario-library', state.authSession.authenticated
    ? { new: '#scenario-builder-title', file: '#scenario-file-input', aspic: '#aspic-import-title' }[scenarioLibrary.tab]
    : '#scenario-signin-btn');
}

function renderScenarioLibraryAccess() {
  const authenticated = state.authSession.authenticated;
  byId('scenario-signin-required').hidden = authenticated;
  byId('scenario-builder-fields').disabled = !authenticated || scenarioLibrary.busy;
  byId('scenario-file-input').disabled = !authenticated || scenarioLibrary.busy;
  byId('scenario-import-name').disabled = !authenticated || scenarioLibrary.busy;
  byId('scenario-aspic-fields').disabled = !authenticated || scenarioLibrary.busy || scenarioLibrary.reading;
  const submit = byId('scenario-library-submit');
  submit.disabled = !authenticated || scenarioLibrary.busy || scenarioLibrary.reading || librarySources[scenarioLibrary.tab]?.busy
    || (scenarioLibrary.tab === 'file' && !scenarioLibrary.preview);
  submit.textContent = scenarioLibrary.busy ? 'Opening...'
    : scenarioLibrary.tab === 'new' ? 'Create & open'
    : scenarioLibrary.tab === 'aspic' && !aspicPreview ? 'Check & preview' : 'Import & open';
  byId('scenario-download-current').disabled = !state.bundle || hasPendingStateRequest();
  renderMaterialAccess();
}

function switchScenarioLibraryTab(tab) {
  if (scenarioLibrary.busy || scenarioLibrary.reading) return;
  scenarioLibrary.tab = tab;
  for (const name of ['new', 'file', 'aspic']) {
    const active = name === tab;
    const button = byId(`scenario-tab-${name}`);
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
    byId(`scenario-panel-${name}`).hidden = !active;
    librarySources[name].host.hidden = !active;
  }
  setWorkspaceStatus('scenario-library-status');
  renderScenarioLibraryAccess();
}

function resetScenarioBuilder() {
  scenarioLibrary.statements = [];
  scenarioLibrary.rules = [];
  scenarioLibrary.nextId = 1;
  byId('scenario-builder-form').reset();
  byId('scenario-statements').replaceChildren();
  addBuilderStatement('fact', '', false);
  addBuilderStatement('conclusion', '', false);
  addBuilderRule(false);
  scenarioLibrary.dirty = false;
}

function addBuilderStatement(kind = 'fact', description = '', focus = true) {
  if (scenarioLibrary.statements.length >= 100) {
    setWorkspaceStatus('scenario-library-status', 'For more than 100 statements, use a scenario file.', 'info');
    return;
  }
  const statement = { id: `statement_${scenarioLibrary.nextId++}`, kind, description };
  scenarioLibrary.statements.push(statement);
  const row = document.createElement('div');
  row.className = 'scenario-statement-row';
  row.dataset.statementId = statement.id;
  const number = scenarioLibrary.nextId - 1;
  row.innerHTML = `
    <label class="visually-hidden" for="${statement.id}-kind">Statement ${number} kind</label>
    <select id="${statement.id}-kind">
      <option value="fact">Fact</option><option value="assumption">Assumption</option><option value="conclusion">Conclusion</option>
    </select>
    <label class="visually-hidden" for="${statement.id}-text">Statement ${number}</label>
    <input id="${statement.id}-text" type="text" required maxlength="2000">
    <button class="btn btn-small" type="button" aria-label="Remove statement ${number}">×</button>`;
  const input = row.querySelector('input');
  const select = row.querySelector('select');
  input.value = description;
  input.placeholder = kind === 'conclusion' ? 'A claim to test, e.g. we should hold the picnic outside' : 'A statement, e.g. the forecast is sunny';
  select.value = kind;
  input.addEventListener('input', () => {
    statement.description = input.value;
    refreshBuilderChoices();
  });
  select.addEventListener('change', () => { statement.kind = select.value; });
  row.querySelector('button').addEventListener('click', () => {
    scenarioLibrary.statements = scenarioLibrary.statements.filter(item => item !== statement);
    scenarioLibrary.dirty = true;
    row.remove();
    refreshBuilderChoices();
    byId('scenario-add-statement').focus();
  });
  byId('scenario-statements').append(row);
  refreshBuilderChoices();
  if (focus) { scenarioLibrary.dirty = true; input.focus(); }
}

function addBuilderRule(focus = true) {
  if (scenarioLibrary.rules.length >= 50) {
    setWorkspaceStatus('scenario-library-status', 'For more than 50 rules, use a scenario file.', 'info');
    return;
  }
  scenarioLibrary.rules.push({ premises: [''], conclusion: '', type: 'defeasible' });
  renderBuilderRules();
  if (focus) {
    scenarioLibrary.dirty = true;
    byId('scenario-builder-rules').lastElementChild?.querySelector('select')?.focus();
  }
}

function builderChoice(select, selected) {
  select.replaceChildren(new Option('Choose a statement', ''));
  for (const item of scenarioLibrary.statements) {
    const label = item.description.trim();
    if (!label) continue;
    select.add(new Option(label, item.id));
    select.add(new Option(`Not: ${label}`, `-${item.id}`));
  }
  if (selected && ![...select.options].some(option => option.value === selected)) {
    select.add(new Option('Statement removed or empty, choose again', selected));
  }
  select.value = selected;
}

function refreshBuilderChoices() {
  for (const select of document.querySelectorAll('#scenario-builder-rules [data-literal]')) {
    builderChoice(select, select.value);
  }
}

function renderBuilderRules() {
  const list = byId('scenario-builder-rules');
  list.replaceChildren();
  for (const [index, rule] of scenarioLibrary.rules.entries()) {
    const card = document.createElement('fieldset');
    card.className = 'scenario-rule-card';
    card.innerHTML = `<legend>Rule ${index + 1}</legend>`;
    const choose = (label, value, setter) => {
      const field = document.createElement('label');
      field.className = 'scenario-rule-field';
      const text = document.createElement('span');
      text.textContent = label;
      const select = document.createElement('select');
      select.required = true;
      select.dataset.literal = '';
      builderChoice(select, value);
      select.addEventListener('change', () => { setter(select.value); scenarioLibrary.dirty = true; });
      field.append(text, select);
      card.append(field);
      return field;
    };
    rule.premises.forEach((premise, position) => {
      const field = choose(position ? 'And' : 'If', premise, value => { rule.premises[position] = value; });
      if (rule.premises.length > 1) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-small';
        remove.textContent = '×';
        remove.setAttribute('aria-label', `Remove condition ${position + 1} from rule ${index + 1}`);
        remove.addEventListener('click', () => {
          rule.premises.splice(position, 1); scenarioLibrary.dirty = true; renderBuilderRules();
          list.children[index].querySelector('select').focus();
        });
        // Keep the button outside the label, so it does not activate a select.
        field.insertAdjacentElement('afterend', remove);
      }
    });
    const condition = document.createElement('button');
    condition.type = 'button';
    condition.className = 'btn btn-small scenario-add-condition';
    condition.textContent = '+ Condition';
    condition.disabled = rule.premises.length >= 50;
    condition.addEventListener('click', () => {
      rule.premises.push(''); scenarioLibrary.dirty = true; renderBuilderRules();
      list.children[index].querySelectorAll('[data-literal]')[rule.premises.length - 1].focus();
    });
    card.append(condition);
    const strength = document.createElement('label');
    strength.className = 'scenario-rule-field';
    strength.innerHTML = '<span>Then</span><select aria-label="Rule strength"><option value="defeasible">Usually (defeasible)</option><option value="strict">Always (strict)</option></select>';
    const select = strength.querySelector('select');
    select.value = rule.type;
    select.addEventListener('change', () => { rule.type = select.value; scenarioLibrary.dirty = true; });
    card.append(strength);
    choose('Conclude', rule.conclusion, value => { rule.conclusion = value; });
    const remove = document.createElement('button');
    remove.type = 'button'; remove.className = 'btn btn-small'; remove.textContent = 'Remove rule';
    remove.setAttribute('aria-label', `Remove rule ${index + 1}`);
    remove.addEventListener('click', () => {
      scenarioLibrary.rules.splice(index, 1); scenarioLibrary.dirty = true; renderBuilderRules();
      byId('scenario-add-rule').focus();
    });
    card.append(remove);
    list.append(card);
  }
}

function scenarioStarter() {
  return {
    title: 'Planning a picnic', description: 'Compare two reasons for and against an outdoor picnic.',
    facts: { sunny: { description: 'The forecast is sunny' }, windy: { description: 'A strong wind is expected' } },
    conclusions: { outside: { description: 'We should hold the picnic outside' } },
    rules: {
      sunshine: { type: 'defeasible', premises: ['sunny'], conclusion: 'outside' },
      wind: { type: 'defeasible', premises: ['windy'], conclusion: '-outside' },
    },
  };
}

function useScenarioStarter() {
  if (scenarioLibrary.dirty && !window.confirm('Replace the unfinished builder draft with the small example?')) return;
  const starter = scenarioStarter();
  scenarioLibrary.statements = [];
  scenarioLibrary.rules = [];
  byId('scenario-statements').replaceChildren();
  byId('scenario-builder-title').value = starter.title;
  byId('scenario-builder-description').value = starter.description;
  for (const entry of Object.values(starter.facts)) addBuilderStatement('fact', entry.description, false);
  addBuilderStatement('conclusion', starter.conclusions.outside.description, false);
  const [sun, wind, outside] = scenarioLibrary.statements.map(item => item.id);
  scenarioLibrary.rules = [
    { premises: [sun], conclusion: outside, type: 'defeasible' },
    { premises: [wind], conclusion: `-${outside}`, type: 'defeasible' },
  ];
  renderBuilderRules();
  scenarioLibrary.dirty = true;
  setWorkspaceStatus('scenario-library-status', 'A small starting point. Change any statement or rule to make it yours.', 'info');
  byId('scenario-builder-title').focus();
}

function scenarioFromBuilder() {
  const result = {
    title: byId('scenario-builder-title').value.trim(),
    description: byId('scenario-builder-description').value.trim(),
    facts: {}, assumptions: {}, conclusions: {}, rules: {},
  };
  if (!result.title) throw new Error('Give your scenario a title.');
  const ids = new Set();
  for (const item of scenarioLibrary.statements) {
    const description = item.description.trim();
    if (!description) throw new Error('Write a statement in each row, or remove the empty row.');
    ids.add(item.id);
    const section = { fact: 'facts', assumption: 'assumptions', conclusion: 'conclusions' }[item.kind];
    result[section][item.id] = { description };
  }
  if (!Object.keys(result.conclusions).length) throw new Error('Add at least one Conclusion to explore.');
  if (!scenarioLibrary.rules.length) throw new Error('Add a rule to connect your statements.');
  scenarioLibrary.rules.forEach((rule, index) => {
    if (![...rule.premises, rule.conclusion].every(literal => ids.has(literal.replace(/^-/, '')))) {
      throw new Error(`Choose an existing statement for every condition and conclusion in rule ${index + 1}.`);
    }
    result.rules[`rule_${index + 1}`] = { ...rule, premises: [...new Set(rule.premises)] };
  });
  return result;
}

function clearScenarioPreview() {
  scenarioLibrary.fileController?.abort();
  scenarioLibrary.fileController = null;
  scenarioLibrary.fileGeneration += 1;
  scenarioLibrary.preview = null;
  librarySources.file?.reset();
  scenarioLibrary.reading = false;
  byId('scenario-file-preview').hidden = true;
  renderScenarioLibraryAccess();
}

async function previewScenarioFile(file) {
  if (scenarioLibrary.busy) return;
  clearScenarioPreview();
  if (!file) return;
  if (!state.authSession.authenticated) {
    setWorkspaceStatus('scenario-library-status', 'Sign in before opening a private scenario file.', 'info');
    return;
  }
  const generation = scenarioLibrary.fileGeneration;
  const controller = new AbortController();
  scenarioLibrary.fileController = controller;
  setWorkspaceStatus('scenario-library-status', 'Checking the file and its argumentation structure...', 'info');
  scenarioLibrary.reading = true;
  renderScenarioLibraryAccess();
  try {
    if (!/\.(yaml|yml|json)$/i.test(file.name)) throw new Error('Choose an ABDA-NL .yaml, .yml, or .json file.');
    if (file.size > SCENARIO_FILE_LIMIT) throw new Error('Choose a scenario file smaller than 1 MB.');
    const buffer = await file.arrayBuffer();
    if (generation !== scenarioLibrary.fileGeneration) return;
    let text;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
    catch (_error) { throw new Error('Save the file as UTF-8 text, then try again.'); }
    const preview = await apiRequest('/api/projects/import/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }), signal: controller.signal,
    });
    if (generation !== scenarioLibrary.fileGeneration) return;
    scenarioLibrary.preview = preview;
    const scenario = preview.scenario;
    librarySources.file.reset(scenario.sources || []);
    if (scenario.sources?.length) byId('scenario-sources-panel').open = true;
    byId('scenario-import-name').value = scenario.title.slice(0, 120);
    byId('scenario-file-name').textContent = file.name;
    byId('scenario-file-description').textContent = scenario.description || '';
    byId('scenario-file-counts').replaceChildren();
    for (const section of ['facts', 'assumptions', 'conclusions', 'rules']) {
      const count = document.createElement('span');
      const total = Object.keys(scenario[section] || {}).length;
      count.textContent = `${total} ${total === 1 ? section.slice(0, -1) : section}`;
      byId('scenario-file-counts').append(count);
    }
    const warnings = [...preview.warnings];
    if (!Object.keys(scenario.conclusions).length) warnings.push('No key conclusions are defined. Use the All filter after opening to explore propositions.');
    byId('scenario-file-warnings').textContent = warnings.join('\n');
    byId('scenario-file-preview').hidden = false;
    setWorkspaceStatus('scenario-library-status', 'Validated. Ready to open as a new private project.', 'success');
  } catch (error) {
    if (generation !== scenarioLibrary.fileGeneration || isAbortError(error)) return;
    setWorkspaceStatus('scenario-library-status', error.message, 'error');
  } finally {
    if (generation === scenarioLibrary.fileGeneration) {
      scenarioLibrary.reading = false;
      renderScenarioLibraryAccess();
    }
  }
}

async function submitScenarioLibrary() {
  if (scenarioLibrary.busy || scenarioLibrary.reading || !state.authSession.authenticated) return;
  if (hasPendingStateRequest() || state.projectSavePending) {
    setWorkspaceStatus('scenario-library-status', 'Wait for the current change or save to finish.', 'info');
    return;
  }
  const tab = scenarioLibrary.tab;
  let scenario, sourceId, name;
  try {
    if (tab === 'new') {
      if (!byId('scenario-builder-form').reportValidity()) return;
      scenario = scenarioFromBuilder(); sourceId = null; name = scenario.title;
    } else if (tab === 'aspic') {
      if (!aspicPreview) { await previewAspic(); return; }
      const preview = aspicPreview;
      scenario = preview.scenario; sourceId = null; name = scenario.title;
    } else {
      if (!scenarioLibrary.preview || !byId('scenario-import-name').reportValidity()) return;
      scenario = scenarioLibrary.preview.scenario;
      sourceId = scenarioLibrary.preview.source_scenario_id;
      name = byId('scenario-import-name').value.trim();
      if (!name) throw new Error('Give the imported scenario a name.');
    }
    scenario = { ...scenario, sources: librarySources[tab].value() };
  } catch (error) {
    setWorkspaceStatus('scenario-library-status', error.message, 'error');
    return;
  }
  if (hasUnsavedChanges() && !window.confirm('Open the new project and discard unsaved edits in the current view? Download or save them first if you want to keep them.')) return;
  const previousBundle = state.bundle;
  const previousOps = state.diff_ops;
  const previousProject = state.activeProject;
  const previousUser = state.authSession.user?.id;
  const previousRequest = currentRequest;
  scenarioLibrary.busy = true;
  renderScenarioLibraryAccess();
  setWorkspaceStatus('scenario-library-status', 'Validating and creating your private project...', 'info');
  try {
    const project = await apiRequest('/api/projects/import', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: scenario.description.slice(0, 4000), source_scenario_id: sourceId, scenario }),
    });
    if (state.authSession.user?.id !== previousUser) return;
    if (tab === 'new') resetScenarioBuilder();
    else if (tab === 'file') { clearScenarioPreview(); byId('scenario-file-input').value = ''; }
    else {
      for (const input of byId('scenario-aspic-fields').querySelectorAll('input,textarea')) input.value = '';
      invalidateAspic();
    }
    librarySources[tab].reset(); scenarioLibrary.dirty = false;
    const changed = state.bundle !== previousBundle || state.diff_ops !== previousOps
      || state.activeProject !== previousProject || currentRequest !== previousRequest;
    if (!changed) {
      setViewContext('project', project);
      state.scenario_id = project.source_scenario_id;
      state.baseline = project.scenario;
      state.diff_ops = [];
      setBundle({ scenario: project.scenario, af: project.af });
      resetChatConversation(); resetViewFilters(); indexBundle(); populateScenarioSelect(); renderAll();
      // A private copy opened from a shared view must not reload the old share.
      if (new URLSearchParams(window.location.hash.slice(1)).has('share')) {
        window.history.replaceState({}, '', window.location.pathname + window.location.search);
      }
      requestCloseModal('modal-scenario-library');
    }
    await refreshProjects({ quiet: true });
    showGlobalStatus(changed ? `Created "${project.name}". Open it from My projects when ready.`
      : `Opened "${project.name}". Saved privately, ready to explore.`, 'success');
    setWorkspaceStatus('scenario-library-status');
  } catch (error) {
    setWorkspaceStatus('scenario-library-status', error.message, 'error');
  } finally {
    scenarioLibrary.busy = false;
    renderScenarioLibraryAccess();
  }
}

function downloadScenarioFile(scenario, sourceId) {
  const payload = { format: 'abda-nl-scenario', version: scenario.sources?.length ? 2 : 1, source_scenario_id: sourceId || null, scenario };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  const slug = (scenario.title || 'scenario').normalize('NFKD').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70);
  link.download = `${slug || 'scenario'}.abda.json`;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadCurrentScenario() {
  if (!state.bundle || hasPendingStateRequest()) {
    setWorkspaceStatus('scenario-library-status', 'Wait for the current scenario to finish loading.', 'info');
    return;
  }
  const example = state.scenarios.find(item => item.id === state.scenario_id);
  const exampleSource = example?.category === 'community' ? example.source_scenario_id : state.scenario_id;
  const sourceId = state.activeProject?.source_scenario_id || state.sharedProject?.source_scenario_id
    || (state.viewKind === 'example' ? exampleSource : null);
  downloadScenarioFile(state.bundle.scenario, sourceId);
  setWorkspaceStatus('scenario-library-status', 'Downloaded the current scenario, including unsaved edits. Reopen it with Open file.', 'success');
}
