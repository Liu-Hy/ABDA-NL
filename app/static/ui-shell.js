/* Scenario navigation and display preferences. No model requests originate here. */
let activeShellPopup = null;
let shellTypeahead = '';
let shellTypeaheadTimer = null;
let resetUndo = null;
let aboutScope = null;
let shellAccountScope = null;

function shellModalOpener() {
  const focused = document.activeElement;
  if (activeShellPopup?.panel.contains(focused)) return activeShellPopup.trigger;
  const popup = focused?.closest('.shell-popover');
  if (popup) return document.querySelector(`[aria-controls="${CSS.escape(popup.id)}"]`) || focused;
  const menu = focused?.closest('details');
  return menu && !focused.matches('summary') ? menu.querySelector('summary') : focused;
}

function appendScenarioSuggestions(container) {
  if (!state.bundle) return;
  const bundle = state.bundle;
  const scenario = bundle.scenario;
  const actions = document.createElement('div');
  actions.className = 'scenario-suggestions';
  const add = (label, action) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn btn-small'; button.textContent = label;
    button.addEventListener('click', () => { if (state.bundle === bundle) action(); });
    actions.append(button);
  };
  const accepted = Object.keys(scenario.conclusions || {}).find(id =>
    bundle.af.labels_by_proposition?.[id] === 'accepted' && getCandidateRootArguments(id).length);
  if (accepted) add(`Explain: ${scenario.conclusions[accepted].description}`, () => openExplainModal(accepted));
  const inactive = Object.entries(scenario.assumptions || {}).find(([, entry]) => entry.active === false);
  if (inactive && !state.readOnly) add(`Preview activating: ${inactive[1].description}`, () => previewAndConfirmToggle(
    { op: 'toggle-assumption', id: inactive[0] },
    { title: 'Activate this assumption?', summary: `Activate: ${escapeHtml(inactive[1].description)}` },
  ));
  if (scenario.corpus?.length || scenario.sources?.length) add('Ask about source documents', () => {
    chatComposer.insertText('What do the source documents say about this scenario?');
    revealChatForNarrowLayout(); chatComposer.focus();
  });
  if (actions.childElementCount) container.append(actions);
}

function resetScope() {
  return JSON.stringify([state.authSession.user?.id || null, state.viewKind,
    state.activeProject?.id || state.sharedProject?.id || state.scenario_id,
    state.activeProject?.version || state.sharedProject?.version || null]);
}

function validResetUndo() {
  if (resetUndo && (resetUndo.scope !== resetScope() || resetUndo.baseline !== state.baseline
      || resetUndo.bundle !== state.bundle || state.diff_ops.length || state.readOnly)) resetUndo = null;
  return resetUndo;
}

async function undoBaselineReset() {
  const checkpoint = validResetUndo();
  if (!checkpoint || hasPendingStateRequest() || blockStateMutationDuringSave()) return;
  const ctrl = beginRequest();
  try {
    const bundle = await apiPostState(state.scenario_id, checkpoint.operations, ctrl.signal);
    if (!isCurrent(ctrl) || checkpoint !== validResetUndo()) return;
    state.diff_ops = structuredClone(checkpoint.operations);
    resetUndo = null;
    setBundle(bundle, { pulseLabels: true });
    indexBundle();
    renderAll();
    showGlobalStatus('Your changes have been restored.', 'success');
  } catch (error) {
    if (!isAbortError(error) && isCurrent(ctrl)) showGlobalStatus(error.message, 'error');
  } finally { finishRequest(ctrl); }
}

function closeShellPopup(restoreFocus = true) {
  if (!activeShellPopup) return;
  const { panel, trigger } = activeShellPopup;
  panel.hidden = true;
  trigger.setAttribute('aria-expanded', 'false');
  activeShellPopup = null;
  if (restoreFocus && trigger.isConnected) trigger.focus();
}

function openShellPopup(trigger, panel) {
  if (activeShellPopup?.panel === panel) { closeShellPopup(); return; }
  closeShellPopup(false);
  if (panel.id === 'scenario-popover') renderScenarioChoices();
  else renderShellMenus();
  panel.hidden = false;
  trigger.setAttribute('aria-expanded', 'true');
  activeShellPopup = { panel, trigger };
  const first = panel.querySelector('[role="option"][aria-selected="true"]')
    || panel.querySelector('[role="option"], [role^="menuitem"]:not(:disabled), button:not(:disabled)');
  first?.focus();
}

function shellMenuItem(label, action, options = {}) {
  const button = document.createElement('button');
  button.type = 'button';
  button.setAttribute('role', options.checked === undefined ? 'menuitem' : 'menuitemradio');
  if (options.checked !== undefined) button.setAttribute('aria-checked', String(options.checked));
  button.textContent = label;
  button.disabled = Boolean(options.disabled);
  button.addEventListener('click', event => {
    closeShellPopup();
    action(event);
  });
  return button;
}

function shellMenuNote(text) {
  const note = document.createElement('div');
  note.className = 'shell-menu-note';
  note.setAttribute('role', 'presentation');
  note.textContent = text;
  return note;
}

function renderShellMenus() {
  const ai = byId('ai-menu');
  const save = byId('save-menu');
  const account = byId('account-menu');
  if (!ai || !save || !account) return;
  ai.replaceChildren(shellMenuNote(state.trial?.active
    ? `Funded credit: ${formatUSD(state.trial.available_microusd)} available` : 'Choose a funded model'));
  for (const profile of state.config?.profiles || []) {
    ai.append(shellMenuItem(profile.display_name || profile.label || profile.id, () => {
      state.llmAccess.mode = 'funded';
      state.llmAccess.profile = profile.id;
      renderAISettings();
      renderAccessSummary();
      renderShellControls();
      showGlobalStatus('Funded model selected for your next question.', 'success');
    }, { checked: state.llmAccess.mode === 'funded' && state.llmAccess.profile === profile.id }));
  }
  ai.append(shellMenuItem('Use your own API key...', () => openWorkspace('ai')));
  ai.append(shellMenuItem('AI access settings...', () => openWorkspace('ai')));
  const hasProject = Boolean(state.activeProject);
  save.replaceChildren(
    shellMenuItem('Save a private copy...', () => {
      if (!state.authSession.authenticated) return openWorkspace('account');
      openWorkspace('projects', { prepareSave: true });
    }),
    shellMenuItem('Share project...', () => openProjectSharing(), { disabled: !hasProject }),
    shellMenuItem(state.authSession.scenario_admin ? 'Publish as a community example...' : 'Suggest as a community example...',
      () => beginExampleSubmission(), { disabled: !hasProject || state.authSession.community_catalog_enabled === false }),
    shellMenuItem('Download scenario (.json)', () => downloadCurrentScenario(), { disabled: !state.bundle }),
    shellMenuItem('Export conversation (.json)', () => exportConversation(),
      { disabled: !state.chatMessages.length }),
  );
  const user = state.authSession.user;
  account.replaceChildren(shellMenuNote(user ? user.display_name || user.email : 'Explore freely. Sign in to save projects and use AI.'));
  account.append(shellMenuItem(user ? 'Account and credit...' : 'Sign in...', () => openWorkspace('account')));
  account.append(shellMenuItem('Manage projects...', () => openWorkspace('projects')));
  if (state.authSession.community_catalog_enabled !== false) {
    account.append(shellMenuItem('Community examples...', () => openWorkspace('examples')));
  }
  account.append(shellMenuItem('AI access...', () => openWorkspace('ai')));
  account.append(shellMenuItem('Agent access (Codex, Claude Code)...', () => openWorkspace('mcp')));
  if (state.authSession.can_switch_admin_view) {
    account.append(shellMenuItem(state.authSession.normal_user_view
      ? 'Restore administrator view' : 'Demonstrate as a normal user', event => toggleAccountView(event),
    { disabled: typeof accountView !== 'undefined' && accountView.busy }));
  }
  for (const [label, href] of [['Privacy', '/privacy.html'], ['Terms', '/terms.html']]) {
    const link = document.createElement('a');
    link.href = href;
    link.textContent = label;
    link.setAttribute('role', 'menuitem');
    account.append(link);
  }
  if (user) account.append(shellMenuItem('Sign out', event => handleLogout(event)));
}

function renderScenarioChoices() {
  const list = byId('scenario-options');
  if (!list) return;
  const focusKey = document.activeElement?.dataset?.scenarioKey;
  const groups = [
    ['Included examples', (state.scenarios || []).filter(item => item.category !== 'community')],
    ['Community examples', (state.scenarios || []).filter(item => item.category === 'community')],
    ['Your projects', (state.projects || []).filter(item => !item.archived_at).map(item => ({ ...item, project: true }))],
  ];
  list.replaceChildren();
  for (const [label, items] of groups) {
    if (!items.length) continue;
    const group = document.createElement('div');
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    const heading = document.createElement('div');
    heading.className = 'scenario-option-heading';
    heading.setAttribute('role', 'presentation');
    heading.textContent = label;
    group.append(heading);
    for (const item of items) {
      const selected = item.project ? state.activeProject?.id === item.id
        : state.viewKind === 'example' && state.scenario_id === item.id;
      const option = document.createElement('div');
      option.className = 'scenario-option';
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', String(selected));
      option.tabIndex = selected ? 0 : -1;
      option.dataset.scenarioKey = (item.project ? 'project:' : 'example:') + item.id;
      option.dataset.searchLabel = item.name || item.title;
      const title = document.createElement('span');
      title.textContent = item.name || item.title;
      option.append(title);
      if (item.category === 'community' && item.public_summary) {
        const summary = document.createElement('small');
        summary.className = 'scenario-option-summary'; summary.textContent = item.public_summary;
        option.append(summary);
      }
      const metadata = [];
      if (item.project) metadata.push(`v${item.version}`, formatDate(item.updated_at));
      else if (item.category === 'community') {
        metadata.push('Community');
        if (item.published_at) metadata.push(formatDate(item.published_at));
        if (item.attribution_name) metadata.push(item.attribution_name);
      } else if (selected && state.bundle) {
        const scenario = state.bundle.scenario;
        metadata.push(`${Object.keys(scenario.facts || {}).length} facts`,
          `${Object.keys(scenario.rules || {}).length} rules`,
          `${Object.keys(scenario.conclusions || {}).length} conclusions`);
      }
      if (metadata.length) {
        const detail = document.createElement('small');
        detail.textContent = metadata.filter(Boolean).join(' · ');
        option.append(detail);
      }
      const activate = () => {
        closeShellPopup();
        if (selected) { byId('scenario-menu-btn').focus(); return; }
        if (item.project) loadProject(item.id);
        else requestScenarioLoad(item.id);
      };
      option.addEventListener('click', activate);
      option.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
      });
      group.append(option);
    }
    list.append(group);
  }
  if (!state.authSession.authenticated) list.append(shellMenuNote('Sign in to see your private projects.'));
  if (!list.querySelector('[tabindex="0"]')) list.querySelector('[role="option"]')?.setAttribute('tabindex', '0');
  if (focusKey && activeShellPopup?.panel.id === 'scenario-popover') {
    [...list.querySelectorAll('[role="option"]')].find(item => item.dataset.scenarioKey === focusKey)?.focus();
  }
}

function renderShellControls() {
  if (!byId('scenario-menu-btn')) return;
  const accountScope = JSON.stringify([state.authSession.user?.id, state.authSession.normal_user_view,
    state.authSession.scenario_admin, state.authSession.can_switch_admin_view]);
  if (shellAccountScope !== accountScope) {
    closeShellPopup(false); shellAccountScope = accountScope;
    if (typeof clearArgumentViews === 'function') clearArgumentViews();
  }
  const hasChanges = state.diff_ops.length > 0;
  const pending = hasPendingStateRequest() || state.projectSavePending;
  const undo = validResetUndo();
  byId('reset-btn').hidden = !hasChanges;
  byId('reset-btn').disabled = !hasChanges || pending || state.readOnly;
  byId('reset-undo-btn').hidden = !undo;
  byId('reset-undo-btn').disabled = pending;
  byId('save-btn').textContent = state.readOnly ? 'Save a copy' : 'Save';
  byId('save-btn').disabled = !state.bundle || pending || Boolean(state.activeProject && !hasChanges);
  byId('save-btn').title = state.activeProject ? 'Save changes to this private project' : 'Save as a private project';
  byId('scenario-edit-btn').hidden = !state.activeProject;
  byId('scenario-download-btn').disabled = !state.bundle || pending;
  byId('scenario-sources-btn').disabled = !state.bundle || pending;
  const source = state.scenarios.find(item => item.id === state.scenario_id);
  if (state.viewKind === 'example') {
    byId('context-indicator').textContent = source?.category === 'community' ? 'Community example' : 'Example';
  }
  if (state.config) {
    const access = state.llmAccess;
    const provider = (state.config.byok_providers || []).find(item => item.id === access.provider);
    const model = access.mode === 'byok' ? provider?.models?.find(item => item.id === access.model)
      : (state.config.profiles || []).find(item => item.id === access.profile);
    const label = model?.display_name || model?.label || model?.id || 'Default';
    byId('ai-access-btn').textContent = `AI: ${label} · ${access.mode === 'byok' ? 'own key' : 'funded'}`;
    byId('ai-access-btn').title = byId('ai-access-btn').textContent;
  }
  const background = state.bundle?.scenario.description || '';
  const scope = resetScope();
  if (aboutScope !== scope) {
    aboutScope = scope;
    let collapsed = false;
    try { collapsed = localStorage.getItem('abda.about-collapsed') === '1'; } catch (_) { /* Optional preference. */ }
    byId('scenario-about').hidden = !background || collapsed;
  }
  byId('scenario-background').textContent = background;
  byId('scenario-about-btn').hidden = !background;
  byId('scenario-about-btn').setAttribute('aria-expanded', String(!byId('scenario-about').hidden));
  if (!background) byId('scenario-about').hidden = true;
}

function initShellUI() {
  byId('scenario-menu-btn').addEventListener('click', event => openShellPopup(event.currentTarget, byId('scenario-popover')));
  document.querySelectorAll('[data-shell-menu]').forEach(trigger => {
    trigger.addEventListener('click', () => openShellPopup(trigger, byId(trigger.dataset.shellMenu)));
  });
  byId('scenario-library-btn').addEventListener('click', () => closeShellPopup(false));
  byId('scenario-import-btn').addEventListener('click', () => { closeShellPopup(false); openScenarioLibrary('file'); });
  byId('scenario-projects-btn').addEventListener('click', () => { closeShellPopup(false); openWorkspace('projects'); });
  byId('scenario-download-btn').addEventListener('click', () => { closeShellPopup(false); downloadCurrentScenario(); });
  byId('scenario-sources-btn').addEventListener('click', () => { closeShellPopup(false); openSourcesReader(); });
  byId('scenario-edit-btn').addEventListener('click', () => { closeShellPopup(false); openPrivateScenarioEditor(); });
  byId('reset-undo-btn').addEventListener('click', undoBaselineReset);
  byId('scenario-about-btn').addEventListener('click', () => {
    byId('scenario-about').hidden = !byId('scenario-about').hidden;
    try { localStorage.setItem('abda.about-collapsed', byId('scenario-about').hidden ? '1' : '0'); } catch (_) { /* Optional preference. */ }
    renderShellControls();
  });
  for (const [id, field, render] of [
    ['facts-changed', 'factsChangedOnly', renderFacts], ['facts-suspended', 'factsSuspendedOnly', renderFacts],
    ['rules-changed', 'rulesChangedOnly', renderKB], ['rules-suspended', 'rulesSuspendedOnly', renderKB],
    ['facts-grouped', 'factsGrouped', renderFacts], ['rules-grouped', 'rulesGrouped', renderKB],
  ]) byId(id).addEventListener('change', event => { state[field] = event.target.checked; if (state.bundle) render(); });
  document.addEventListener('pointerdown', event => {
    if (activeShellPopup && !activeShellPopup.panel.contains(event.target) && !activeShellPopup.trigger.contains(event.target)) closeShellPopup(false);
    for (const details of document.querySelectorAll('.panel-options[open], .row-options[open]')) {
      if (!details.contains(event.target)) details.open = false;
    }
  });
  document.addEventListener('toggle', event => {
    const details = event.target;
    if (!details.matches?.('.panel-options, .row-options') || !details.open) return;
    document.querySelectorAll('.panel-options[open], .row-options[open]').forEach(other => {
      if (other !== details) other.open = false;
    });
    const menu = details.querySelector(':scope > div');
    const rect = details.querySelector('summary').getBoundingClientRect();
    if (!menu) return;
    menu.style.left = `${Math.max(8, Math.min(rect.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(rect.bottom + 4, innerHeight - menu.offsetHeight - 8))}px`;
  }, true);
  document.addEventListener('click', event => {
    if (event.target.closest('.panel-options button, .row-options button')) {
      event.target.closest('details').open = false;
    }
    const copy = event.target.closest('[data-copy-rule]');
    if (copy && state.bundle) {
      const text = formalElement(copy.dataset.copyRule, state.bundle.scenario);
      copyText(text).then(() => showGlobalStatus('ASPIC- line copied.', 'success'))
        .catch(() => showGlobalStatus('Copy failed. Open ASPIC- text to select the line.', 'error'));
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (activeShellPopup) {
        event.preventDefault(); event.stopImmediatePropagation(); closeShellPopup(); return;
      }
      const details = event.target.closest('.panel-options[open], .row-options[open]');
      if (details) {
        event.preventDefault(); event.stopImmediatePropagation();
        details.open = false; details.querySelector('summary').focus(); return;
      }
    }
    if (!activeShellPopup) return;
    if (event.key === 'Tab' && activeShellPopup.panel.getAttribute('role') === 'menu') {
      closeShellPopup(); return;
    }
    const selector = activeShellPopup.panel.id === 'scenario-popover' ? '[role="option"]' : '[role^="menuitem"]:not(:disabled)';
    const items = [...activeShellPopup.panel.querySelectorAll(selector)];
    const index = items.indexOf(document.activeElement);
    if (index < 0 || !items.length) return;
    let next = null;
    if (event.key === 'ArrowDown') next = (index + 1) % items.length;
    if (event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = items.length - 1;
    if (event.key.length === 1 && event.key !== ' ' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      clearTimeout(shellTypeaheadTimer);
      shellTypeahead += event.key.toLocaleLowerCase();
      shellTypeaheadTimer = setTimeout(() => { shellTypeahead = ''; }, 700);
      const offset = [...items.slice(index + 1), ...items.slice(0, index + 1)]
        .find(item => (item.dataset.searchLabel || item.textContent).toLocaleLowerCase().startsWith(shellTypeahead));
      if (offset) next = items.indexOf(offset);
    }
    if (next !== null) {
      event.preventDefault(); items[next].focus();
      if (selector === '[role="option"]') items.forEach((item, i) => { item.tabIndex = i === next ? 0 : -1; });
    }
  }, true);
}
