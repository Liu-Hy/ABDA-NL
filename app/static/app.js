/* ================================================================
   ABDA-NL frontend
   Fetches state bundles from the FastAPI backend and renders the
   Conclusions / Facts / Assumptions / Rules panels. Toggles on
   assumptions and defeasible rules append ops to a client-held
   diff_ops list and POST /state for re-computation.
   ================================================================ */

const AI_CONTEXT_ICON = '<svg class="ai-context-icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false"><path d="M9 3.5 10.7 8.3 15.5 10 10.7 11.7 9 16.5 7.3 11.7 2.5 10 7.3 8.3Z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M15.5 2.5v4m-2-2h4" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/></svg>';

const state = {
  scenarios: [],        // [{id, title, description}, ...]
  scenario_id: null,    // currently-loaded scenario id
  baseline: null,       // scenario object at baseline (zero ops)
  bundle: null,         // current {scenario, af} from the server
  diff_ops: [],         // ops appended since baseline
  renderedDiffOps: [],  // ops represented by the currently rendered bundle
  config: null,
  authSession: { authenticated: false, auth_mode: 'disabled', user: null },
  trial: null,
  projects: [],
  mcpTokens: [],
  activeProject: null,
  activeShares: [],
  sharesLoadedFor: null,
  latestShare: null,
  oneTimeSecretGeneration: 0,
  viewKind: 'example',  // 'example' | 'project' | 'shared'
  sharedProject: null,
  readOnly: false,
  projectSavePending: false,
  llmAccess: {
    mode: 'funded',
    profile: null,
    provider: null,
    model: null,
    apiKey: '',
  },
  // UI state
  conclusionFilter: 'key',
  factsFilter: 'facts',
  factsChangedOnly: false,
  factsSuspendedOnly: false,
  kbTab: 'all',
  rulesChangedOnly: false,
  rulesSuspendedOnly: false,
  searchQuery: '',
  factsGrouped: false,
  rulesGrouped: false,
  // Rendering helpers populated on each bundle load
  descMap: {},          // id -> NL description (facts/assumptions/props/conclusions)
  negDescMap: {},       // id -> authored NL rendering of the negated literal (if any)
  ruleIds: new Set(),   // set of rule ids (for literal rendering)
  // Chat
  chatMessages: [],     // [{role: 'user'|'assistant', content: str}, ...]
  chatPending: false,   // true while a /chat request is in flight
  chatContextRefs: [],
  chatDegraded: false,
  labelPulseIds: new Set(),  // proposition ids whose labels changed on last recompute
  labelPulseTimer: null,
};

// Max turns the server accepts in one request (per spec). We trim client
// history to this many user+assistant pairs before POSTing so the backend
// never has to reject a too-long message list.
const CHAT_TURN_CAP = 20;

// Assistant text is untrusted even when it came from a funded provider. Keep
// the Markdown surface deliberately smaller than DOMPurify's general HTML
// profile, and insert the sanitized fragment without reparsing it in a wrapper.
const CHAT_MARKDOWN_ALLOWED_TAGS = Object.freeze([
  'a', 'blockquote', 'br', 'code', 'del', 'em', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'hr', 'li', 'ol', 'p', 'pre', 'strong', 'table', 'tbody',
  'td', 'th', 'thead', 'tr', 'ul',
]);
const CHAT_MARKDOWN_ALLOWED_ATTR = Object.freeze([
  'align', 'colspan', 'href', 'rowspan', 'scope', 'start', 'title',
]);


function apiErrorMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail.message === 'string') return detail.message;
  if (Array.isArray(body?.errors) && body.errors[0]?.message) return body.errors[0].message;
  return fallback;
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(apiErrorMessage(body, `${options.method || 'GET'} ${path}: ${response.status}`));
    error.status = response.status;
    error.code = body?.detail?.code || body?.errors?.[0]?.code || null;
    error.errors = body?.errors || [];
    error.body = body;
    throw error;
  }
  return body;
}


/* ── API wrappers ─────────────────────────────────────── */

async function apiListScenarios() {
  return (await apiRequest('/scenarios')).scenarios;
}

async function apiGetConfig() {
  return await apiRequest('/config');
}

async function apiPostState(
  scenario_id,
  diff_ops,
  signal,
  project = state.activeProject,
) {
  const path = project ? `/api/projects/${encodeURIComponent(project.id)}/state` : '/state';
  const payload = project
    ? { expected_version: project.version, diff_ops }
    : { scenario_id, diff_ops };
  return await apiRequest(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
}

async function apiSaveScenario(payload) {
  return await apiRequest('/scenarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

// Track the current in-flight POST /state so newer requests can cancel
// older ones. This closes two races: (1) load-then-toggle where the
// toggle's response arrives after the load's and writes stale state;
// (2) rapid double-toggle where the slower response lands last. An
// aborted fetch throws AbortError which the callers swallow.
let currentRequest = null;
function beginRequest() {
  if (currentRequest) currentRequest.abort();
  const ctrl = new AbortController();
  currentRequest = ctrl;
  renderScenarioLibraryAccess();
  if (typeof renderShellControls === 'function') renderShellControls();
  return ctrl;
}
function isCurrent(ctrl) {
  return ctrl === currentRequest;
}
function isAbortError(e) {
  return e && (e.name === 'AbortError' || e.code === 20);
}
function finishRequest(ctrl) {
  if (ctrl !== currentRequest) return;
  currentRequest = null;
  // A library opened during a load must recover after success or failure.
  // A superseded request must not enable controls for a newer pending one.
  renderScenarioLibraryAccess();
  if (typeof renderShellControls === 'function') renderShellControls();
}
function hasPendingStateRequest() {
  return currentRequest !== null;
}
function blockStateMutationDuringSave() {
  if (!state.projectSavePending) return false;
  showGlobalStatus('Wait for the current scenario save to finish before making another change.', 'info');
  renderAll();
  return true;
}


function initBaseUI() {
  document.getElementById('aspic-btn')?.addEventListener('click', openAspicModal);
  document.getElementById('reset-btn')?.addEventListener('click', resetToBaseline);
  document.getElementById('view-af-btn')?.addEventListener('click', openAFModal);
  document.querySelector('.concl-filters')?.addEventListener('click', event => {
    const button = event.target.closest('[data-filter]');
    if (button) switchConclusionFilter(button.dataset.filter);
  });
  document.querySelector('.facts-filter-bar')?.addEventListener('click', event => {
    const button = event.target.closest('.facts-filter[data-filter]');
    if (button) switchFactsFilter(button.dataset.filter);
  });
  document.querySelector('.rules-toolbar')?.addEventListener('click', event => {
    const button = event.target.closest('.kb-tab[data-tab]');
    if (button) switchKBTab(button.dataset.tab);
  });
  document.querySelectorAll('[data-edit-task]').forEach(button => {
    button.addEventListener('click', () => openEditModal(button.dataset.editTask));
  });
  document.getElementById('kb-search-input')?.addEventListener('input', event => filterKB(event.target.value));
  document.getElementById('chat-send-btn')?.addEventListener('click', () => sendChatMessage());
  document.getElementById('chat-cancel-btn')?.addEventListener('click', () => cancelChatRequest());
  document.getElementById('edit-instruction')?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      sendPropose();
    }
  });
  document.getElementById('edit-footer')?.addEventListener('click', event => {
    const action = event.target.closest('[data-edit-action]')?.dataset.editAction;
    if (action === 'cancel') closeEditModal();
    if (action === 'refine') refineProposal();
    if (action === 'apply') applyProposal();
    if (action === 'propose') sendPropose();
  });

  document.querySelectorAll('.modal-close').forEach(button => {
    button.addEventListener('click', () => requestCloseModal(button.closest('.modal-backdrop').id));
  });
  document.getElementById('save-title')?.addEventListener('input', onSaveTitleInput);
  document.getElementById('save-id')?.addEventListener('input', onSaveIdInput);
  document.getElementById('save-overwrite-source')?.addEventListener('change', onSaveOverwriteToggle);
  document.getElementById('save-cancel-btn')?.addEventListener('click', () => closeModal('modal-save'));
  document.getElementById('save-submit-btn')?.addEventListener('click', () => submitSave(false));
  document.getElementById('save-overwrite-cancel-btn')?.addEventListener('click', () => closeModal('modal-save-overwrite-confirm'));
  document.getElementById('save-overwrite-confirm-btn')?.addEventListener('click', onSaveOverwriteConfirm);
  document.getElementById('save-collision-cancel-btn')?.addEventListener('click', onSaveCollisionCancel);
  document.getElementById('save-collision-rename-btn')?.addEventListener('click', onSaveCollisionRename);
  document.getElementById('save-collision-overwrite-btn')?.addEventListener('click', onSaveCollisionOverwrite);
  document.getElementById('suspend-impact-cancel-btn')?.addEventListener('click', cancelSuspendImpact);
  document.getElementById('suspend-impact-apply-btn')?.addEventListener('click', applySuspendImpact);
  document.getElementById('aspic-copy-btn')?.addEventListener('click', copyAspicToClipboard);
}


/* ── Bootstrap ────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', async () => {
  initBaseUI();
  initResize();
  initModalAccessibility();
  initWorkspaceUI();
  initScenarioLibrary();
  initShellUI();
  try {
    // Fetch config first so LLM-only DOM is hidden before first paint of
    // scenario content — avoids a flash of chat/save/add buttons on
    // servers that run with ABDA_ENABLE_LLM unset (the default).
    const viewRevision = accountView.revision;
    const [config, authSession, scenarios] = await Promise.all([
      apiGetConfig(),
      apiRequest('/api/auth/session'),
      apiListScenarios(),
    ]);
    state.config = config;
    state.authSession = await authSessionForCurrentView(authSession, viewRevision);
    state.scenarios = scenarios;
    initializeLLMAccess(config);
    document.body.classList.toggle('llm-disabled', !config.llm_enabled);
    populateScenarioSelect();
    renderAccountUI();
    renderAISettings();
    renderAccessSummary();

    const authError = new URLSearchParams(window.location.search).get('auth_error');
    if (authError) {
      const messages = {
        email_verification_required: 'Sign-in was not completed because the provider did not verify the email address.',
        account_link_required: 'This email already belongs to another sign-in identity. Use the original sign-in method.',
        account_unavailable: 'This account is not available. Contact the project team if this is unexpected.',
        identity_claims_invalid: 'The sign-in provider returned an identity that this service could not verify.',
      };
      showGlobalStatus(
        messages[authError] || 'Sign-in could not be completed. Please try again.',
        'error',
      );
      const cleanUrl = new URL(window.location.href);
      cleanUrl.searchParams.delete('auth_error');
      window.history.replaceState({}, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`);
    }

    const shareToken = new URLSearchParams(window.location.hash.slice(1)).get('share');
    if (shareToken) {
      await loadSharedProject(shareToken);
    } else {
      // Pick a reasonable default: popov_v_hayashi if present, else the first.
      const defaultId = state.scenarios.some(s => s.id === 'popov_v_hayashi')
        ? 'popov_v_hayashi'
        : state.scenarios[0]?.id;
      if (defaultId) await loadScenario(defaultId);
    }
    await refreshAuthenticatedWorkspace({ quiet: true });
  } catch (e) {
    showGlobalError(`Failed to initialize: ${e.message}`);
  }
});

function populateScenarioSelect() {
  renderScenarioChoices();
  renderShellControls();
}

function hasUnsavedChanges() {
  return state.diff_ops.length > 0;
}

function requestScenarioLoad(id) {
  if (id === '__current_project__' || id === '__shared_project__') return;
  if (hasUnsavedChanges() && !window.confirm('Discard the unsaved changes in the current view?')) {
    populateScenarioSelect();
    return;
  }
  loadScenario(id);
}

function setViewContext(kind, project = null) {
  const previousProjectId = state.activeProject?.id || null;
  state.viewKind = kind;
  state.activeProject = kind === 'project' ? project : null;
  state.sharedProject = kind === 'shared' ? project : null;
  state.readOnly = kind === 'shared';
  if (kind !== 'project' || project?.id !== previousProjectId) {
    state.activeShares = [];
    state.sharesLoadedFor = null;
    state.latestShare = null;
  }
  document.body.classList.toggle('shared-view', state.readOnly);

  const indicator = document.getElementById('context-indicator');
  indicator.classList.remove('context-project', 'context-shared');
  if (kind === 'project') {
    indicator.textContent = 'Private scenario';
    indicator.classList.add('context-project');
  } else if (kind === 'shared') {
    indicator.textContent = 'Shared read-only';
    indicator.classList.add('context-shared');
  } else {
    indicator.textContent = 'Built-in scenario';
  }
  renderAccountUI();
  const resetButton = document.getElementById('reset-btn');
  if (resetButton) resetButton.disabled = state.readOnly || !state.diff_ops.length;
  const saveButton = document.getElementById('save-btn');
  if (saveButton) saveButton.textContent = kind === 'shared' ? 'Save a copy' : 'Save';
  renderChatAccess();
}

async function loadProject(projectId) {
  if (hasUnsavedChanges() && !window.confirm('Discard the unsaved changes in the current view?')) return;
  const ctrl = beginRequest();
  setWorkspaceStatus('projects-status', 'Opening scenario...', 'info');
  try {
    const project = await apiRequest(`/api/projects/${encodeURIComponent(projectId)}`, {
      signal: ctrl.signal,
    });
    if (!isCurrent(ctrl)) return;
    setViewContext('project', project);
    state.scenario_id = project.source_scenario_id;
    state.baseline = project.scenario;
    state.diff_ops = [];
    setBundle({ scenario: project.scenario, af: project.af });
    resetChatConversation();
    resetViewFilters();
    indexBundle();
    populateScenarioSelect();
    renderAll();
    renderProjectsUI();
    requestCloseModal('modal-workspace');
    showGlobalStatus(`Opened private scenario "${project.name}".`, 'success');
  } catch (error) {
    if (isAbortError(error) || !isCurrent(ctrl)) return;
    setWorkspaceStatus('projects-status', error.message, 'error');
  } finally {
    finishRequest(ctrl);
  }
}

async function loadSharedProject(token) {
  if (!token || token.length > 256) throw new Error('This shared scenario link is invalid.');
  const ctrl = beginRequest();
  try {
    const project = await apiRequest('/api/shares/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      signal: ctrl.signal,
    });
    if (!isCurrent(ctrl)) return;
    setViewContext('shared', project);
    state.scenario_id = null;
    state.baseline = project.scenario;
    state.diff_ops = [];
    setBundle({ scenario: project.scenario, af: project.af });
    resetChatConversation();
    resetViewFilters();
    indexBundle();
    populateScenarioSelect();
    renderAll();
    showGlobalStatus(`Viewing shared scenario "${project.name}" in read-only mode.`, 'info');
  } finally {
    finishRequest(ctrl);
  }
}

function resetViewFilters() {
  state.conclusionFilter = 'key';
  state.factsFilter = 'facts';
  state.kbTab = 'all';
  state.searchQuery = '';
  state.factsChangedOnly = false;
  state.factsSuspendedOnly = false;
  state.rulesChangedOnly = false;
  state.rulesSuspendedOnly = false;
  for (const id of ['facts-changed', 'facts-suspended', 'rules-changed', 'rules-suspended']) {
    const control = document.getElementById(id);
    if (control) control.checked = false;
  }
  const searchInput = document.getElementById('kb-search-input');
  if (searchInput) searchInput.value = '';
  syncToggleButtons('.concl-filter', 'filter', 'key');
  syncToggleButtons('.facts-filter', 'filter', 'facts');
  syncToggleButtons('.kb-tab', 'tab', 'all');
}


/* ── State transitions ────────────────────────────────── */

async function loadScenario(id) {
  const ctrl = beginRequest();
  try {
    const bundle = await apiPostState(id, [], ctrl.signal, null);
    if (!isCurrent(ctrl)) return;  // superseded by a newer request
    setViewContext('example');
    state.scenario_id = id;
    state.diff_ops = [];
    // Reset UI-local state that is only meaningful for the prior scenario
    // (tab selection, search query). Without this a user coming from the
    // Modified tab lands on an empty view for a pristine scenario and
    // thinks the UI is broken.
    resetChatConversation();
    resetViewFilters();
    state.baseline = bundle.scenario;
    setBundle(bundle);
    indexBundle();
    populateScenarioSelect();
    renderAll();
  } catch (e) {
    if (isAbortError(e) || !isCurrent(ctrl)) return;
    populateScenarioSelect();
    showGlobalError(`Failed to load scenario ${id}: ${e.message}`);
  } finally {
    finishRequest(ctrl);
  }
}

async function resetToBaseline() {
  if (state.readOnly || (!state.scenario_id && !state.activeProject)) return;
  if (!state.renderedDiffOps.length) return;
  if (blockStateMutationDuringSave()) return;
  const operations = structuredClone(state.renderedDiffOps);
  const originalScope = resetScope();
  const originalBaseline = state.baseline;
  const ctrl = beginRequest();
  state.diff_ops = state.renderedDiffOps.slice();
  try {
    const bundle = await apiPostState(state.scenario_id, [], ctrl.signal);
    if (!isCurrent(ctrl)) return;
    if (originalScope !== resetScope() || originalBaseline !== state.baseline) return;
    state.diff_ops = [];
    setBundle(bundle, { pulseLabels: true });
    resetUndo = { operations, scope: originalScope, baseline: originalBaseline, bundle };
    indexBundle();
    renderAll();
    showGlobalStatus('Restored the baseline. Undo reset is available until your next change.', 'success');
  } catch (e) {
    if (isAbortError(e) || !isCurrent(ctrl)) return;
    showGlobalError(`Reset failed: ${e.message}`);
    renderAll();
  } finally {
    finishRequest(ctrl);
  }
}

async function applyOp(op) {
  return applyOps([op]);
}

// Batch multiple ops into a single round-trip. Used by the Conflicts
// view where "A stronger" / "Same" / "B stronger" can emit 1-2 set-block
// ops at once; applying them as a batch avoids two intermediate renders.
async function applyOps(ops) {
  if (!ops || ops.length === 0) return;
  if (state.readOnly) {
    showGlobalStatus('Shared scenarios are read-only. Save a private copy to make changes.', 'info');
    return;
  }
  if (blockStateMutationDuringSave()) return;
  const ctrl = beginRequest();
  state.diff_ops = [...state.diff_ops, ...ops];
  try {
    const bundle = await apiPostState(state.scenario_id, state.diff_ops, ctrl.signal);
    if (!isCurrent(ctrl)) return;
    setBundle(bundle, { pulseLabels: true });
    indexBundle();
    renderAll();
  } catch (e) {
    if (isAbortError(e) || !isCurrent(ctrl)) return;
    state.diff_ops = state.renderedDiffOps.slice();
    showGlobalError(e.message);
    renderAll();
  } finally {
    finishRequest(ctrl);
  }
}

// --- Suspend-impact preview ------------------------------------------------
// Intercepts the active-toggle checkboxes on assumptions and defeasible
// rules. Runs the op through /state speculatively, diffs the resulting
// labels_by_proposition against the current one, and shows a modal so the
// user can see which conclusions will change label before committing.
// Apply commits by promoting the previewed bundle to state (no second
// round-trip). Cancel re-renders so the checkbox snaps back to the
// pre-click state.

let pendingSuspendImpact = null;

async function previewAndConfirmToggle(op, meta) {
  if (state.readOnly) {
    renderFacts();
    renderKB();
    showGlobalStatus('Shared scenarios are read-only.', 'info');
    return;
  }
  if (blockStateMutationDuringSave()) return;
  const ctrl = beginRequest();
  try {
    const prospectiveOps = [...state.diff_ops, op];
    let projected;
    try {
      projected = await apiPostState(state.scenario_id, prospectiveOps, ctrl.signal);
    } catch (e) {
      if (isAbortError(e) || !isCurrent(ctrl)) return;
      renderFacts();
      renderKB();
      showGlobalError(`Preview failed: ${e.message}`);
      return;
    }
    if (!isCurrent(ctrl)) return;

    const before = state.bundle.af.labels_by_proposition || {};
    const after = projected.af.labels_by_proposition || {};
    const diffs = computeLabelDiffs(before, after, projected.scenario);

    pendingSuspendImpact = { prospectiveOps, projected };
    document.getElementById('suspend-impact-title').textContent = meta.title;
    document.getElementById('suspend-impact-summary').innerHTML = meta.summary;
    document.getElementById('suspend-impact-list').innerHTML = renderImpactDiffs(diffs);
    openModal('modal-suspend-impact', '#suspend-impact-apply-btn');
  } finally {
    finishRequest(ctrl);
  }
}

// Returns an array of { id, description, before, after } for every
// proposition whose label changed between the two label maps. Sorted
// with key conclusions first, then propositions, then facts/assumptions,
// each block alphabetical within itself -- matches what the user scans
// for first in the Conclusions panel.
function computeLabelDiffs(before, after, scenario) {
  const ids = new Set([...Object.keys(before), ...Object.keys(after)]);
  const concKeys = new Set(Object.keys(scenario.conclusions || {}));
  const propKeys = new Set(Object.keys(scenario.propositions || {}));
  const out = [];
  for (const id of ids) {
    const b = before[id] || 'absent';
    const a = after[id] || 'absent';
    if (b === a) continue;
    const entry =
      scenario.conclusions?.[id] ||
      scenario.propositions?.[id] ||
      scenario.facts?.[id] ||
      scenario.assumptions?.[id];
    const description = entry?.description || id;
    const tier = concKeys.has(id) ? 0 : propKeys.has(id) ? 1 : 2;
    out.push({ id, description, before: b, after: a, tier });
  }
  out.sort((x, y) => x.tier - y.tier || x.description.localeCompare(y.description));
  return out;
}

function renderImpactDiffs(diffs) {
  if (diffs.length === 0) {
    return `<div class="suspend-impact-empty">No conclusions change label under this edit.</div>`;
  }
  const badge = (label) => {
    const text = label.charAt(0).toUpperCase() + label.slice(1);
    return `<span class="badge badge-${label}" style="font-size:.6rem">${text}</span>`;
  };
  return diffs.map(d => `<div class="suspend-impact-item">
    <span class="suspend-impact-item-text">${escapeHtml(d.description)} <span class="inline-id">[${escapeHtml(d.id)}]</span></span>
    <span class="suspend-impact-transition">${badge(d.before)} → ${badge(d.after)}</span>
  </div>`).join('');
}

function applySuspendImpact() {
  if (!pendingSuspendImpact) return;
  const { prospectiveOps, projected } = pendingSuspendImpact;
  pendingSuspendImpact = null;
  state.diff_ops = prospectiveOps;
  setBundle(projected, { pulseLabels: true });
  indexBundle();
  renderAll();
  closeModal('modal-suspend-impact');
}

function setBundle(bundle, options = {}) {
  if (options.pulseLabels && state.bundle?.af) {
    state.labelPulseIds = computeChangedLabelIds(
      state.bundle.af.labels_by_proposition || {},
      bundle.af?.labels_by_proposition || {},
    );
  } else {
    state.labelPulseIds = new Set();
  }
  state.labelChangedIds = new Set(state.labelPulseIds);
  state.bundle = bundle;
  state.renderedDiffOps = state.diff_ops.slice();
}

function computeChangedLabelIds(before, after) {
  const ids = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  const changed = new Set();
  for (const id of ids) {
    if ((before || {})[id] !== (after || {})[id]) changed.add(id);
  }
  return changed;
}

function cancelSuspendImpact() {
  pendingSuspendImpact = null;
  closeModal('modal-suspend-impact');
  renderFacts();
  renderKB();
}

function indexBundle() {
  const scn = state.bundle.scenario;
  const map = {};
  const negMap = {};
  for (const section of ['facts', 'assumptions', 'propositions', 'conclusions']) {
    for (const [id, e] of Object.entries(scn[section] || {})) {
      map[id] = e.description;
      if (e.negated_description) negMap[id] = e.negated_description;
    }
  }
  for (const [id, r] of Object.entries(scn.rules || {})) {
    if (r.negated_description) negMap[id] = r.negated_description;
  }
  state.descMap = map;
  state.negDescMap = negMap;
  state.ruleIds = new Set(Object.keys(scn.rules || {}));
}


/* ── "modified vs baseline" detection ─────────────────── */

function isAssumptionModified(id) {
  const b = state.baseline.assumptions?.[id];
  const c = state.bundle.scenario.assumptions?.[id];
  if (!b && !c) return false;
  if (!b || !c) return true;  // added or removed via future ops
  return b.active !== c.active
    || b.description !== c.description
    || b.category !== c.category
    || b.source !== c.source
    || b.block !== c.block;
}

function isFactModified(id) {
  const b = state.baseline.facts?.[id];
  const c = state.bundle.scenario.facts?.[id];
  if (!b && !c) return false;
  if (!b || !c) return true;
  return b.description !== c.description
    || b.category !== c.category
    || b.source !== c.source;
}

function isRuleModified(id) {
  const b = state.baseline.rules?.[id];
  const c = state.bundle.scenario.rules?.[id];
  if (!b && !c) return false;
  if (!b || !c) return true;  // added or removed via future ops
  return b.active !== c.active
    || b.block !== c.block
    || b.conclusion !== c.conclusion
    || b.type !== c.type
    || JSON.stringify(b.premises) !== JSON.stringify(c.premises);
}


/* ── Rendering ────────────────────────────────────────── */

function renderAll() {
  renderScenarioName();
  renderModifiedIndicator();
  renderShellControls();
  renderConclusions();
  renderFacts();
  renderKB();
  renderChat();
  if (state.authSession.authenticated) renderProjectsUI();
  validateArgumentViews();
}

function renderScenarioName() {
  const scn = state.bundle?.scenario;
  const label = state.activeProject?.name || state.sharedProject?.name || scn?.title || '';
  const element = document.getElementById('scenario-name');
  element.textContent = label;
  element.title = scn?.title && scn.title !== label ? `Scenario: ${scn.title}` : '';
}

function renderModifiedIndicator() {
  const indicator = document.getElementById('modified-indicator');
  if (!indicator) return;
  const count = state.diff_ops.length;
  if (count === 0) {
    indicator.hidden = true;
    indicator.textContent = '';
    return;
  }
  indicator.hidden = false;
  const prefix = state.activeProject ? 'Unsaved' : 'Modified from baseline';
  indicator.textContent = `${prefix}: ${count} ${count === 1 ? 'change' : 'changes'}`;
}

function renderConclusions() {
  const list = document.getElementById('conclusions-list');
  const scn = state.bundle.scenario;
  const labels = state.bundle.af.labels_by_proposition || {};

  //   key       -> all scenario.conclusions (Explain is individually
  //                disabled on conclusions without any argument for them)
  //   accepted/rejected/undecided/absent -> conclusions ∪ propositions filtered by label
  //   all       -> conclusions ∪ propositions
  let entries = [];
  if (state.conclusionFilter === 'key') {
    entries = Object.entries(scn.conclusions || {});
  } else {
    entries = [
      ...Object.entries(scn.conclusions || {}),
      ...Object.entries(scn.propositions || {}),
    ];
    if (state.conclusionFilter !== 'all') {
      entries = entries.filter(([id]) => labels[id] === state.conclusionFilter);
    }
  }

  if (entries.length === 0) {
    document.getElementById('conclusions-count').textContent = '0';
    list.innerHTML = `<div class="placeholder-msg">No conclusions match the ${state.conclusionFilter} filter.</div>`;
    return;
  }

  document.getElementById('conclusions-count').textContent = `${entries.length}${state.conclusionFilter === 'key' ? ' key' : ''}`;
  list.innerHTML = entries.map(([id, entry]) => {
    const label = labels[id] || 'absent';
    const badge = label.charAt(0).toUpperCase() + label.slice(1);
    const explainable = getCandidateRootArguments(id).length > 0;
    const title = explainable
      ? ''
      : (label === 'absent'
          ? 'No argument derives this conclusion in the current state'
          : 'No derivation is available for this conclusion');
    const explain = explainable
      ? `<button class="btn-explain" data-explain-id="${escapeAttr(id)}">Explain</button>`
      : `<button class="btn-explain" disabled title="${escapeAttr(title)}">Explain</button>`;
    const changed = state.labelPulseIds.has(id) ? ' label-changed' : '';
    return `<div class="conclusion-card status-${label}${changed}" data-element-kind="conclusion" data-element-id="${escapeAttr(id)}">
      <span class="conclusion-label">${escapeHtml(entry.description)}${state.labelChangedIds?.has(id) ? '<span class="label-change-note">Status changed</span>' : ''}</span>
      <div class="conclusion-meta">
        <span class="conclusion-status-bar status-${label}">${badge}${label === 'absent' ? ' · No argument' : ''}</span>
        <button type="button" class="inline-id element-inspect-link" data-inspect-conclusion="${escapeAttr(id)}" title="Inspect this conclusion and its derivations" aria-label="Inspect derivations for ${escapeAttr(entry.description)}">${escapeHtml(id)}</button>
      </div>
      <div class="conclusion-actions">
        ${explain}
        <button type="button" class="rule-info" data-context-kind="conclusion" data-context-id="${escapeAttr(id)}" data-desc="${escapeAttr(entry.description)}" title="Add this conclusion to chat" aria-label="Add conclusion to chat: ${escapeAttr(entry.description)}">${AI_CONTEXT_ICON}</button>
      </div>
    </div>`;
  }).join('');

  for (const btn of list.querySelectorAll('button[data-explain-id]')) {
    btn.addEventListener('click', () => openExplainModal(btn.dataset.explainId));
  }
  if (state.labelPulseIds.size > 0) {
    if (state.labelPulseTimer) window.clearTimeout(state.labelPulseTimer);
    state.labelPulseTimer = window.setTimeout(() => {
      state.labelPulseIds.clear();
      state.labelPulseTimer = null;
    }, 900);
  }
}

function switchConclusionFilter(f) {
  state.conclusionFilter = f;
  syncToggleButtons('.concl-filter', 'filter', f);
  renderConclusions();
}

function renderFacts() {
  const list = document.getElementById('facts-list');
  const scn = state.bundle.scenario;

  const kind = state.factsFilter === 'assumptions' ? 'assumption' : 'fact';
  let items = Object.entries(scn[state.factsFilter] || {}).map(([id, entry]) => [id, entry, kind]);
  if (state.factsChangedOnly) items = items.filter(([id]) => kind === 'fact' ? isFactModified(id) : isAssumptionModified(id));
  if (state.factsSuspendedOnly) items = items.filter(([, entry, type]) => type === 'assumption' && entry.active === false);
  document.getElementById('facts-count').textContent = String(items.length);

  if (items.length === 0) {
    const emptyMsg = `No ${state.factsFilter} match these filters.`;
    list.innerHTML = `<div class="placeholder-msg">${emptyMsg}</div>`;
    return;
  }

  // Keep category ordering stable with either display preference.
  const groups = {};
  for (const item of items) {
    const cat = item[1].category || 'other';
    (groups[cat] ||= []).push(item);
  }
  const sortedCats = Object.keys(groups).sort();
  if (!state.factsGrouped) {
    list.innerHTML = sortedCats
      .flatMap(cat => groups[cat].map(([id, e, kind]) => renderFactLikeCard(id, e, kind)))
      .join('');
  } else {
    list.innerHTML = sortedCats.map(cat => {
      const cards = groups[cat]
        .map(([id, e, kind]) => renderFactLikeCard(id, e, kind))
        .join('');
      return `<div class="kb-group">
        <div class="kb-group-title">${categoryBadge(cat)}</div>
        ${cards}
      </div>`;
    }).join('');
  }

  for (const cb of list.querySelectorAll('input[data-asm-id]')) {
    cb.addEventListener('change', e => {
      const id = e.target.dataset.asmId;
      const asm = state.bundle.scenario.assumptions?.[id];
      const nowActive = e.target.checked;
      const action = nowActive ? 'Unsuspend' : 'Suspend';
      const desc = asm?.description || id;
      previewAndConfirmToggle(
        { op: 'toggle-assumption', id },
        {
          title: `${action} assumption?`,
          summary: `<strong>${action}:</strong> ${escapeHtml(desc)} <span class="inline-id">[${escapeHtml(id)}]</span>`,
        },
      );
    });
  }
}

function categoryBadge(cat) {
  if (!cat) return '';
  return `<span class="kb-badge">${escapeHtml(cat)}</span>`;
}


function renderFactLikeCard(id, entry, kind) {
  const info = 'Add this ' + kind + ' to chat';
  const desc = escapeAttr(entry.description);
  const inlineId = `<button type="button" class="inline-id element-inspect-link" data-open-element-kind="${kind}" data-open-element-id="${escapeAttr(id)}" title="Inspect formal representation and derivations">[${escapeHtml(id)}]</button>`;
  const badge = !state.factsGrouped ? categoryBadge(entry.category) : '';
  const text = `<div class="fact-body"><span class="fact-text">${escapeHtml(entry.description)}</span><div class="fact-meta">${badge} ${inlineId}</div></div>`;
  if (kind === 'assumption') {
    const active = entry.active !== false;
    const divergent = isAssumptionModified(id);
    const cls = 'fact-card'
      + (divergent ? ' kb-divergent' : '')
      + (!active ? ' suspended' : '');
    return `<div class="${cls}" data-element-kind="${kind}" data-element-id="${escapeAttr(id)}">
      ${text}
      <div class="fact-actions">
      <button type="button" class="rule-info" data-context-kind="${kind}" data-context-id="${escapeAttr(id)}" data-desc="${desc}" title="${info}" aria-label="Add ${kind} to chat: ${desc}">${AI_CONTEXT_ICON}</button>
      <label class="active-control"><input type="checkbox" ${active ? 'checked' : ''} ${state.readOnly ? 'disabled' : ''} data-asm-id="${escapeAttr(id)}" aria-label="${active ? 'Suspend' : 'Unsuspend'} assumption ${desc}"> ${active ? 'Active' : 'Suspended'}</label>
      </div>
    </div>`;
  }
  const divergent = isFactModified(id);
  const cls = 'fact-card' + (divergent ? ' kb-divergent' : '');
  return `<div class="${cls}" data-element-kind="${kind}" data-element-id="${escapeAttr(id)}">
    ${text}
    <div class="fact-actions">
    <button type="button" class="rule-info" data-context-kind="${kind}" data-context-id="${escapeAttr(id)}" data-desc="${desc}" title="${info}" aria-label="Add ${kind} to chat: ${desc}">${AI_CONTEXT_ICON}</button>
    </div>
  </div>`;
}

function switchFactsFilter(f) {
  state.factsFilter = f;
  syncToggleButtons('.facts-filter', 'filter', f);
  renderFacts();
}

function renderKB() {
  const root = document.getElementById('kb-content');
  const scn = state.bundle.scenario;

  // Conflicts tab takes a distinct code path: we show preference-card
  // pairs rather than the usual rule list.
  if (state.kbTab === 'conflicts') {
    document.getElementById('rules-count').textContent = '';
    renderConflicts(root);
    return;
  }

  let rules = Object.entries(scn.rules || {});

  if (state.rulesChangedOnly) {
    rules = rules.filter(([id]) => isRuleModified(id));
  }
  if (state.rulesSuspendedOnly) {
    rules = rules.filter(([, r]) => r.active === false);
  }
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    rules = rules.filter(([id, r]) => {
      if (id.toLowerCase().includes(q)) return true;
      const concDesc = (state.descMap[r.conclusion.replace(/^-/, '')] || '').toLowerCase();
      if (concDesc.includes(q)) return true;
      for (const p of r.premises || []) {
        const pd = (state.descMap[p.replace(/^-/, '')] || '').toLowerCase();
        if (pd.includes(q)) return true;
      }
      return false;
    });
  }

  document.getElementById('rules-count').textContent = String(rules.length);
  if (rules.length === 0) {
    root.innerHTML = `<div class="placeholder-msg">No rules match.</div>`;
    return;
  }

  // Keep category ordering stable with either display preference.
  const groups = {};
  for (const [id, rule] of rules) {
    const cat = rule.category || 'other';
    (groups[cat] ||= []).push([id, rule]);
  }
  const sortedCats = Object.keys(groups).sort();
  if (!state.rulesGrouped) {
    root.innerHTML = sortedCats
      .flatMap(cat => groups[cat].map(([id, r]) => renderRuleCard(id, r)))
      .join('');
  } else {
    root.innerHTML = sortedCats.map(cat => {
      const cards = groups[cat].map(([id, r]) => renderRuleCard(id, r)).join('');
      return `<div class="kb-group">
        <div class="kb-group-title">${categoryBadge(cat)}</div>
        ${cards}
      </div>`;
    }).join('');
  }

  for (const cb of root.querySelectorAll('input.rule-active-toggle')) {
    cb.addEventListener('change', e => {
      const id = e.target.dataset.ruleId;
      const nowActive = e.target.checked;
      const action = nowActive ? 'Unsuspend' : 'Suspend';
      previewAndConfirmToggle(
        { op: 'toggle-rule', id },
        {
          title: `${action} rule?`,
          summary: `<strong>${action}:</strong> rule <span class="inline-id">[${escapeHtml(id)}]</span>`,
        },
      );
    });
  }
  for (const btn of root.querySelectorAll('button.btn-rule-modify')) {
    btn.addEventListener('click', e => {
      openEditModal('modify-rule', e.currentTarget.dataset.editRuleId);
    });
  }
}

// ----------------------------------------------------------------------
// Conflicts view: rebut pairs between defeasible rules and assumptions,
// with a three-way preference radio wired to set-block ops.
// Strict rules and facts are excluded (their blocks can't be reordered).
// Undercuts are NOT shown here because the ABDA engine ignores
// preferences on the undercut test (see ArgumentBuilder.does_attacks):
// the attack always fires as long as the undercut argument exists, so
// preference controls on undercut pairs would be cosmetic.
// ----------------------------------------------------------------------

function detectConflicts() {
  const scn = state.bundle.scenario;
  const rules = scn.rules || {};
  const assumptions = scn.assumptions || {};

  // Collect defeasible rule-like entities (defeasible rules + active
  // assumptions; active assumptions are bodyless defeasible rules
  // concluding their own id).
  const defRuleIds = new Set(
    Object.entries(rules).filter(([, r]) => r.type === 'defeasible').map(([id]) => id),
  );
  const ents = new Map();
  for (const [id, r] of Object.entries(rules)) {
    if (r.type !== 'defeasible') continue;
    ents.set(id, { id, target: 'rule', block: r.block || 1, conclusion: r.conclusion, rule: r, assumption: null });
  }
  for (const [id, a] of Object.entries(assumptions)) {
    ents.set(id, { id, target: 'assumption', block: a.block || 1, conclusion: id, rule: null, assumption: a });
  }

  const rebuts = [];
  const seenRebut = new Set();

  for (const [aid, A] of ents) {
    // Skip undercut-literal-producing entities entirely; their attack on
    // the target rule isn't preference-sensitive and they have no
    // propositional rebut pair to show.
    if (A.conclusion.startsWith('-') && defRuleIds.has(A.conclusion.slice(1))) continue;

    const negConc = A.conclusion.startsWith('-') ? A.conclusion.slice(1) : '-' + A.conclusion;
    const negBase = negConc.startsWith('-') ? negConc.slice(1) : negConc;
    if (defRuleIds.has(negBase)) continue;
    for (const [bid, B] of ents) {
      if (bid === aid) continue;
      if (B.conclusion !== negConc) continue;
      const key = [aid, bid].sort().join('|');
      if (seenRebut.has(key)) continue;
      seenRebut.add(key);
      rebuts.push({ type: 'rebut', a: A, b: B });
    }
  }
  return { rebuts };
}

function renderConflicts(root) {
  const { rebuts } = detectConflicts();
  if (rebuts.length === 0) {
    root.innerHTML = `<div class="placeholder-msg">No rebut conflicts in the current state. Every defeasible rule and assumption sits alone.</div>`;
    return;
  }

  let html = `<div class="kb-group">
    <div class="kb-group-title">Rebuts (${rebuts.length})</div>`;
  for (const c of rebuts) html += renderConflictCard(c, 'rebut');
  html += `</div>`;
  root.innerHTML = html;

  for (const input of root.querySelectorAll('input[data-conflict-op]')) {
    input.addEventListener('change', e => {
      const choice = e.target.value;
      const A = {
        id: e.target.dataset.aId,
        target: e.target.dataset.aTarget,
      };
      const B = {
        id: e.target.dataset.bId,
        target: e.target.dataset.bTarget,
      };
      applyPreferenceChoice(A, B, choice);
    });
  }
}

function renderConflictCard(conflict, kind) {
  const { a, b } = conflict;
  const ba = a.block, bb = b.block;
  const choiceState = ba === bb ? 'same' : (ba > bb ? 'a' : 'b');
  const cardId = `conf-${kind}-${a.id}-${b.id}`;
  const arrow = '↔ rebuts';
  // Only rebuts are surfaced in the Conflicts view (see detectConflicts
  // header): undercuts aren't preference-sensitive in ABDA's engine, so
  // the radios would be cosmetic there.
  const aSide = renderConflictSide(a);
  const bSide = renderConflictSide(b);
  const dataAttrs = `data-a-id="${escapeAttr(a.id)}" data-a-target="${escapeAttr(a.target)}" data-b-id="${escapeAttr(b.id)}" data-b-target="${escapeAttr(b.target)}" data-conflict-op="${kind}"`;
  const radio = (value, label, checked) => `
    <label class="pref-option">
      <input type="radio" name="${cardId}" value="${value}" ${checked ? 'checked' : ''} ${state.readOnly ? 'disabled' : ''} ${dataAttrs}/>
      <span>${label}</span>
    </label>`;
  const aTag = `<span class="inline-id">[${escapeHtml(a.id)}]</span>`;
  const bTag = `<span class="inline-id">[${escapeHtml(b.id)}]</span>`;
  return `<div class="pref-conflict-card">
    <div class="pref-conflict-sides">
      <div class="pref-side pref-side-a ${choiceState==='a' ? 'pref-side-stronger' : ''}">${aSide}</div>
      <div class="pref-vs">${arrow}</div>
      <div class="pref-side pref-side-b ${choiceState==='b' ? 'pref-side-stronger' : ''}">${bSide}</div>
    </div>
    <div class="pref-control">
      ${radio('a',    `Prefer ${aTag}`,      choiceState === 'a')}
      ${radio('same', 'Equal priority',          choiceState === 'same')}
      ${radio('b',    `Prefer ${bTag}`,      choiceState === 'b')}
    </div>
  </div>`;
}

// Render one side of a conflict card: the rule's formal statement for
// rules, or the assumption's natural-language description for
// assumptions. Both get the id shown inline for traceability.
function renderConflictSide(ent) {
  if (ent.target === 'rule' && ent.rule) {
    return `<div class="pref-rule">${renderRuleText(ent.id, ent.rule)}</div>`;
  }
  if (ent.target === 'assumption' && ent.assumption) {
    return `<div class="pref-rule">${escapeHtml(ent.assumption.description || ent.id)} <span class="inline-id">[${escapeHtml(ent.id)}]</span></div>`;
  }
  return `<div class="pref-rule"><span class="inline-id">[${escapeHtml(ent.id)}]</span></div>`;
}

function applyPreferenceChoice(A, B, choice) {
  // Baseline-aware: target canonical blocks so the three radios always
  // land at well-defined states. If the user's choice matches what
  // baseline had, restore the baseline blocks exactly — so round-trips
  // via the Conflicts view leave the scenario bit-for-bit identical to
  // where it started (important for the Explain button's enabled state,
  // which depends on whether the supporting argument has attackers —
  // and that in turn depends on whether blocks are strictly ordered or
  // equal, not just on relative magnitudes).
  const scn = state.bundle.scenario;
  const baseline = state.baseline;
  const blockIn = (src, ent) => {
    const r = ent.target === 'rule' ? src.rules?.[ent.id] : src.assumptions?.[ent.id];
    return (r && r.block) || 1;
  };
  const bla = blockIn(baseline, A);
  const blb = blockIn(baseline, B);
  const baselineChoice = bla === blb ? 'same' : (bla > blb ? 'a' : 'b');
  const ops = [];
  const pushSet = (ent, newBlock) => {
    const cur = blockIn(scn, ent);
    if (cur !== newBlock) ops.push({ op: 'set-block', target: ent.target, id: ent.id, block: newBlock });
  };
  if (choice === baselineChoice) {
    // Revert to baseline blocks exactly.
    pushSet(A, bla);
    pushSet(B, blb);
  } else {
    // Target canonical blocks pivoted around the baseline maximum so
    // repeated clicks produce consistent states.
    const base = Math.max(bla, blb);
    if (choice === 'a') {
      pushSet(A, base + 1);
      pushSet(B, base);
    } else if (choice === 'b') {
      pushSet(A, base);
      pushSet(B, base + 1);
    } else { // 'same'
      pushSet(A, base);
      pushSet(B, base);
    }
  }
  if (ops.length > 0) applyOps(ops);
}

// ----------------------------------------------------------------------

function renderRuleCard(id, rule) {
  const divergent = isRuleModified(id);
  const inactive = rule.active === false;
  const cls = 'rule-card'
    + (divergent ? ' kb-divergent' : '')
    + (inactive ? ' suspended' : '');

  const premiseLits = (rule.premises || []).map(p => renderLiteral(p));
  const conclusionLit = renderLiteral(rule.conclusion);
  const premises = premiseLits.map(escapeHtml).join(' <span class="kw">and</span> ');
  const conclusion = escapeHtml(conclusionLit);
  const connective = rule.type === 'strict' ? 'necessarily' : 'normally';
  const body = premises
    ? `<span class="kw">If</span> ${premises} <span class="kw">then</span> <span class="kw rule-connective" title="${rule.type === 'strict' ? 'Strict: this rule cannot be defeated.' : 'Defeasible: a stronger conflicting argument or an undercut can defeat this rule.'}">${connective}</span> ${conclusion}`
    : `<span class="kw rule-connective" title="${rule.type === 'strict' ? 'Strict: this rule cannot be defeated.' : 'Defeasible: a stronger conflicting argument or an undercut can defeat this rule.'}">${connective}</span> ${conclusion}`;
  const plainBody = premiseLits.length
    ? `If ${premiseLits.join(' and ')} then ${connective} ${conclusionLit}`
    : `${connective} ${conclusionLit}`;

  const checkbox = rule.type === 'defeasible'
    ? `<label class="active-control"><input type="checkbox" class="rule-active-toggle" data-rule-id="${escapeAttr(id)}" ${inactive ? '' : 'checked'} ${state.readOnly ? 'disabled' : ''} aria-label="${inactive ? 'Unsuspend' : 'Suspend'} rule ${escapeAttr(id)}"> ${inactive ? 'Suspended' : 'Active'}</label>`
    : '';
  const info = 'Add this rule to chat';
  const idInline = `<button type="button" class="inline-id element-inspect-link" data-open-element-kind="rule" data-open-element-id="${escapeAttr(id)}" aria-label="Inspect derivations for rule ${escapeAttr(id)}">${escapeHtml(id)}</button>`;

  const badge = !state.rulesGrouped ? categoryBadge(rule.category) : '';
  const editBtn = state.readOnly ? '' : `<button class="btn btn-small btn-rule-modify llm-only" data-edit-rule-id="${escapeAttr(id)}">Modify with AI</button>`;
  return `<div class="${cls}" data-element-kind="rule" data-element-id="${escapeAttr(id)}">
    <div class="rule-body">
      <div class="rule-text">${body}</div>
      <div class="rule-meta">${badge} ${idInline}</div>
    </div>
    <div class="rule-actions">
      <button type="button" class="rule-info" data-context-kind="rule" data-context-id="${escapeAttr(id)}" data-desc="${escapeAttr(plainBody)}" title="${info}" aria-label="Add rule ${escapeAttr(id)} to chat">${AI_CONTEXT_ICON}</button>
      <details class="row-options"><summary aria-label="Actions for rule ${escapeAttr(id)}">⋯</summary><div>
        ${editBtn}
        <button type="button" class="btn btn-small" data-open-element-kind="rule" data-open-element-id="${escapeAttr(id)}">Inspect derivations</button>
        <button type="button" class="btn btn-small" data-copy-rule="${escapeAttr(id)}">Copy ASPIC- line</button>
      </div></details>
      ${checkbox}
    </div>
  </div>`;
}

function renderLiteral(lit) {
  const negated = lit.startsWith('-');
  const base = negated ? lit.slice(1) : lit;
  if (negated && state.negDescMap[base]) return state.negDescMap[base];
  if (state.ruleIds.has(base)) {
    return negated ? `rule ${base} does not apply` : `rule ${base} applies`;
  }
  const desc = state.descMap[base] || base;
  return negated ? `it is not the case that ${desc}` : desc;
}

function switchKBTab(tab) {
  state.kbTab = tab;
  syncToggleButtons('.kb-tab', 'tab', tab);
  renderKB();
}

function filterKB(q) {
  state.searchQuery = q;
  renderKB();
}


/* ── Chat ─────────────────────────────────────────────── */

function resetChatConversation() {
  syncConversationIdentity();
  if (conversationStore.restoring) {
    conversationStore.restoring = false;
    return;
  }
  const draft = chatComposer.snapshot();
  saveConversationDraft();
  const previous = activeConversation();
  if (previous && !previous.messages.length && !previous.draft) {
    state.chatPending = false;
    return;
  }
  newConversationRecord();
  chatComposer.restore(draft);
  saveConversationDraft();
}

async function apiPostChat(scenario_id, diff_ops, messages, signal, context_refs = [], context = null) {
  const project = context ? context.activeProject : state.activeProject;
  const path = project ? `/api/projects/${encodeURIComponent(project.id)}/chat` : '/chat';
  const payload = project
    ? { expected_version: project.version, diff_ops, messages, context_refs, llm: currentLLMOptions() }
    : { scenario_id, diff_ops, messages, context_refs, llm: currentLLMOptions() };
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = apiErrorMessage(body, `POST ${path}: ${r.status}`);
    const err = new Error(msg);
    err.status = r.status;
    err.code = body?.detail?.code || body?.errors?.[0]?.code || null;
    err.billing_uncertain = body?.detail?.billing_uncertain === true;
    throw err;
  }
  return body;
}

function appendAssistantMarkdown(bubble, content) {
  const text = String(content ?? '');
  if (typeof window.marked !== 'undefined' && typeof window.DOMPurify !== 'undefined') {
    try {
      const fragment = window.DOMPurify.sanitize(
        window.marked.parse(text, { breaks: true, gfm: true }),
        {
          ALLOWED_ATTR: CHAT_MARKDOWN_ALLOWED_ATTR,
          ALLOWED_TAGS: CHAT_MARKDOWN_ALLOWED_TAGS,
          RETURN_DOM_FRAGMENT: true,
        }
      );
      fragment.querySelectorAll('a[href]').forEach(anchor => {
        anchor.setAttribute('rel', 'nofollow noopener noreferrer');
        anchor.setAttribute('referrerpolicy', 'no-referrer');
      });
      bubble.append(fragment);
      return;
    } catch {
      // A parser or sanitizer failure must degrade to inert text.
    }
  }
  bubble.classList.add('chat-bubble-plain');
  bubble.textContent = text;
}

function renderChat() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  syncConversationIdentity();
  if (activeProposalRequest && !proposalRequestAccountIsCurrent(activeProposalRequest)) closeEditModal();
  renderConversationControls();
  renderQuestionContext();
  container.replaceChildren();
  if (state.chatMessages.length === 0 && !state.chatPending) {
    const empty = document.createElement('div');
    empty.className = 'chat-empty';
    empty.append('Ask about this scenario, or use ');
    const example = document.createElement('span');
    example.className = 'rule-info-demo';
    example.innerHTML = AI_CONTEXT_ICON;
    empty.append(example, ' beside an item to add it to your message.');
    container.append(empty);
    renderChatAccess();
    return;
  }
  state.chatMessages.forEach((m, index) => {
    const message = document.createElement('div');
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    if (m.role === 'user') {
      message.className = 'chat-msg chat-msg-user';
      appendUserQuestion(bubble, m);
    } else {
      message.className = 'chat-msg chat-msg-assistant';
      if (m.earlier_state) {
        const earlier = document.createElement('p');
        earlier.className = 'chat-response-meta';
        earlier.textContent = 'Answer for the earlier scenario saved with this question.';
        bubble.append(earlier);
      }
      appendAssistantMarkdown(bubble, m.content);
      appendInlineReferenceLinks(bubble, m);
      appendVerifiedEvidence(bubble, m);
      if (m.meta) {
        const meta = document.createElement('div');
        meta.className = 'chat-response-meta';
        meta.textContent = String(m.meta);
        bubble.append(meta);
      }
    }
    message.append(bubble);
    appendConversationTurnControls(message, m, index);
    container.append(message);
  });
  if (state.chatPending) {
    const pending = document.createElement('div');
    const bubble = document.createElement('div');
    pending.className = 'chat-msg chat-msg-assistant chat-msg-loading';
    bubble.className = 'chat-bubble';
    for (let index = 0; index < 3; index += 1) {
      const dot = document.createElement('span');
      dot.className = 'chat-dot';
      bubble.append(dot);
    }
    pending.append(bubble);
    container.append(pending);
  }
  container.scrollTop = container.scrollHeight;
  renderChatAccess();
}

function revealChatForNarrowLayout() {
  if (!window.matchMedia('(max-width: 858px)').matches) return;
  const panel = document.getElementById('right-panel');
  if (!panel) return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  panel.scrollIntoView({
    behavior: reducedMotion ? 'auto' : 'smooth',
    block: 'start',
  });
}

function captureModelViewContext() {
  return {
    bundle: state.bundle,
    diffOps: state.diff_ops,
    scenarioId: state.scenario_id,
    viewKind: state.viewKind,
    activeProject: state.activeProject,
    sharedProject: state.sharedProject,
  };
}

function modelViewContextIsCurrent(context) {
  return (
    state.bundle === context.bundle
    && state.diff_ops === context.diffOps
    && state.scenario_id === context.scenarioId
    && state.viewKind === context.viewKind
    && state.activeProject === context.activeProject
    && state.sharedProject === context.sharedProject
  );
}

function announceChat(text) {
  const announcement = document.getElementById('chat-announcement');
  if (announcement) announcement.textContent = text;
}

// Runtime request handles stay outside persisted conversation records.
const chatRequests = new Map();

function cancelChatRequest(record = activeConversation(), { silent = false } = {}) {
  const request = chatRequests.get(record);
  if (!request || request.cancelled) return;
  request.cancelled = true;
  request.controller.abort();
  chatRequests.delete(record);
  record.pending = false;
  if (request.submitted && request.usesFundedAccess) {
    // Usage already dispatched can settle after the browser closes the request.
    for (const delay of [0, 1500]) window.setTimeout(() => {
      if (request.epoch === conversationStore.epoch && state.authSession.authenticated) refreshTrialBalanceQuietly();
    }, delay);
  }
  if (silent) return;
  if (request.submitted) record.messages.push({ role: 'assistant', content: 'Answer stopped. Your question is retained.',
    snapshot_id: request.snapshotId, local_notice: true });
  if (activeConversation() === record) {
    state.chatPending = false;
    state.chatDegraded = false;
    chatComposer.restoreIfEmpty(request.draft);
    saveConversationDraft();
    renderChat();
    announceChat('Answer stopped. Your question is retained.');
    chatComposer.focus();
  } else if (!record.draft) {
    record.draft = request.draft.text;
    record.draft_segments = structuredClone(request.draft.segments);
    record.context_refs = structuredClone(request.draft.refs);
  }
  persistConversations(record);
  renderConversationControls();
}

async function sendChatMessage(prefilledText) {
  if (state.chatPending || chatComposer.isComposing) return;
  syncConversationIdentity();
  const startingEpoch = conversationStore.epoch;
  await conversationStore.ready;
  await currentScenarioSignature().promise;
  if (state.chatPending || startingEpoch !== conversationStore.epoch) return;
  const accessIssue = llmAccessIssue();
  if (accessIssue) {
    if (accessIssue.tab) openWorkspace(accessIssue.tab);
    showGlobalStatus(accessIssue.message, 'info');
    return;
  }
  const draft = chatComposer.snapshot();
  const text = typeof prefilledText === 'string' ? prefilledText : draft.text;
  if (!text.trim()) return;
  if (hasPendingStateRequest() || !state.bundle) {
    showGlobalStatus('Wait for the scenario to finish updating before sending your question.', 'info');
    return;
  }
  const selectedContext = structuredClone(draft.refs);
  if (selectedContext.length > 24) {
    showGlobalStatus('A question can include up to 24 context items. Remove extra items before asking.', 'info');
    return;
  }
  if (selectedContext.some(ref => !questionContextIsCurrent(ref))) {
    showGlobalStatus('The selected items belong to an earlier scenario state. Use Refresh on each earlier context item, or remove it, before asking. Your draft is unchanged.', 'info');
    return;
  }
  const record = activeConversation();
  const conversation = record.messages;
  const epoch = conversationStore.epoch;
  const requestContext = captureModelViewContext();
  const requestUsesFundedAccess = state.llmAccess.mode !== 'byok';
  const available = () => epoch === conversationStore.epoch && !conversationStore.deleted.has(record.id)
    && conversationStore.records.includes(record);
  const visible = () => available() && activeConversation() === record;
  const request = { controller: new AbortController(), cancelled: false, submitted: false,
    epoch, usesFundedAccess: requestUsesFundedAccess,
    draft: text === draft.text ? draft : { text, refs: selectedContext } };
  chatRequests.set(record, request);
  record.pending = true;
  state.chatPending = true;
  renderChat();
  if (typeof prefilledText === 'string') revealChatForNarrowLayout();
  let snapshotId;
  try {
    const snapshot = await captureConversationSnapshot(requestContext, request.controller.signal);
    if (request.cancelled) return;
    if (!visible() || !modelViewContextIsCurrent(requestContext)) {
      if (available()) showGlobalStatus('The scenario changed while preparing the question. Your draft was retained.', 'info');
      return;
    }
    const comparableSnapshot = JSON.stringify({ ...snapshot, captured_at: null });
    const existingSnapshot = Object.entries(record.snapshots).find(([, prior]) =>
      JSON.stringify({ ...prior, captured_at: null }) === comparableSnapshot);
    snapshotId = existingSnapshot?.[0] || conversationId();
    if (!existingSnapshot) record.snapshots[snapshotId] = snapshot;
    request.snapshotId = snapshotId;
    request.submitted = true;
    conversation.push({ role: 'user', content: text, snapshot_id: snapshotId,
      segments: text === draft.text ? structuredClone(draft.segments) : undefined,
      context_refs: selectedContext.map(({ kind, id }) => ({ kind, id })) });
    if (text === draft.text) chatComposer.clearIfUnchanged(draft);
    saveConversationDraft();
    persistConversations(record);
    renderChat();
    announceChat('Question sent. Waiting for an answer.');
    const messages = conversation.filter(message => !message.local_notice)
      .slice(-CHAT_TURN_CAP).map(message => ({ role: message.role, content: message.content }));
    const resp = await apiPostChat(requestContext.scenarioId, requestContext.diffOps, messages, request.controller.signal,
      selectedContext.map(({ kind, id }) => ({ kind, id })), requestContext);
    if (request.cancelled) return;
    await refreshConversationRecords();
    if (request.cancelled || !available()) return;
    if (resp.billing_source !== 'byok' && state.authSession.authenticated) refreshTrialBalanceQuietly();
    const earlier = !visible() || !modelViewContextIsCurrent(requestContext);
    const source = resp.billing_source === 'byok' ? 'Own key' : 'Funded';
    const cost = resp.cost_microusd > 0 ? `, ${formatUSD(resp.cost_microusd)}` : '';
    const assessment = resp.billing_uncertain ? '. Cost conservatively assessed because complete provider usage was unavailable.' : '';
    conversation.push({ role: 'assistant', content: resp.message,
      meta: `${source}, ${resp.model}${cost}, ${resp.latency_ms} ms${assessment}`,
      snapshot_id: snapshotId, evidence: resp.evidence || [], earlier_state: earlier });
    if (visible()) {
      state.chatDegraded = false;
      announceChat((earlier ? 'Answer for the earlier scenario. ' : '') + resp.message);
    } else {
      record.unread = true;
      conversationStore.notice = `An answer arrived in "${record.title}" for its saved scenario. Select that conversation to read it.`;
      announceChat(conversationStore.notice);
    }
  } catch (e) {
    if (request.cancelled) return;
    await refreshConversationRecords();
    if (request.cancelled || !available()) return;
    if (requestUsesFundedAccess && state.authSession.authenticated) refreshTrialBalanceQuietly();
    const assessment = e.billing_uncertain === true
      ? ' Cost conservatively assessed because complete provider usage was unavailable.' : '';
    conversation.push({ role: 'assistant',
      content: `Chat could not finish: ${e.message}.${assessment} Your question is retained. You can keep exploring the scenario and choose Ask to retry.`,
      snapshot_id: snapshotId, local_notice: true });
    if (visible()) {
      chatComposer.restoreIfEmpty(text === draft.text ? draft : { text, refs: selectedContext });
      state.chatDegraded = e.status === 502 || e.status === 503 || e.status === 504 || !e.status;
      announceChat(`The answer could not finish.${assessment} Your question was retained.`);
    } else record.unread = true;
  } finally {
    // A stopped request may finish after another question has started.
    if (chatRequests.get(record) !== request) return;
    chatRequests.delete(record);
    record.pending = false;
    if (available()) {
      if (visible()) {
        state.chatPending = false;
        saveConversationDraft();
        renderChat();
      }
      persistConversations(record);
      renderConversationControls();
    }
  }
}

// Delegated click handler: any `.rule-info[data-desc]` anywhere in the left
// panel adds an editable reference with its identity without submitting.
// The controls are hidden when LLM mode is disabled.
document.addEventListener('click', (e) => {
  const target = e.target.closest('.rule-info');
  if (!target) return;
  if (document.body.classList.contains('llm-disabled')) return;
  const desc = target.dataset.desc;
  if (!desc) return;
  addQuestionDraft(desc, target.dataset.contextKind, target.dataset.contextId);
});


/* ── Error surface ────────────────────────────────────── */

function showGlobalError(msg) {
  showGlobalStatus(msg, 'error');
}


/* ── Utility ──────────────────────────────────────────── */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(s) {
  return escapeHtml(s);
}

function syncToggleButtons(selector, dataKey, activeValue) {
  document.querySelectorAll(selector).forEach(button => {
    const active = button.dataset[dataKey] === activeValue;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}


/* ── Resize handles ──────────────────────────────────────── */

function initResize() {
  setupColResize('resize-handle', 'left-panel', 30, 85);
  setupColResizeInner('v-resize-top', 'conclusions-panel', 'top-section', 25, 75);
  setupRowResize('h-resize-left', 'top-section', 'left-panel', 15, 75);
  setupRowResizeFromBottom('h-resize-chat', 'chat-input-area', 'right-panel', 10, 50);
}

function setupKeyboardResize(handle, getPct, setPct, minPct, maxPct, orientation, inverted = false) {
  const initialValue = Number(handle.getAttribute('aria-valuenow'));
  let currentPct = Number.isFinite(initialValue) ? initialValue : minPct;
  const updateValue = (measuredPct = getPct()) => {
    if (!Number.isFinite(measuredPct)) return;
    const pct = Math.min(maxPct, Math.max(minPct, measuredPct));
    currentPct = pct;
    handle.setAttribute('aria-valuenow', String(Math.round(pct)));
  };
  handle.addEventListener('keydown', event => {
    const decreaseKey = orientation === 'vertical' ? 'ArrowLeft' : 'ArrowUp';
    const increaseKey = orientation === 'vertical' ? 'ArrowRight' : 'ArrowDown';
    let next = currentPct;
    const step = event.shiftKey ? 10 : 5;
    if (event.key === 'Home') next = minPct;
    else if (event.key === 'End') next = maxPct;
    else if (event.key === decreaseKey) next += inverted ? step : -step;
    else if (event.key === increaseKey) next += inverted ? -step : step;
    else return;
    event.preventDefault();
    next = Math.min(maxPct, Math.max(minPct, next));
    setPct(next);
    updateValue(next);
  });
  updateValue();
  window.addEventListener('resize', () => updateValue());
  return updateValue;
}

function setupColResize(handleId, panelId, minPct, maxPct) {
  const handle = document.getElementById(handleId);
  const panel = document.getElementById(panelId);
  if (!handle || !panel) return;
  let dragging = false;
  const container = panel.parentElement;
  const getPct = () => (panel.getBoundingClientRect().width / container.getBoundingClientRect().width) * 100;
  const setPct = pct => { panel.style.width = pct + '%'; };
  const updateValue = setupKeyboardResize(handle, getPct, setPct, minPct, maxPct, 'vertical');
  handle.addEventListener('mousedown', e => {
    dragging = true;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = container.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    if (pct >= minPct && pct <= maxPct) {
      setPct(pct);
      updateValue(pct);
    }
  });
  document.addEventListener('mouseup', () => {
    if (dragging) {
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
}

function setupColResizeInner(handleId, panelId, containerId, minPct, maxPct) {
  const handle = document.getElementById(handleId);
  const panel = document.getElementById(panelId);
  const container = document.getElementById(containerId);
  if (!handle || !panel || !container) return;
  let dragging = false;
  const getPct = () => (panel.getBoundingClientRect().width / container.getBoundingClientRect().width) * 100;
  const setPct = pct => {
    panel.style.flex = 'none';
    panel.style.width = pct + '%';
  };
  const updateValue = setupKeyboardResize(handle, getPct, setPct, minPct, maxPct, 'vertical');
  handle.addEventListener('mousedown', e => {
    dragging = true;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = container.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    if (pct >= minPct && pct <= maxPct) {
      setPct(pct);
      updateValue(pct);
    }
  });
  document.addEventListener('mouseup', () => {
    if (dragging) {
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
}

function setupRowResize(handleId, panelId, containerId, minPct, maxPct) {
  const handle = document.getElementById(handleId);
  const panel = document.getElementById(panelId);
  const container = document.getElementById(containerId);
  if (!handle || !panel || !container) return;
  let dragging = false;
  const getPct = () => (panel.getBoundingClientRect().height / container.getBoundingClientRect().height) * 100;
  const setPct = pct => {
    panel.style.height = pct + '%';
    panel.style.flexShrink = '0';
  };
  const updateValue = setupKeyboardResize(handle, getPct, setPct, minPct, maxPct, 'horizontal');
  handle.addEventListener('mousedown', e => {
    dragging = true;
    handle.classList.add('dragging');
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = container.getBoundingClientRect();
    const pct = ((e.clientY - rect.top) / rect.height) * 100;
    if (pct >= minPct && pct <= maxPct) {
      setPct(pct);
      updateValue(pct);
    }
  });
  document.addEventListener('mouseup', () => {
    if (dragging) {
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
}

function setupRowResizeFromBottom(handleId, panelId, containerId, minPct, maxPct) {
  const handle = document.getElementById(handleId);
  const panel = document.getElementById(panelId);
  const container = document.getElementById(containerId);
  if (!handle || !panel || !container) return;
  let dragging = false;
  const getPct = () => (panel.getBoundingClientRect().height / container.getBoundingClientRect().height) * 100;
  const setPct = pct => {
    panel.style.flex = 'none';
    panel.style.height = pct + '%';
  };
  const updateValue = setupKeyboardResize(handle, getPct, setPct, minPct, maxPct, 'horizontal', true);
  handle.addEventListener('mousedown', e => {
    dragging = true;
    handle.classList.add('dragging');
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = container.getBoundingClientRect();
    const pct = ((rect.bottom - e.clientY) / rect.height) * 100;
    if (pct >= minPct && pct <= maxPct) {
      setPct(pct);
      updateValue(pct);
    }
  });
  document.addEventListener('mouseup', () => {
    if (dragging) {
      dragging = false;
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
}


/* ================================================================
   View AF — layered graph of the abstract argumentation framework.
   Groups AF arguments by canonical key (top_rule, conclusion) so the
   diagram shows one node per logical argument rather than per Cartesian
   variant. Nodes laid out in horizontal layers by min-max defense depth
   (min-max numbering / Caminada 2015 §3.2), with "inf" (undecided
   and cycle-stuck arguments) rendered as a separate column.

   Colour palette: accepted → blue, rejected → orange, undecided → yellow.
   Edge style: solid for rebut, dashed for undercut. Arrows point from
   attacker to target.
   ================================================================ */

// Scope for the View-Graph modal. 'key' (default) restricts to the
// dialectical neighbourhood of scenario.conclusions; 'all' shows every
// argument conclusion in the AF.
let afScope = 'key';
let afShowIsolated = false;

function wrapGraphLabel(text) {
  const words = String(text).split(/\s+/u).flatMap(word => word.match(/.{1,32}/gu) || []);
  const lines = [''];
  for (const word of words) {
    let line = lines[lines.length - 1];
    if (line && line.length + word.length + 1 > 32) {
      if (lines.length === 3) { lines[2] = lines[2].slice(0, 29) + '...'; break; }
      lines.push(word);
    } else lines[lines.length - 1] = line ? `${line} ${word}` : word;
  }
  return lines;
}

function afControlsHtml(isolatedCount = 0) {
  return `<div class="af-toolbar">
    <div class="af-scope-control" role="group" aria-label="Conclusion graph scope">
      <button type="button" class="af-scope-btn ${afScope === 'key' ? 'active' : ''}" data-af-scope="key" aria-pressed="${afScope === 'key'}">Key conclusions</button>
      <button type="button" class="af-scope-btn ${afScope === 'all' ? 'active' : ''}" data-af-scope="all" aria-pressed="${afScope === 'all'}">All conclusions</button>
      ${afScope === 'all' ? `<label class="state-filter"><input type="checkbox" id="af-show-isolated" ${afShowIsolated ? 'checked' : ''}> Show ${isolatedCount} conclusions without displayed attacks</label>` : ''}
    </div>
    <div class="af-zoom-controls" role="group" aria-label="Conclusion graph zoom">
      <button type="button" class="btn btn-small" data-af-zoom="out" aria-label="Zoom out">−</button>
      <button type="button" class="btn btn-small" data-af-zoom="reset" aria-label="Reset zoom to 100 percent">100%</button>
      <button type="button" class="btn btn-small" data-af-zoom="in" aria-label="Zoom in">+</button>
      <button type="button" class="btn btn-small" data-af-zoom="fit" aria-label="Fit graph to window">Fit</button>
      <span class="af-zoom-readout" id="af-zoom-readout" role="status" aria-live="polite" aria-atomic="true">100%</span>
    </div>
  </div>`;
}

function renderEmptyAF(message, isolatedCount = 0) {
  document.getElementById('af-modal-body').innerHTML = `${afControlsHtml(isolatedCount)}<p class="placeholder-msg">${escapeHtml(message)}</p>`;
  wireAFZoom();
}

function openAFModal() {
  if (!state.bundle) return;
  argumentNavigation = null;
  graphContext = newArgumentNavigation(state.bundle);
  renderAFView();
  openModal('modal-af', '.modal-close');
  // Fit the graph to the available viewport once the modal is painted.
  // computeAFFit() needs non-zero clientWidth/Height on the scroll
  // container, which is only true after the modal becomes visible and
  // the browser has laid it out.
  requestAnimationFrame(() => {
    afZoom = computeAFFit();
    applyAFZoom();
  });
}

function renderAFView() {
  const body = document.getElementById('af-modal-body');
  const bundle = graphContext?.bundle || state.bundle;
  const af = bundle.af;
  const scn = bundle.scenario;
  let args = af.arguments || [];
  let attacks = af.attacks || [];
  if (args.length === 0) {
    renderEmptyAF('No arguments in this state.');
    return;
  }

  // --- Scope filter ---------------------------------------------------------
  // 'key': restrict to the dialectical neighbourhood of the scenario's
  //         key conclusions (every argument concluding a key or its
  //         negation, plus transitive-closure attackers). Removes
  //         fact/assumption-level supports that don't engage in attacks.
  // 'all': include every argument in the AF; only the later isolated-
  //         node filter prunes nodes with no edges.
  if (afScope === 'key') {
    const keyIds = new Set(Object.keys(scn.conclusions || {}));
    const seedIds = new Set(
      args
        .filter(a => {
          const base = a.conclusion.startsWith('-') ? a.conclusion.slice(1) : a.conclusion;
          return keyIds.has(base);
        })
        .map(a => a.id),
    );
    if (seedIds.size === 0) {
      renderEmptyAF('No arguments for a key conclusion in this state. Select All conclusions to inspect other nodes.');
      return;
    }
    const relevant = new Set();
    const frontier = [...seedIds];
    while (frontier.length > 0) {
      const id = frontier.pop();
      if (relevant.has(id)) continue;
      relevant.add(id);
      for (const e of attacks) {
        if (e.to === id && !relevant.has(e.from)) frontier.push(e.from);
      }
    }
    args = args.filter(a => relevant.has(a.id));
    attacks = attacks.filter(e => relevant.has(e.from) && relevant.has(e.to));
  }

  // --- Conclusion-level grouping -------------------------------------------
  // One node per distinct conclusion literal (including rule-undercut
  // literals like -r4). Arguments that share a conclusion -- e.g. r1
  // and rh both conclude hayashi_no_return in Popov -- collapse into
  // a single node. Label aggregates with in > undec > out across all
  // contributing arguments; min_max is the minimum of finite values,
  // else "inf". Carries the full list of contributing rules so the
  // tooltip can surface them.
  const groups = new Map();
  for (const a of args) {
    const key = a.conclusion;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        conclusion: a.conclusion,
        conclusion_nl: a.conclusion_nl,
        rules: [],
        args: [],
      });
    }
    const g = groups.get(key);
    if (!g.rules.includes(a.top_rule)) g.rules.push(a.top_rule);
    g.args.push(a);
  }
  for (const g of groups.values()) {
    const labels = new Set(g.args.map(a => a.label));
    g.label = labels.has('in') ? 'in' : (labels.has('undec') ? 'undec' : 'out');
    const finites = g.args.map(a => a.min_max).filter(v => typeof v === 'number');
    g.min_max = finites.length > 0 ? Math.min(...finites) : 'inf';
  }

  // --- Conclusion-level edges ----------------------------------------------
  // Project an argument-level attack A → B down to Conc(A) → Conc(B) only
  // when the attacker's argument-level label matches the source conclusion
  // node's (aggregated) label AND the target argument's label matches the
  // target node's label. Without this guard the quotient can surface
  // edges that contradict grounded semantics -- e.g. if X has args X1(in)
  // and X2(out), and Y has args Y1(out) and Y2(undec), then Def 11 sets
  // X=in and Y=undec; an argument-level edge X2→Y1 (out→out, fine) gets
  // projected as X→Y, which reads on screen as in→undec and is never a
  // valid grounded configuration. Dropping the projection in that case
  // loses a structural edge but keeps the diagram faithful to the labels
  // the user sees in the Conclusions panel.
  //
  // If both rebut and undercut edges between the same conclusion pair
  // survive the filter, prefer 'rebut' as the semantically direct one.
  const edgeMap = new Map();
  const argConcl = new Map();
  const argLabelById = new Map();
  for (const a of args) {
    argConcl.set(a.id, a.conclusion);
    argLabelById.set(a.id, a.label);
  }
  for (const e of attacks) {
    const sk = argConcl.get(e.from);
    const dk = argConcl.get(e.to);
    if (!sk || !dk) continue;
    const sg = groups.get(sk);
    const dg = groups.get(dk);
    if (!sg || !dg) continue;
    if (argLabelById.get(e.from) !== sg.label) continue;
    if (argLabelById.get(e.to) !== dg.label) continue;
    const pair = sk + '->' + dk;
    const prev = edgeMap.get(pair);
    if (prev === 'rebut') continue;
    edgeMap.set(pair, e.type);
  }

  // All scope explicitly exposes every conclusion group, with an optional
  // counted filter for nodes without displayed attacks. Key scope keeps its
  // unchallenged conclusions visible.
  const participating = new Set();
  for (const pair of edgeMap.keys()) {
    const [sk, dk] = pair.split('->');
    participating.add(sk);
    participating.add(dk);
  }
  const isolated = [...groups.keys()].filter(key => !participating.has(key));
  if (afScope === 'all' && !afShowIsolated) isolated.forEach(key => groups.delete(key));
  if (groups.size === 0) {
    renderEmptyAF(`All ${isolated.length} conclusions are isolated in this view. Enable the checkbox above to inspect them.`, isolated.length);
    return;
  }

  // --- Layer partition ------------------------------------------------------
  // Finite layers: sorted ascending. Layer 1 at the bottom of the diagram.
  // Infinite cluster goes to the right as its own column.
  const finiteLayers = new Map();
  const infGroup = [];
  for (const g of groups.values()) {
    if (g.min_max === 'inf') { infGroup.push(g); continue; }
    if (!finiteLayers.has(g.min_max)) finiteLayers.set(g.min_max, []);
    finiteLayers.get(g.min_max).push(g);
  }
  // Stable sort within each layer by (top_rule, conclusion) so layouts
  // are deterministic across renders.
  const sortKey = (g) => g.top_rule + '::' + g.conclusion;
  for (const layer of finiteLayers.values()) layer.sort((a, b) => sortKey(a).localeCompare(sortKey(b)));
  infGroup.sort((a, b) => sortKey(a).localeCompare(sortKey(b)));

  const depths = [...finiteLayers.keys()].sort((a, b) => a - b);

  // --- Layout via dagre -----------------------------------------------------
  // Dagre handles layered ranking + polyline edge routing. rankdir 'BT'
  // places sources (attackers with no incoming edges) at the bottom and
  // sinks at the top (sources = attackers with no incoming edges).
  const NODE_W = 248, NODE_H = 88;
  if (typeof dagre === 'undefined') {
    renderEmptyAF('Graph layout is unavailable. Reload to try again.', isolated.length);
    return;
  }
  const dg = new dagre.graphlib.Graph();
  dg.setGraph({ rankdir: 'BT', nodesep: 30, ranksep: 55, marginx: 24, marginy: 24 });
  dg.setDefaultEdgeLabel(() => ({}));
  for (const g of groups.values()) dg.setNode(g.key, { width: NODE_W, height: NODE_H });
  for (const [pair, type] of edgeMap) {
    const [sk, dk] = pair.split('->');
    dg.setEdge(sk, dk, { type });
  }
  dagre.layout(dg);
  // Compute the real bounding box including every edge waypoint. Dagre
  // reports `graph().width/height` based on node extents plus margins,
  // but the polyline control points it places for long back-edges can
  // extend beyond that box -- if we used the dagre-reported dimensions
  // as the viewBox, those segments would be drawn outside the canvas
  // and appear to wrap around. Taking the real bounds guarantees every
  // segment stays inside.
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const key of dg.nodes()) {
    const n = dg.node(key);
    minX = Math.min(minX, n.x - n.width / 2);
    minY = Math.min(minY, n.y - n.height / 2);
    maxX = Math.max(maxX, n.x + n.width / 2);
    maxY = Math.max(maxY, n.y + n.height / 2);
  }
  for (const e of dg.edges()) {
    for (const p of (dg.edge(e).points || [])) {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
  }
  const BBOX_PAD = 24;
  minX -= BBOX_PAD; minY -= BBOX_PAD; maxX += BBOX_PAD; maxY += BBOX_PAD;
  const totalWidth = maxX - minX;
  const totalHeight = maxY - minY;
  const graphSummary = (
    `Conclusion graph with ${groups.size} conclusion groups and ${edgeMap.size} projected directed attacks. `
    + 'Activate a node to inspect its individual derivations.'
  );

  // --- Rendering ------------------------------------------------------------
  const fillFor = (label) => ({
    in:    '#eaf2fd',
    out:   '#fff0df',
    undec: '#fff6cf',
  })[label] || '#b0b6c0';
  const textFor = label => ({ in: '#215491', out: '#85480d', undec: '#6b5604' }[label] || '#354152');

  // Build a smooth SVG path from a polyline of points using the classic
  // "quadratic Bezier through midpoints" construction: the curve starts
  // at pts[0], draws a Q segment with each interior point as control,
  // ending at the midpoint of the next pair, then a final L to pts[last].
  // Rounds sharp bends that dagre hands back without introducing wild
  // overshoots.
  const smoothPath = (pts) => {
    if (pts.length < 3) {
      return pts.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
    }
    let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const curr = pts[i], next = pts[i + 1];
      const mx = (curr.x + next.x) / 2;
      const my = (curr.y + next.y) / 2;
      d += ` Q ${curr.x.toFixed(1)},${curr.y.toFixed(1)} ${mx.toFixed(1)},${my.toFixed(1)}`;
    }
    d += ` L ${pts[pts.length - 1].x.toFixed(1)},${pts[pts.length - 1].y.toFixed(1)}`;
    return d;
  };

  // The legend describes projected directions. It does not infer why an
  // edge is absent, which can depend on more than a rule preference.
  const isMutualRebut = (sk, dk, type) => {
    if (type !== 'rebut') return false;
    return edgeMap.get(dk + '->' + sk) === 'rebut';
  };

  let edgeSvg = '';
  for (const e of dg.edges()) {
    const edge = dg.edge(e);
    const pts = edge.points || [];
    if (pts.length < 2) continue;
    // Dagre's last point lies on the target node's border. Pull it back
    // a few pixels along the final segment so the arrowhead has a gap.
    const tail = pts[pts.length - 2];
    const head = pts[pts.length - 1];
    const dx = head.x - tail.x, dy = head.y - tail.y;
    const len = Math.hypot(dx, dy) || 1;
    const back = 4;
    const headAdj = { x: head.x - (dx / len) * back, y: head.y - (dy / len) * back };
    const routed = [...pts.slice(0, -1), headAdj];
    const d = smoothPath(routed);
    const dash = edge.type === 'undercut' ? '6,4' : '';
    const hollow = edge.type === 'rebut' && !isMutualRebut(e.v, e.w, edge.type);
    const marker = hollow ? 'af-arrow-hollow' : 'af-arrow';
    const mutual = isMutualRebut(e.v, e.w, edge.type);
    edgeSvg += `<path d="${d}" stroke="#5a6a78" stroke-width="${mutual ? 4 : 1.8}" stroke-dasharray="${dash}" fill="none" marker-end="url(#${marker})"/>`;
    if (mutual) edgeSvg += `<path d="${d}" stroke="#fff" stroke-width="1.5" fill="none" pointer-events="none"/>`;
  }

  // A conclusion literal `-<name>` where <name> is a rule id is an
  // undercut literal (meta-claim that the rule does not apply here), not
  // a propositional negation. Render it with a ✕ prefix and a dashed
  // node border so it stops looking identical to, say, ¬crispy.
  const ruleIds = new Set(Object.keys(scn.rules || {}));
  const isRuleUndercut = (lit) => lit.startsWith('-') && ruleIds.has(lit.slice(1));
  const NBSP    = '\u00a0';      // keep ✕ and the rule name on the same line
  const formatLiteralLabel = (lit) => {
    if (isRuleUndercut(lit)) return '✕' + NBSP + lit.slice(1);
    return lit;
  };

  let nodeSvg = '';
  for (const key of dg.nodes()) {
    const n = dg.node(key);
    const g = groups.get(key);
    if (!g || !n) continue;
    const x = n.x - n.width / 2;
    const y = n.y - n.height / 2;
    const fill = fillFor(g.label);
    const color = textFor(g.label);
    const undercutNode = isRuleUndercut(g.conclusion);
    const lines = wrapGraphLabel(g.conclusion_nl || g.conclusion);
    const status = { in: 'Accepted', out: 'Rejected', undec: 'Undecided' }[g.label] || g.label;
    // Explicit accessible names avoid the native SVG tooltip duplicating
    // the full conclusion card shown by wireAFTooltip().
    nodeSvg += `<g transform="translate(${x}, ${y})" class="af-node${undercutNode ? ' af-node-undercut' : ''}" role="button" tabindex="0" aria-label="${escapeAttr(`${g.conclusion_nl}; ${status}; ${g.args.length} derivations. Inspect ${g.conclusion}`)}" data-af-concl="${escapeAttr(g.conclusion_nl)}" data-af-label="${escapeAttr(g.label)}" data-af-lit="${escapeAttr(g.conclusion)}" data-af-rules="${escapeAttr(g.rules.join(', '))}">
      <rect width="${NODE_W}" height="${NODE_H}" rx="6" ry="6" fill="${fill}" stroke="${color}" stroke-width="1"/>
      <text x="${NODE_W / 2}" text-anchor="middle" font-size="14" fill="${color}">${lines.map((line, index) => `<tspan x="${NODE_W / 2}" y="${20 + index * 16}">${escapeHtml(line)}</tspan>`).join('')}</text>
      <text x="${NODE_W / 2}" y="74" text-anchor="middle" font-size="12" fill="${color}" font-family="monospace">${escapeHtml(formatLiteralLabel(g.conclusion))}</text>
    </g>`;
  }

  const legend = `<div class="af-legend">
    <span class="af-swatch" style="background:#3a7ad0"></span> Accepted
    <span class="af-swatch" style="background:#e08a3a"></span> Rejected
    <span class="af-swatch" style="background:#e6c94e"></span> Undecided
    <span class="af-edge-symbol af-edge-mutual" aria-hidden="true">⇉</span> Rebut in both directions
    <span class="af-edge-symbol" aria-hidden="true">→</span> One-way rebut
    <span class="af-edge-symbol af-edge-undercut" aria-hidden="true">⇢</span> Undercut
    <span class="af-ucnode-sample" aria-hidden="true">✕ rule</span> Rule does not apply
  </div>`;

  body.innerHTML = `
    ${legend}
    <p class="derivation-note">This overview groups arguments by conclusion and summarizes attacks. Inspect an individual derivation to see every premise, rule, and attack.</p>
    <p class="visually-hidden" id="af-graph-summary">${escapeHtml(graphSummary)}</p>
    ${afControlsHtml(isolated.length)}
    <p class="derivation-note">${groups.size} conclusion groups shown${afScope === 'all' && !afShowIsolated ? `; ${isolated.length} isolated hidden` : ''}. Activate any node to inspect it.</p>
    <div class="af-svg-scroll" id="af-svg-scroll" tabindex="0" role="region" aria-label="Scrollable conclusion graph" aria-describedby="af-graph-summary">
      <svg width="${totalWidth}" height="${totalHeight}" viewBox="${minX} ${minY} ${totalWidth} ${totalHeight}" xmlns="http://www.w3.org/2000/svg" data-base-w="${totalWidth}" data-base-h="${totalHeight}" role="group" aria-label="ABDA-NL conclusion graph" aria-describedby="af-graph-summary">
        <defs>
          <marker id="af-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#5a6a78"/>
          </marker>
          <marker id="af-arrow-hollow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#5a6a78" stroke-width="2.0" stroke-linecap="round" stroke-linejoin="round"/>
          </marker>
        </defs>
        ${edgeSvg}
        ${nodeSvg}
      </svg>
    </div>
    <div class="af-tooltip" id="af-tooltip" style="display:none"></div>
  `;
  afZoom = 1;
  applyAFZoom();
  wireAFZoom();
  wireAFTooltip();
  body.querySelectorAll('.af-node').forEach(node => {
    node.addEventListener('click', () => inspectGraphConclusion(node.dataset.afLit));
    node.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inspectGraphConclusion(node.dataset.afLit); }
    });
  });
}

// Zoom state and controls. Scaling is done by resizing the SVG's width/
// height attributes while the viewBox is unchanged; coordinates inside
// the SVG remain the same. The scroll container (.af-svg-scroll) lets
// the user pan when the scaled diagram overflows.
let afZoom = 1;
function applyAFZoom() {
  const svg = document.querySelector('#af-svg-scroll svg');
  if (!svg) return;
  const w = Number(svg.dataset.baseW);
  const h = Number(svg.dataset.baseH);
  svg.setAttribute('width', (w * afZoom).toFixed(1));
  svg.setAttribute('height', (h * afZoom).toFixed(1));
  const readout = document.getElementById('af-zoom-readout');
  if (readout) readout.textContent = Math.round(afZoom * 100) + '%';
}
function wireAFZoom() {
  const body = document.getElementById('af-modal-body');
  if (!body) return;
  body.querySelector('#af-show-isolated')?.addEventListener('change', event => {
    afShowIsolated = event.target.checked; renderAFView();
    document.getElementById('af-show-isolated')?.focus();
    requestAnimationFrame(() => { afZoom = computeAFFit(); applyAFZoom(); });
  });
  const STEP = 0.15, MIN = 0.25, MAX = 3;
  for (const btn of body.querySelectorAll('[data-af-zoom]')) {
    btn.addEventListener('click', () => {
      const action = btn.dataset.afZoom;
      if (action === 'in')         afZoom = Math.min(MAX, afZoom + STEP);
      else if (action === 'out')   afZoom = Math.max(MIN, afZoom - STEP);
      else if (action === 'reset') afZoom = 1;
      else if (action === 'fit')   afZoom = computeAFFit();
      applyAFZoom();
    });
  }
  // Scope toggle: re-renders the whole view with the new filter, then
  // re-fits so the new graph is sized to the container.
  for (const btn of body.querySelectorAll('[data-af-scope]')) {
    btn.addEventListener('click', () => {
      const next = btn.dataset.afScope;
      if (next === afScope) return;
      afScope = next;
      renderAFView();
      body.querySelector(`[data-af-scope="${next}"]`)?.focus();
      requestAnimationFrame(() => { afZoom = computeAFFit(); applyAFZoom(); });
    });
  }
  // Mouse wheel + Ctrl/Cmd → zoom. Plain wheel scrolls the container.
  const scroll = document.getElementById('af-svg-scroll');
  if (scroll) {
    scroll.addEventListener('wheel', e => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const delta = e.deltaY > 0 ? -STEP : STEP;
      afZoom = Math.min(MAX, Math.max(MIN, afZoom + delta));
      applyAFZoom();
    }, { passive: false });
  }
}
function computeAFFit() {
  const svg = document.querySelector('#af-svg-scroll svg');
  const container = document.getElementById('af-svg-scroll');
  if (!svg || !container) return 1;
  const w = Number(svg.dataset.baseW);
  const h = Number(svg.dataset.baseH);
  // Subtract container padding (.4rem all around ≈ 13px) plus a small
  // breathing margin so nodes at the boundary don't clip against the
  // container edge.
  const availW = container.clientWidth - 24;
  const availH = container.clientHeight - 24;
  if (availW <= 0 || availH <= 0) return 1;
  // Don't scale up past 1.0 on open -- a small graph shouldn't be
  // blown up and pixelated just to fill the viewport. Scale down if
  // the natural size overflows.
  const raw = Math.min(availW / w, availH / h);
  return Math.max(0.25, Math.min(1, raw));
}

// Custom hover tooltip: shows the full conclusion NL (matching the text
// in the Conclusions dashboard) plus the rule id and status lozenge.
// Uses position:fixed so it doesn't care about modal-body scroll.
function wireAFTooltip() {
  const body = document.getElementById('af-modal-body');
  const tip = document.getElementById('af-tooltip');
  if (!body || !tip) return;
  const statusMap = { in: 'Accepted', out: 'Rejected', undec: 'Undecided' };
  const statusClass = { in: 'status-accepted', out: 'status-rejected', undec: 'status-undecided' };
  for (const el of body.querySelectorAll('g.af-node')) {
    el.addEventListener('mouseenter', () => {
      const concl = el.dataset.afConcl || '';
      const label = el.dataset.afLabel || '';
      const rulesCsv = el.dataset.afRules || '';
      const ruleTags = rulesCsv.split(',').map(r => r.trim()).filter(Boolean)
        .map(r => `<span class="inline-id">[${escapeHtml(r)}]</span>`).join(' ');
      tip.innerHTML = `
        <div class="af-tooltip-claim">${escapeHtml(concl)}</div>
        <div class="af-tooltip-meta">
          ${ruleTags}
          <span class="af-tooltip-status ${statusClass[label] || ''}">${escapeHtml(statusMap[label] || label)}</span>
        </div>
      `;
      tip.style.display = 'block';
      // Position to the right of the node; flip left if it would overflow.
      const rect = el.getBoundingClientRect();
      // DOM rectangles include the page's CSS zoom; fixed offsets do not.
      const scale = Number(getComputedStyle(document.documentElement).zoom) || 1;
      const viewportW = window.innerWidth / scale;
      const viewportH = window.innerHeight / scale;
      const tipW = tip.offsetWidth;
      const tipH = tip.offsetHeight;
      let left = rect.right / scale + 10;
      if (left + tipW > viewportW - 8) left = rect.left / scale - tipW - 10;
      let top = rect.top / scale;
      if (top + tipH > viewportH - 8) top = viewportH - tipH - 8;
      tip.style.left = Math.max(8, left) + 'px';
      tip.style.top = Math.max(8, top) + 'px';
    });
    el.addEventListener('mouseleave', () => {
      tip.style.display = 'none';
    });
  }
}

/* ================================================================
   Game Explorer — interactive argument-tree walker
   Opened from the Explain button on a conclusion. User picks one of
   the candidate arguments (filtered by label matching the conclusion
   status), then walks the HTB/CB dialectic by expanding nodes. No
   two-player adversarial play; user expands and backtracks freely.
   Reads everything from state.bundle.af.
   ================================================================ */

// Game-scoped state (reset each time the modal opens).
let gameNodes = {};
let gameNodeCounter = 0;
let gameFocusId = null;
let gameRootId = null;
let gameConclusionId = null;
let gameBundle = null;
// When the conclusion is rejected purely because a strict rule derives its
// negation (no for-argument at all), there is no Caminada game trace to
// play -- we render a prose rationale plus the winning argument card, no
// HTB/CB moves, no "Back to arguments" (picker is skipped upstream).
let gameExplanationOnly = false;
let _renderGuard = 0;

function makeGameNode(type, argId, parentId) {
  const id = 'gn' + (++gameNodeCounter);
  const node = { id, type, argId, parentId, children: [], resolution: null, collapsed: false };
  gameNodes[id] = node;
  return node;
}

// --- AF lookups ------------------------------------------------------

function getArgumentById(argId) {
  return ((gameBundle || state.bundle).af.arguments || []).find(a => a.id === argId);
}

function getAttackersOf(argId) {
  return ((gameBundle || state.bundle).af.attacks || []).filter(a => a.to === argId);
}

function getArgumentsConcluding(conclusionId, bundle = state.bundle) {
  return (bundle.af.arguments || []).filter(a => a.conclusion === conclusionId);
}

// Explain follows individual engine derivations. Sharing a top rule does not
// imply sharing premises, attacks, or a grounded label.
function gameArgumentKey(arg) {
  return arg?.id || '';
}

function getGameAttackerIds(argId) {
  return [...new Set(getAttackersOf(argId).map(edge => edge.from))];
}

// Arguments concluding this proposition that are consistent with the
// aggregated status. Mapping:
//   accepted  → "in" args only
//   rejected  → "out" args only
//   undecided → "out" OR "undec" args (an undecided proposition can
//               never have an "in" arg, but it CAN consist entirely of
//               "out" arguments when no "in" argument for -X exists --
//               e.g. Popov's popov_has_poss under the Cartesian fix.)
//   absent    → no candidates (modal disables Explain upstream)
function getCandidateRootArguments(conclusionId, bundle = state.bundle) {
  const status = bundle.af.labels_by_proposition?.[conclusionId];
  const allowed = {
    accepted: new Set(['in']),
    rejected: new Set(['out']),
    undecided: new Set(['out', 'undec']),
  }[status];
  if (!allowed) return [];
  let matching = getArgumentsConcluding(conclusionId, bundle).filter(a => allowed.has(a.label));
  // Rejected-via-negation fallback: the conclusion has no for-arguments
  // at all (e.g. reached only through a strict rule on -c). Surface the
  // "in" arguments for -c as explainable roots -- walking one of them
  // shows why -c is warranted, which is why c is rejected.
  if (status === 'rejected' && matching.length === 0) {
    matching = getArgumentsConcluding('-' + conclusionId, bundle).filter(a => a.label === 'in');
  }
  return matching;
}

// --- Modal open / close ---------------------------------------------

function openExplainModal(conclusionId, bundle = state.bundle, historical = false, argId = null, navigation = null) {
  if (!bundle) return;
  gameBundle = bundle;
  argumentNavigation = navigation || newArgumentNavigation(bundle, historical);
  if (!navigation) graphContext = null;
  gameConclusionId = conclusionId;
  gameNodes = {};
  gameNodeCounter = 0;
  gameFocusId = null;
  gameRootId = null;
  gameExplanationOnly = false;

  const scn = bundle.scenario;
  const entry = scn.conclusions?.[conclusionId] || scn.propositions?.[conclusionId];
  document.getElementById('game-modal-title').textContent =
    'Explain: ' + (entry ? entry.description : literalInScenario(conclusionId, scn));

  // Route directly to the explanation view when the conclusion is
  // rejected and has no for-arguments (so nothing to walk). The unique
  // in-argument for -c becomes the explanation root.
  const af = bundle.af;
  const status = af.labels_by_proposition?.[conclusionId];
  const forArgs = (af.arguments || []).filter(a => a.conclusion === conclusionId);
  gameExplanationOnly = status === 'rejected' && forArgs.length === 0;
  const candidates = getCandidateRootArguments(conclusionId, bundle);
  const selected = argId ? af.arguments.find(arg => arg.id === argId) : candidates.length === 1 ? candidates[0] : null;
  if (selected) startGameWithRoot(selected.id);
  else renderArgumentPicker();
  openModal('modal-game', '.modal-close');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('visible');
  el.setAttribute('aria-hidden', 'true');
  if (typeof restoreModalFocus === 'function') restoreModalFocus(id);
}

// --- Edit modal: Propose / Refine / Apply for add-rule, modify-rule, add-fact, add-assumption ---

// Per-modal state. Reset on open; cleared on close.
const editState = {
  task: null,              // 'add-rule' | 'modify-rule' | 'add-fact' | 'add-assumption'
  existingId: null,        // for modify-rule
  lastProposal: null,      // most recent {op, review_issues, ...} from /propose
  inFlight: false,
};
let editRequestGeneration = 0;
// Abort handles belong to this modal lifecycle, never to saved scenario or chat data.
let activeProposalRequest = null;

function proposalRequestAccountIsCurrent(request) {
  const account = state.authSession.authenticated ? state.authSession.user?.id || null : null;
  return request.epoch === conversationStore.epoch && request.account === account;
}

function proposalRequestIsCurrent(request) {
  return activeProposalRequest === request && request.generation === editRequestGeneration
    && !request.controller.signal.aborted && proposalRequestAccountIsCurrent(request);
}

function cancelProposalRequest() {
  const request = activeProposalRequest;
  if (!request) return;
  activeProposalRequest = null;
  request.controller.abort();
  if (request.submitted && request.usesFundedAccess) {
    // The server can settle dispatched usage after the browser disconnects.
    for (const delay of [0, 1500]) window.setTimeout(() => {
      if (proposalRequestAccountIsCurrent(request) && state.authSession.authenticated) refreshTrialBalanceQuietly();
    }, delay);
  }
}

function openEditModal(task, existingId = null) {
  if (state.readOnly) {
    showGlobalStatus('Shared scenarios are read-only.', 'info');
    return;
  }
  const accessIssue = llmAccessIssue();
  if (accessIssue) {
    openWorkspace(accessIssue.tab || 'ai');
    showGlobalStatus(accessIssue.message, 'info');
    return;
  }
  cancelProposalRequest();
  editRequestGeneration += 1;
  editState.task = task;
  editState.existingId = existingId;
  editState.lastProposal = null;
  editState.inFlight = false;

  const titles = {
    'add-rule': 'Add Rule',
    'modify-rule': existingId ? `Edit Rule: ${existingId}` : 'Edit Rule',
    'add-fact': 'Add Fact',
    'add-assumption': 'Add Assumption',
  };
  document.getElementById('edit-modal-title').textContent = titles[task] || 'Edit';

  const ta = document.getElementById('edit-instruction');
  ta.value = '';
  const currentRule = document.getElementById('edit-current-rule');
  currentRule.replaceChildren();
  currentRule.hidden = true;
  if (task === 'modify-rule' && existingId) {
    const rule = state.bundle?.scenario?.rules?.[existingId];
    if (rule) {
      currentRule.innerHTML = `<strong>Current rule</strong><p>${renderRuleText(existingId, rule)}</p><code>${escapeHtml(formalElement(existingId, state.bundle.scenario))}</code>`;
      currentRule.hidden = false;
    }
    ta.placeholder = 'Describe the change you want to make.';
  } else {
    ta.placeholder = {
      'add-rule': "e.g. 'Add a rule saying that if X then normally/necessarily Y.'  Use 'normally' for a defeasible rule (can be defeated) or 'necessarily' for a strict rule (cannot be defeated).",
      'add-fact': "e.g. 'Add a fact that the patient is on a chronic PPI.'",
      'add-assumption': "e.g. 'Add an assumption that the witness is treated as reliable.'",
    }[task] || '';
  }

  document.getElementById('edit-instruction-label').textContent =
    task === 'modify-rule'
      ? 'Describe how you want this rule to change:'
      : 'Describe the edit you want:';

  document.getElementById('edit-status').innerHTML = '';
  document.getElementById('edit-preview').innerHTML = '';
  _renderEditFooter();

  openModal('modal-edit', '#edit-instruction');
  setTimeout(() => ta.focus(), 0);
}

function closeEditModal() {
  cancelProposalRequest();
  editRequestGeneration += 1;
  editState.task = null;
  editState.existingId = null;
  editState.lastProposal = null;
  editState.inFlight = false;
  closeModal('modal-edit');
}

async function sendPropose() {
  if (editState.inFlight) return;
  const ta = document.getElementById('edit-instruction');
  const instruction = ta.value.trim();
  if (!instruction) {
    _setEditStatus('error', 'Please describe what you want to edit.');
    return;
  }

  const requestGeneration = ++editRequestGeneration;
  const requestContext = captureModelViewContext();
  const requestUsesFundedAccess = state.llmAccess.mode !== 'byok';
  const request = {
    controller: new AbortController(), generation: requestGeneration,
    epoch: conversationStore.epoch,
    account: state.authSession.authenticated ? state.authSession.user?.id || null : null,
    usesFundedAccess: requestUsesFundedAccess, submitted: false,
  };
  activeProposalRequest = request;
  editState.inFlight = true;
  editState.lastProposal = null;
  _setEditStatus('loading', 'Proposing…');
  document.getElementById('edit-preview').innerHTML = '';
  _renderEditFooter();

  const common = {
    diff_ops: state.diff_ops,
    task: editState.task,
    instruction,
    llm: currentLLMOptions(),
  };
  const project = state.activeProject;
  const path = project ? `/api/projects/${encodeURIComponent(project.id)}/propose` : '/propose';
  const payload = project
    ? { ...common, expected_version: project.version }
    : { ...common, scenario_id: state.scenario_id };
  if (editState.task === 'modify-rule') payload.existing_id = editState.existingId;

  try {
    request.submitted = true;
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: request.controller.signal,
    });
    const body = await r.json().catch(() => ({}));
    if (!proposalRequestIsCurrent(request)) return;
    const responseUsesFundedAccess = body.billing_source
      ? body.billing_source !== 'byok'
      : requestUsesFundedAccess;
    if (responseUsesFundedAccess && state.authSession.authenticated) {
      refreshTrialBalanceQuietly();
    }
    if (!modelViewContextIsCurrent(requestContext)) {
      editState.lastProposal = null;
      document.getElementById('edit-preview').innerHTML = '';
      const assessment = body.billing_uncertain === true || body.detail?.billing_uncertain === true
        ? ' Cost conservatively assessed because complete provider usage was unavailable.' : '';
      _setEditStatus(
        'error',
        `The scenario changed before this proposal arrived. Request a new proposal for the current state.${assessment}`,
      );
      return;
    }
    if (!r.ok) {
      _renderEditError(r.status, body);
      return;
    }
    editState.lastProposal = body;
    _renderProposal(body);
    _setEditStatus('ok', `Proposed in ${body.latency_ms} ms${body.proposer_attempts > 1 ? ` (${body.proposer_attempts} attempts)` : ''}.${body.billing_uncertain ? ' Cost conservatively assessed because complete provider usage was unavailable.' : ''}`);
  } catch (e) {
    if (!proposalRequestIsCurrent(request)) return;
    if (requestUsesFundedAccess && state.authSession.authenticated) {
      refreshTrialBalanceQuietly();
    }
    if (!modelViewContextIsCurrent(requestContext)) {
      editState.lastProposal = null;
      document.getElementById('edit-preview').innerHTML = '';
      _setEditStatus(
        'error',
        'The scenario changed before this proposal arrived. Request a new proposal for the current state.',
      );
      return;
    }
    _setEditStatus('error', `Network error: ${e.message}`);
  } finally {
    if (proposalRequestIsCurrent(request)) {
      activeProposalRequest = null;
      editState.inFlight = false;
      _renderEditFooter();
    }
  }
}

async function applyProposal() {
  if (!editState.lastProposal?.op) return;
  const op = editState.lastProposal.op;
  closeEditModal();
  await applyOp(op);
}

function refineProposal() {
  // Keep the modal open, clear the preview so the user can retype.
  editState.lastProposal = null;
  document.getElementById('edit-preview').innerHTML = '';
  _setEditStatus('', '');
  _renderEditFooter();
  document.getElementById('edit-instruction').focus();
}

function _setEditStatus(kind, msg) {
  const el = document.getElementById('edit-status');
  if (!msg) { el.innerHTML = ''; return; }
  const cls = kind ? `edit-status-${kind}` : '';
  if (kind === 'loading') {
    el.innerHTML = `<div class="${cls}"><span class="edit-loading-label">${escapeHtml(msg)}</span><span class="edit-loading-dots"><span class="chat-dot"></span><span class="chat-dot"></span><span class="chat-dot"></span></span></div>`;
    return;
  }
  el.innerHTML = `<div class="${cls}">${escapeHtml(msg)}</div>`;
}

function _renderEditFooter() {
  const footer = document.getElementById('edit-footer');
  const hasProposal = !!editState.lastProposal?.op;
  if (hasProposal) {
    footer.innerHTML = `
      <button class="btn" data-edit-action="cancel">Cancel</button>
      <button class="btn" data-edit-action="refine">Refine</button>
      <button class="btn btn-primary" data-edit-action="apply">Apply</button>
    `;
  } else {
    const busy = editState.inFlight;
    footer.innerHTML = `
      <button class="btn" data-edit-action="cancel">Cancel</button>
      <button class="btn btn-primary" data-edit-action="propose" ${busy ? 'disabled' : ''}>${busy ? 'Proposing…' : 'Propose'}</button>
    `;
  }
}

function _renderProposal(body) {
  const preview = document.getElementById('edit-preview');
  const op = body.op;
  const kind = op.op;

  let mainHtml = '';
  if (kind === 'add-rule' || kind === 'modify-rule') {
    const rule = op.rule;
    const connective = rule.type === 'strict' ? 'necessarily' : 'normally';
    const proposerNotes = op.new_premise_notes || [];
    const notesById = {};
    for (const n of proposerNotes) notesById[n.id] = n.description;

    // --- NL view (top) ---
    // Use descMap when the literal is already in the scenario; fall
    // back to the Proposer's new_premise_notes description for
    // forward references; last-resort fall back to the bare id so
    // there's always something readable.
    const nlFor = (lit) => {
      const neg = lit.startsWith('-');
      const base = neg ? lit.slice(1) : lit;
      let desc = state.descMap[base];
      if (!desc && notesById[base]) desc = notesById[base];
      if (!desc && state.ruleIds?.has(base)) return neg ? `rule ${base} does not apply` : `rule ${base} applies`;
      if (!desc) desc = base;  // fallback: bare id
      return neg ? `it is not the case that ${desc}` : desc;
    };
    const nlPremises = (rule.premises || []).map(nlFor);
    const nlConclusion = nlFor(rule.conclusion);
    const nlPremisesHtml = nlPremises.map(escapeHtml).join(' <span class="kw">and</span> ');
    const nlBody = nlPremises.length
      ? `<span class="kw">If</span> ${nlPremisesHtml} <span class="kw">then</span> <span class="kw rule-connective" title="${rule.type === 'strict' ? 'Strict: this rule cannot be defeated.' : 'Defeasible: a stronger conflicting argument or an undercut can defeat this rule.'}">${connective}</span> ${escapeHtml(nlConclusion)}`
      : `<span class="kw rule-connective" title="${rule.type === 'strict' ? 'Strict: this rule cannot be defeated.' : 'Defeasible: a stronger conflicting argument or an undercut can defeat this rule.'}">${connective}</span> ${escapeHtml(nlConclusion)}`;

    // --- ASPIC- view (bottom) ---
    const arrow = rule.type === 'strict' ? '->' : '=>';
    const aspicArrow = `<span class="aspic-arrow">${escapeHtml(arrow)}</span>`;
    const aspicLit = (lit) => {
      if (lit.startsWith('-')) {
        return `<span class="aspic-negation">-</span>${escapeHtml(lit.slice(1))}`;
      }
      return escapeHtml(lit);
    };
    const aspicPremises = (rule.premises || []).map(aspicLit).join(', ');
    const aspicConclusion = aspicLit(rule.conclusion);
    const aspicBody = aspicPremises
      ? `${aspicPremises} ${aspicArrow} ${aspicConclusion}`
      : `${aspicArrow} ${aspicConclusion}`;
    const aspicLine = `${aspicBody} <span class="aspic-name">[${escapeHtml(op.id)}]</span>`;

    mainHtml = `
      <div class="edit-prop-heading">${kind === 'add-rule' ? 'Proposed new rule' : 'Proposed updated rule'} <span class="inline-id">[${escapeHtml(op.id)}]</span></div>
      <div class="edit-prop-body">${nlBody}</div>
      <div class="edit-prop-aspic-label">ASPIC- syntax</div>
      <pre class="edit-prop-aspic">${aspicLine}</pre>
    `;
  } else if (kind === 'add-fact' || kind === 'add-assumption') {
    const payload = op.fact || op.assumption;
    // Detect "promotion": this op's id already exists as a pending
    // proposition (declared during a prior rule edit but not yet
    // backed by a fact/assumption/rule). Promoting replaces the
    // pending entry -- the upstream rule that introduced it then
    // becomes firable. Flag this distinctly so the user understands
    // they're not adding a fresh item but fulfilling a forward
    // reference.
    const pending = _pendingPropositionFor(op.id);
    if (pending) {
      const kindLabel = kind === 'add-fact' ? 'fact' : 'assumption';
      mainHtml = `
        <div class="edit-prop-heading edit-prop-promote">Promoting pending item into a ${kindLabel} <span class="inline-id">[${escapeHtml(op.id)}]</span></div>
        <div class="edit-prop-promote-ref">Currently in the scenario as: <em>${escapeHtml(pending.description)}</em></div>
        <div class="edit-prop-body">${escapeHtml(payload.description)}</div>
      `;
    } else {
      mainHtml = `
        <div class="edit-prop-heading">${kind === 'add-fact' ? 'Proposed new fact' : 'Proposed new assumption'} <span class="inline-id">[${escapeHtml(op.id)}]</span></div>
        <div class="edit-prop-body">${escapeHtml(payload.description)}</div>
      `;
    }
  }

  // Show explicit values and removals so postprocessing cannot conceal a change.
  const meta = op.rule || op.fact || op.assumption || {};
  const prior = kind === 'modify-rule' ? state.bundle.scenario.rules?.[op.id] || {} : null;
  const displayValue = (key, value) => key === 'active' && typeof value === 'boolean'
    ? (value ? 'Active' : 'Inactive') : value == null || value === '' ? 'None' : String(value);
  const fields = { category: 'Category', source: 'Source', block: 'Preference block', active: 'Status', negated_description: 'Negated description' };
  const metaBits = Object.entries(fields).filter(([key]) => Object.hasOwn(meta, key) || (prior && Object.hasOwn(prior, key))).map(([key, label]) => {
    const value = displayValue(key, meta[key] ?? ({ active: true, block: 1 }[key]));
    const previous = prior ? displayValue(key, prior[key] ?? ({ active: true, block: 1 }[key])) : '';
    return `${label}: ${prior && previous !== value ? `${escapeHtml(previous)} → ` : ''}${escapeHtml(value)}`;
  });
  const metaHtml = metaBits.length ? `<div class="edit-prop-meta">${metaBits.join(' · ')}</div>` : '';

  // Advisory Reviewer issues.
  let issuesHtml = '';
  if (body.review_issues?.length) {
    const rows = body.review_issues.map(iss => {
      const sev = iss.severity;
      const icon = sev === 'blocker' ? '⛔' : sev === 'warning' ? '⚠' : 'ℹ';
      return `<li class="edit-issue edit-issue-${escapeAttr(sev)}"><span class="edit-issue-icon">${icon}</span><span>${escapeHtml(iss.message)}</span></li>`;
    }).join('');
    issuesHtml = `
      <div class="edit-issues-heading">${body.reviewed === false ? 'Advisory review unavailable. Check the proposal before applying.' : 'Reviewer notes (advisory, you can still Apply):'}</div>
      <ul class="edit-issues">${rows}</ul>
    `;
  }

  preview.innerHTML = mainHtml + metaHtml + issuesHtml;
}

// A proposition is "pending" when it's declared in scenario.propositions
// but has no rule concluding it -- typically a forward-reference
// auto-declared during a prior rule edit. Returns the pending
// proposition entry, or null if `id` isn't pending.
function _pendingPropositionFor(id) {
  const scn = state.bundle?.scenario;
  if (!scn) return null;
  const prop = scn.propositions?.[id];
  if (!prop) return null;
  // Must not also exist as fact / assumption / conclusion / rule
  // (those are never "pending" -- they're already defined).
  if (scn.facts?.[id] || scn.assumptions?.[id] || scn.conclusions?.[id] || scn.rules?.[id]) {
    return null;
  }
  // Must have no rule concluding it. Strip leading '-' when comparing.
  const rules = scn.rules || {};
  for (const r of Object.values(rules)) {
    const c = r.conclusion || '';
    const ref = c.startsWith('-') ? c.slice(1) : c;
    if (ref === id) return null;
  }
  return prop;
}

function _renderEditError(status, body) {
  // Unknown-premise is no longer an error path -- it comes through as a
  // severity=warning review_issue with the op. What remains here is a
  // generic 422 proposer_retry_exhausted (blocking issues the Proposer
  // couldn't fix across 3 attempts) plus other 4xx/5xx.
  const detail = body?.detail;
  const msg = detail?.message || detail || body?.detail || `Error ${status}`;
  const assessment = detail?.billing_uncertain === true
    ? ' Cost conservatively assessed because complete provider usage was unavailable.' : '';
  _setEditStatus('error', (typeof msg === 'string' ? msg : JSON.stringify(msg)) + assessment);
}

// --- Save as new scenario ---------------------------------------------

// Per-modal state. The title/id inputs are live-bound; `idEdited` tracks
// whether the user has manually touched the id field so we stop the
// auto-slug from clobbering their edits on subsequent title keystrokes.
// `overwriteSource` mirrors the checkbox that asks "overwrite current?".
const saveState = {
  idEdited: false,
  inFlight: false,
  overwriteSource: false,
};

function openSaveModal() {
  saveState.idEdited = false;
  saveState.inFlight = false;
  saveState.overwriteSource = false;
  const titleInput = document.getElementById('save-title');
  const idInput = document.getElementById('save-id');
  const overwriteCb = document.getElementById('save-overwrite-source');
  titleInput.value = '';
  idInput.value = '';
  titleInput.disabled = false;
  idInput.disabled = false;
  overwriteCb.checked = false;
  _setSaveSubmitLabel('Save');
  _setSaveStatus('', '');
  _setSaveSubmitEnabled(true);
  openModal('modal-save', '#save-title');
  titleInput.focus();
}

function onSaveOverwriteToggle() {
  const cb = document.getElementById('save-overwrite-source');
  const titleInput = document.getElementById('save-title');
  const idInput = document.getElementById('save-id');
  saveState.overwriteSource = cb.checked;
  if (cb.checked) {
    // Auto-fill with the currently loaded scenario's title and id; lock
    // both fields so the user can't drift mid-flow. The confirm modal on
    // submit is the real guard against accidental overwrite.
    const scn = state.bundle?.scenario;
    titleInput.value = scn?.title || '';
    idInput.value = state.scenario_id || '';
    titleInput.disabled = true;
    idInput.disabled = true;
    _setSaveSubmitLabel('Overwrite');
    _setSaveStatus('', '');
  } else {
    titleInput.value = '';
    idInput.value = '';
    titleInput.disabled = false;
    idInput.disabled = false;
    saveState.idEdited = false;
    _setSaveSubmitLabel('Save');
    _setSaveStatus('', '');
    titleInput.focus();
  }
}

function onSaveTitleInput() {
  if (saveState.idEdited) return;
  const title = document.getElementById('save-title').value;
  document.getElementById('save-id').value = _slugifyScenarioId(title);
}

function onSaveIdInput() {
  // User touched the id field manually; stop mirroring from title.
  saveState.idEdited = true;
}

// Slugify a free-form title into a valid scenario id. Pattern is the
// same identifier regex the server enforces: [A-Za-z_][A-Za-z0-9_]*
function _slugifyScenarioId(title) {
  let slug = title.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
  // Id must start with a letter or underscore; prepend '_' if it starts with a digit.
  if (/^[0-9]/.test(slug)) slug = '_' + slug;
  return slug;
}

async function submitSave(overwrite) {
  if (saveState.inFlight) return;
  const title = document.getElementById('save-title').value.trim();
  const save_as_id = document.getElementById('save-id').value.trim();
  if (!title) { _setSaveStatus('error', 'Please enter a title.'); return; }
  if (!save_as_id) { _setSaveStatus('error', 'Please enter a scenario id.'); return; }

  // Overwrite-source path: the checkbox implies both overwrite=true and
  // the user's intent to replace the current scenario. Route through an
  // explicit confirm modal before actually sending the request.
  if (saveState.overwriteSource && !overwrite) {
    openModal('modal-save-overwrite-confirm', '.modal-footer .btn-primary');
    return;
  }

  saveState.inFlight = true;
  _setSaveSubmitEnabled(false);
  _setSaveStatus('info', 'Saving…');
  try {
    const body = await apiSaveScenario({
      source_id: state.scenario_id,
      diff_ops: state.diff_ops,
      save_as_id,
      title,
      overwrite,
    });
    // Success: refresh switcher, pivot to the saved scenario.
    state.scenarios = await apiListScenarios();
    populateScenarioSelect();
    closeModal('modal-save');
    closeModal('modal-save-collision');
    await loadScenario(body.id);
  } catch (e) {
    if (e.status === 409) {
      closeModal('modal-save');
      _showSaveCollisionModal(save_as_id);
    } else {
      _setSaveStatus('error', e.message || 'Save failed.');
    }
  } finally {
    saveState.inFlight = false;
    _setSaveSubmitEnabled(true);
  }
}

function _showSaveCollisionModal(save_as_id) {
  document.getElementById('save-collision-body').textContent =
    `A scenario with id "${save_as_id}" already exists. Overwrite it, or go back and rename?`;
  openModal('modal-save-collision', '.modal-footer .btn');
}

function onSaveCollisionOverwrite() {
  closeModal('modal-save-collision');
  submitSave(true);
}

function onSaveCollisionRename() {
  closeModal('modal-save-collision');
  // Re-open the save modal; inputs still hold the user's values.
  openModal('modal-save', '#save-id');
  // Mark id as edited so auto-slug doesn't clobber the user's choice.
  saveState.idEdited = true;
  document.getElementById('save-id').focus();
  document.getElementById('save-id').select();
}

function onSaveOverwriteConfirm() {
  // User confirmed via the dedicated overwrite-current-scenario modal.
  // Close the confirm, then re-enter submitSave with overwrite=true so
  // the request goes through without the double-check.
  closeModal('modal-save-overwrite-confirm');
  submitSave(true);
}

function onSaveCollisionCancel() {
  // Reopen the save modal with a status hint so the user can see why the
  // attempt didn't go through, rather than ending up on an unchanged main
  // screen with no feedback.
  closeModal('modal-save-collision');
  openModal('modal-save', '#save-id');
  saveState.idEdited = true;
  _setSaveStatus('info', 'Save canceled. Pick a different id, or close this dialog to abandon.');
}

function _setSaveStatus(kind, msg) {
  const el = document.getElementById('save-status');
  el.className = 'save-status' + (kind ? ' save-status-' + kind : '');
  el.textContent = msg || '';
}

function _setSaveSubmitEnabled(enabled) {
  const btn = document.getElementById('save-submit-btn');
  if (btn) btn.disabled = !enabled;
}

function _setSaveSubmitLabel(label) {
  const btn = document.getElementById('save-submit-btn');
  if (btn) btn.textContent = label;
}

// --- Show ASPIC- modal -------------------------------------------------

function openAspicModal() {
  const scn = state.bundle?.scenario;
  if (!scn) return;
  const text = buildAspicText(scn);
  const pre = document.getElementById('aspic-pre');
  pre.dataset.raw = text;
  pre.innerHTML = text.split('\n').map(highlightAspicLine).join('\n');
  const btn = document.getElementById('aspic-copy-btn');
  btn.textContent = 'Copy';
  btn.classList.remove('copied');
  openModal('modal-aspic', '#aspic-copy-btn');
}

function buildAspicText(scn) {
  const lines = [];
  if (scn.title) lines.push(`# ${scn.title}`);

  // Glossary of propositions (positive names, plus any negated forms that
  // actually appear in rule premises or conclusions, excluding rule-name
  // literals like `-box_softens`).
  const glossary = buildAspicGlossary(scn);
  if (glossary.length > 0) {
    lines.push('');
    lines.push('# Glossary of propositions:');
    for (const { id, text } of glossary) lines.push(glossaryLine(id, text));
  }

  // Facts, grouped by category.
  const factIds = Object.keys(scn.facts || {});
  if (factIds.length > 0) {
    lines.push('', '# Facts');
    for (const [cat, ids] of groupIdsByCategory(factIds, id => scn.facts[id])) {
      lines.push(`# ${cat}`);
      for (const id of ids) lines.push(`-> ${id}`);
    }
  }

  // Assumptions, grouped by category.
  const assumptionIds = Object.keys(scn.assumptions || {});
  if (assumptionIds.length > 0) {
    lines.push('', '# Assumptions');
    for (const [cat, ids] of groupIdsByCategory(assumptionIds, id => scn.assumptions[id])) {
      lines.push(`# ${cat}`);
      for (const id of ids) {
        const data = scn.assumptions[id];
        lines.push(`# Block ${data.block ?? 1}`);
        const mark = (data.active === false) ? '# [suspended] ' : '';
        lines.push(`${mark}=> ${id} [${id}]`);
      }
    }
  }

  // Rules, organised by block, then by category within block.
  const byBlock = new Map();
  for (const [id, r] of Object.entries(scn.rules || {})) {
    const block = r.block ?? 1;
    if (!byBlock.has(block)) byBlock.set(block, []);
    byBlock.get(block).push({ id, data: r });
  }
  const sortedBlocks = [...byBlock.keys()].sort((a, b) => a - b);
  for (const block of sortedBlocks) {
    const label = sortedBlocks.length > 1
      ? (block === sortedBlocks[0] ? ' (weakest)'
         : block === sortedBlocks[sortedBlocks.length - 1] ? ' (strongest)'
         : '')
      : '';
    lines.push('', `# Block ${block}${label}`);
    const byCat = groupIdsByCategory(
      byBlock.get(block).map(it => it.id),
      id => byBlock.get(block).find(it => it.id === id).data
    );
    for (const [cat, ids] of byCat) {
      lines.push(`# ${cat}`);
      for (const id of ids) {
        const { data } = byBlock.get(block).find(it => it.id === id);
        const arrow = data.type === 'strict' ? '->' : '=>';
        const premises = (data.premises || []).join(', ');
        const body = premises ? `${premises} ${arrow} ${data.conclusion}` : `${arrow} ${data.conclusion}`;
        const mark = (data.active === false) ? '# [suspended] ' : '';
        lines.push(`${mark}${body} [${id}]`);
      }
    }
  }

  return lines.join('\n').replace(/\n+$/, '');
}

function groupIdsByCategory(ids, getData) {
  const groups = new Map();
  for (const id of ids) {
    const cat = getData(id).category || 'uncategorized';
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat).push(id);
  }
  return groups;
}

function glossaryLine(id, text) {
  // Right-align so the alphanumeric part of the identifier sits at the same
  // column regardless of a leading '-'. Produces:
  //   #   x = "..."
  //   #  -x = "..."
  const indent = id.startsWith('-') ? ' ' : '  ';
  const escaped = text.replace(/"/g, '\\"');
  return `# ${indent}${id} = "${escaped}"`;
}

function buildAspicGlossary(scn) {
  // Collect which negated literals actually occur in rule premises /
  // conclusions (excluding rule-name undercut literals like `-box_softens`).
  const ruleIds = new Set(Object.keys(scn.rules || {}));
  const negatedUsed = new Set();
  for (const rule of Object.values(scn.rules || {})) {
    for (const p of (rule.premises || [])) {
      if (p.startsWith('-') && !ruleIds.has(p.slice(1))) negatedUsed.add(p);
    }
    const c = rule.conclusion;
    if (c && c.startsWith('-') && !ruleIds.has(c.slice(1))) negatedUsed.add(c);
  }

  const entries = [];
  const seen = new Set();
  const push = (id, text) => {
    if (seen.has(id) || !text) return;
    entries.push({ id, text });
    seen.add(id);
  };
  const addWithNeg = (id, source) => {
    push(id, source.description);
    const neg = `-${id}`;
    if (negatedUsed.has(neg)) {
      push(neg, source.negated_description || `not ${source.description}`);
    }
  };

  for (const [id, f] of Object.entries(scn.facts || {})) addWithNeg(id, f);
  for (const [id, a] of Object.entries(scn.assumptions || {})) addWithNeg(id, a);
  for (const [id, p] of Object.entries(scn.propositions || {})) addWithNeg(id, p);
  for (const [id, c] of Object.entries(scn.conclusions || {})) addWithNeg(id, c);

  return entries;
}

function highlightAspicLine(line) {
  const esc = line
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  if (esc.trimStart().startsWith('#')) {
    return `<span class="aspic-comment">${esc}</span>`;
  }
  // Stash arrows under sentinels so the negation regex doesn't eat the '-' in '->'.
  let out = esc
    .replace(/=&gt;/g, '\x01DEF\x01')
    .replace(/-&gt;/g, '\x01STR\x01');
  out = out
    .replace(/\[([A-Za-z_][A-Za-z0-9_]*)\]/g, '<span class="aspic-name">[$1]</span>')
    .replace(/(^|[\s,])(-)([A-Za-z_])/g, '$1<span class="aspic-negation">$2</span>$3')
    .replace(/\x01DEF\x01/g, '<span class="aspic-arrow">=&gt;</span>')
    .replace(/\x01STR\x01/g, '<span class="aspic-arrow">-&gt;</span>');
  return out;
}

async function copyAspicToClipboard() {
  const pre = document.getElementById('aspic-pre');
  const text = pre.dataset.raw || pre.textContent;
  const btn = document.getElementById('aspic-copy-btn');
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 1500);
  } catch (e) {
    btn.textContent = 'Copy failed';
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
  }
}

// --- Argument picker -------------------------------------------------

function renderArgumentPicker() {
  const body = document.getElementById('game-modal-body');
  const previousFocus = body.contains(document.activeElement) ? document.activeElement : null;
  const candidates = getCandidateRootArguments(gameConclusionId, gameBundle || state.bundle);
  const status = (gameBundle || state.bundle).af.labels_by_proposition?.[gameConclusionId];

  if (candidates.length === 0) {
    body.innerHTML = `<div class="placeholder-msg">No derivation available for this conclusion.</div>`;
    restoreGameFocus(previousFocus);
    return;
  }

  // Detect the rejected-via-negation case: the candidates are "in" args
  // for -c rather than "out" args for c. The main explanation view for
  // this case skips the picker entirely; this branch only fires if that
  // upstream detection misses (e.g. multiple distinct in-args for -c).
  const rejectedViaNeg = status === 'rejected'
    && candidates.every(a => a.conclusion === '-' + gameConclusionId && a.label === 'in');

  const headerByStatus = {
    accepted: 'This conclusion is accepted. Pick a derivation to see why.',
    rejected: rejectedViaNeg
      ? 'This conclusion is rejected. No argument supports it directly; the warranted argument for its negation below explains why.'
      : 'This conclusion is rejected. Pick an argument to see what defeated it.',
    undecided: 'This conclusion is undecided. Pick a derivation to trace the argument chain.',
  };

  body.innerHTML = `
    ${argumentNavigationMarkup('game', null)}
    <div class="game-picker-header">${escapeHtml(headerByStatus[status] || 'Select an argument to explore:')}</div>
    <div class="game-picker-list">
      ${candidates.map((arg, index) => renderPickerCard(arg, index, candidates.length)).join('')}
    </div>
  `;

  for (const card of body.querySelectorAll('.game-picker-card')) {
    card.addEventListener('click', () => startGameWithRoot(card.dataset.argId));
  }
  bindArgumentNavigation(body, 'game', null);
  restoreGameFocus(previousFocus);
}

// A chosen move or collapsed branch replaces its controls. Keep keyboard
// focus on the equivalent control, or on the newly active argument.
function restoreGameFocus(previous) {
  if (!previous || previous.isConnected || document.activeElement !== document.body) return;
  const modal = document.getElementById('modal-game');
  if (!modal.classList.contains('visible') || modal.inert) return;
  const body = document.getElementById('game-modal-body');
  const attribute = previous.hasAttribute('data-toggle-collapse-id') ? 'data-toggle-collapse-id'
    : previous.matches('.game-node-focus[data-focus-id]') ? 'data-focus-id' : null;
  const equivalent = attribute
    ? body.querySelector(`[${attribute}="${CSS.escape(previous.getAttribute(attribute))}"]`) : null;
  const target = equivalent || body.querySelector(`#gnode-${CSS.escape(gameFocusId || '')}`)
    || body.querySelector('.game-picker-card') || modal.querySelector('.modal-close');
  target?.focus({ preventScroll: true });
}

function renderPickerCard(arg, index = 0, total = 1) {
  const rule = (gameBundle || state.bundle).scenario.rules?.[arg.top_rule];
  let ruleLine;
  if (rule) {
    ruleLine = renderRuleText(arg.top_rule, rule, (gameBundle || state.bundle).scenario);
  } else {
    // Fallback for bodyless rules (fact / assumption): render the top rule id only.
    ruleLine = `<span class="inline-id">[${escapeHtml(arg.top_rule)}]</span> ${escapeHtml(arg.conclusion_nl)}`;
  }
  return `<button type="button" class="game-picker-card" data-arg-id="${escapeAttr(arg.id)}">
    <span class="game-picker-meta">Argument ${index + 1} of ${total} · ${escapeHtml(arg.id)}</span>
    <span class="game-picker-rule">${ruleLine}</span>
    <span class="game-picker-premises">${escapeHtml(derivationDescription(arg, gameBundle || state.bundle))}</span>
  </button>`;
}

function renderRuleText(ruleId, rule, scenario = state.bundle.scenario) {
  const premises = (rule.premises || []).map(p => escapeHtml(literalInScenario(p, scenario))).join(' <span class="kw">and</span> ');
  const conclusion = escapeHtml(literalInScenario(rule.conclusion, scenario));
  const connective = rule.type === 'strict' ? 'necessarily' : 'normally';
  const idTag = `<span class="inline-id">[${escapeHtml(ruleId)}]</span>`;
  if (!premises) {
    return `<span class="kw rule-connective" title="${rule.type === 'strict' ? 'Strict: this rule cannot be defeated.' : 'Defeasible: a stronger conflicting argument or an undercut can defeat this rule.'}">${connective}</span> ${conclusion} ${idTag}`;
  }
  return `<span class="kw">If</span> ${premises} <span class="kw">then</span> <span class="kw rule-connective" title="${rule.type === 'strict' ? 'Strict: this rule cannot be defeated.' : 'Defeasible: a stronger conflicting argument or an undercut can defeat this rule.'}">${connective}</span> ${conclusion} ${idTag}`;
}

// --- Tree view -------------------------------------------------------

function startGameWithRoot(argId) {
  gameNodes = {};
  gameNodeCounter = 0;
  const root = makeGameNode('htb', argId, null);
  gameRootId = root.id;
  gameFocusId = root.id;
  renderGame();
}

function renderGame() {
  const body = document.getElementById('game-modal-body');
  const previousFocus = body.contains(document.activeElement) ? document.activeElement : null;
  const rootNode = gameNodes[gameRootId];
  if (!rootNode) { renderArgumentPicker(); return; }
  autoResolveTerminalLeaves();

  if (gameExplanationOnly) {
    body.innerHTML = `
      ${argumentNavigationMarkup('game', rootNode.argId)}
      ${renderRejectionRationale(rootNode)}
      <div class="game-tree">${renderGameNode(rootNode)}</div>
    `;
    bindGameTreeHandlers(body);
    bindArgumentNavigation(body, 'game', rootNode.argId);
    restoreGameFocus(previousFocus);
    return;
  }

  body.innerHTML = `
    ${argumentNavigationMarkup('game', rootNode.argId)}
    <div class="game-toolbar">
      ${getCandidateRootArguments(gameConclusionId, gameBundle || state.bundle).length > 1 ? '<button class="btn btn-small" id="game-back-btn">Back to arguments</button>' : ''}
      <span class="game-role-legend"><span class="game-role-swatch game-bar-htb"></span> Proponent defends the claim. <span class="game-role-swatch game-bar-cb"></span> Opponent challenges it. Labels are computed by ABDA.</span>
    </div>
    <div class="game-main">
      <div class="game-main-left">
        <div class="game-tree">${renderGameNode(rootNode)}</div>
        <div class="game-moves" id="game-moves"></div>
      </div>
    </div>
  `;
  document.getElementById('game-back-btn')?.addEventListener('click', renderArgumentPicker);
  bindArgumentNavigation(body, 'game', rootNode.argId);
  bindGameTreeHandlers(body);
  renderGameMoves();
  restoreGameFocus(previousFocus);
  requestAnimationFrame(() => document.getElementById(`gnode-${gameFocusId}`)?.scrollIntoView({ block: 'nearest' }));
}

// Resolve only terminal leaves. Cycles and unplayed choices remain explicit,
// and propagation uses the existing grounded-game rules.
function autoResolveTerminalLeaves() {
  for (const node of Object.values(gameNodes)) {
    if (node.resolution) continue;
    if (node.type === 'cycle') continue;
    if (node.children.length || getGameCycleAttackers(node).length) continue;
    const hasMoves = (node.type === 'htb' && getGameCBs(node).length > 0) ||
                     (node.type === 'cb'  && getGameHTBs(node).length > 0);
    if (hasMoves) continue;  // still has something to play; not stuck
    // Mirrors resolveGameUncontested / resolveGameUndefended.
    node.resolution = node.type === 'htb' ? 'conceded' : 'uncontested';
    propagateGame(node);
  }
}

// Combined helper called on every focus change. Currently only
// auto-resolves stuck off-path leaves so status badges appear and
// parents can be considered resolved for propagation purposes.
// Auto-collapse is intentionally NOT applied -- the user controls
// collapse manually via the per-node caret.
function tidyOffPath() {
  autoResolveTerminalLeaves();
}

function toggleGameCollapse(nodeId) {
  const node = gameNodes[nodeId];
  if (!node) return;
  node.collapsed = !node.collapsed;
  renderGame();
}

// Prose banner shown above the root argument card when the conclusion is
// rejected because a strict rule on -c stands unchallenged. The argument
// card below carries the rule's natural-language rendering, so the banner
// only says *why* this is a no-game case, not the rule's full text.
function renderRejectionRationale(rootNode) {
  const arg = getArgumentById(rootNode.argId);
  if (!arg) return '';
  const rule = (gameBundle || state.bundle).scenario.rules?.[arg.top_rule];
  const isStrictTop = rule && rule.type === 'strict';

  const ruleRef = `<span class="inline-id">[${escapeHtml(arg.top_rule)}]</span>`;
  const detail = isStrictTop
    ? `The strict rule ${ruleRef} derives its negation (shown below). Strict rules can't be challenged, so this stands.`
    : `The argument below for its negation is warranted, and nothing contests it.`;

  return `<div class="game-rationale">
    <p>This conclusion is <strong>rejected</strong>. No argument supports it directly, so there is no game trace.</p>
    <p>${detail}</p>
  </div>`;
}

function renderGameNode(node) {
  const arg = getArgumentById(node.argId);
  if (!arg) return '';
  const isFocus = (node.id === gameFocusId);
  const activeClass = isFocus ? ' game-node-active' : '';
  const resClass = node.resolution ? ` game-node-${node.resolution}` : '';

  // Cycle leaf
  if (node.type === 'cycle') {
    return `<div class="game-node game-node-cycle${resClass}">
      <div class="game-node-inner">
        <div class="game-node-topbar game-bar-cycle">↺ Cycle. Returns to an argument above.</div>
        <div class="game-node-content">
          <div class="game-node-claim">${escapeHtml(arg.conclusion_nl)}</div>
          <div class="game-node-detail">This creates a circular dependency. All arguments in the cycle are undecided.</div>
        </div>
        <div class="game-node-status"><span class="badge badge-undecided">Undecided</span></div>
      </div>
    </div>`;
  }

  let moveLabel, barClass;
  if (node.type === 'htb') { moveLabel = 'Proponent: Has to be the case:'; barClass = 'game-bar-htb'; }
  else { moveLabel = 'Opponent: Can be the case that:'; barClass = 'game-bar-cb'; }

  // Inline collapse caret. Always shown when this node has children so
  // the user can fold any subtree they want out of the way -- whether
  // or not it's fully resolved. Stops click propagation so toggling
  // doesn't also shift focus to this node.
  let caretBtn = '';
  if (node.children.length > 0) {
    const label = node.collapsed
      ? `▸ Expand (${countDescendants(node)} hidden)`
      : `▾ Collapse`;
    caretBtn = `<button type="button" class="game-topbar-caret" data-toggle-collapse-id="${escapeAttr(node.id)}" aria-expanded="${node.collapsed ? 'false' : 'true'}">${label}</button>`;
  }

  let resBadge = '', resReason = '';
  if (node.resolution === 'conceded')     { resBadge = '<span class="badge badge-accepted">Accepted</span>'; resReason = '<div class="game-node-res-reason">Conceded. No challenges remain.</div>'; }
  else if (node.resolution === 'defeated')   { resBadge = '<span class="badge badge-rejected">Rejected</span>'; resReason = '<div class="game-node-res-reason">Rejected. An undefended challenge stands.</div>'; }
  else if (node.resolution === 'retracted')  { resBadge = '<span class="badge badge-rejected">Rejected</span>'; resReason = '<div class="game-node-res-reason">Retracted. Defense was accepted.</div>'; }
  else if (node.resolution === 'uncontested'){ resBadge = '<span class="badge badge-accepted">Accepted</span>'; resReason = '<div class="game-node-res-reason">Challenge stands. No defense available.</div>'; }
  else if (node.resolution === 'undecided')  { resBadge = '<span class="badge badge-undecided">Undecided</span>'; resReason = '<div class="game-node-res-reason">Undecided. Circular dependency.</div>'; }

  const hasMoves = (node.type === 'htb' && getGameCBs(node).length > 0) ||
                   (node.type === 'cb'  && getGameHTBs(node).length > 0);
  const clickable = !node.resolution || hasMoves;
  const focusControl = clickable
    ? `<button type="button" class="game-node-focus" data-focus-id="${escapeAttr(node.id)}" aria-pressed="${isFocus ? 'true' : 'false'}">${moveLabel}</button>`
    : `<span>${moveLabel}</span>`;

  const ruleText = (() => {
    const rule = (gameBundle || state.bundle).scenario.rules?.[arg.top_rule];
    return rule ? renderRuleText(arg.top_rule, rule, (gameBundle || state.bundle).scenario)
                : `<span class="inline-id">[${escapeHtml(arg.top_rule)}]</span> (fact/assumption)`;
  })();

  // Show supports for sub-arguments that could be attacked at all in the
  // AF -- not just those already attacked in the current game tree. This
  // keeps the set of visible supports stable independent of which branch
  // the user has explored, and matches what the moves panel offers: any
  // sub-argument with at least one incoming attack edge
  // somewhere in the AF is dialectically relevant.
  //
  // Explanation-only mode (rejected-via-strict) and accepted conclusions
  // should show the derivation itself, even when there are no challenges
  // to play through. Other statuses keep the dialectically relevant subset.
  const showFullDerivation = gameExplanationOnly
    || (gameBundle || state.bundle).af.labels_by_proposition?.[gameConclusionId] === 'accepted';
  const attackableIds = showFullDerivation
    ? new Set([arg.id, ...(arg.sub_arguments || [])])
    : getAttackableSubArgIds(node);
  const supports = attackableIds.size > 0 ? generateSupports(arg, attackableIds) : [];
  let supportHtml = '';
  if (supports.length > 0) {
    const sid = 'support-' + node.id;
    supportHtml = `<div class="game-supports">
      <button type="button" class="game-supports-toggle" data-supports-id="${sid}" aria-controls="${sid}" aria-expanded="false">
        <span class="game-supports-arrow" id="arrow-${sid}">▶</span> ${showFullDerivation ? 'Premises and subarguments' : 'Contested premises and subarguments'}:
      </button>
      <div class="game-supports-list" id="${sid}" style="display:none">
        ${supports.map(s => `<div class="game-support-card">
          <div class="game-support-label">${escapeHtml(s.label)}</div>
          <div class="game-support-rules">${s.rules}</div>
          ${s.facts ? `<div class="game-support-facts">${s.facts}</div>` : ''}
        </div>`).join('')}
      </div>
    </div>`;
  }

  let attackInfoHtml = '';
  if (node.type === 'cb' && node.parentId) {
    attackInfoHtml = renderAttackInfo(node);
  }

  let html = `<div class="game-node${resClass}${activeClass}" id="gnode-${node.id}" tabindex="-1" role="group" aria-label="${escapeAttr(moveLabel + ' ' + arg.conclusion_nl)}">
    <div class="game-node-inner">
      <div class="game-node-topbar ${barClass}">${focusControl}${caretBtn}</div>
      <div class="game-node-content">
        ${attackInfoHtml}
        <div class="game-node-claim">${escapeHtml(arg.conclusion_nl)}</div>
        <div class="game-node-rule">${ruleText}</div>
      </div>
      <div class="game-node-status">${resBadge}</div>
    </div>
    ${resReason}
    ${node.resolution && node.children.length === 0 ? opposingDerivationsDisclosureFor(node.argId) : ''}
    ${supportHtml}`;

  if (node.children.length > 0 && !node.collapsed) {
    html += '<div class="game-children">';
    for (const cid of node.children) html += renderGameNode(gameNodes[cid]);
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function isSubtreeResolved(node) {
  if (!node) return false;
  if (node.type === 'cycle') return true;
  if (!node.resolution) return false;
  return node.children.every(cid => isSubtreeResolved(gameNodes[cid]));
}

function countDescendants(node) {
  let n = 0;
  for (const cid of node.children) {
    const c = gameNodes[cid];
    if (!c) continue;
    n += 1 + countDescendants(c);
  }
  return n;
}

function renderAttackInfo(cbNode) {
  const parent = gameNodes[cbNode.parentId];
  if (!parent) return '';
  const edge = ((gameBundle || state.bundle).af.attacks || []).find(a => a.from === cbNode.argId && a.to === parent.argId);
  if (!edge) return '';
  const attacker = getArgumentById(cbNode.argId);
  const parentArg = getArgumentById(parent.argId);
  let desc;
  if (edge.type === 'undercut') {
    const ruleId = (attacker?.conclusion || '').replace(/^-/, '');
    desc = `undercuts rule [${escapeHtml(ruleId)}]`;
  } else {
    desc = 'directly rebuts the conclusion';
  }
  const target = parentArg ? escapeHtml(parentArg.conclusion_nl) : '';
  return `<div class="game-attack-info">Attacks: ${target} <span class="game-attack-type">(${desc})</span></div>`;
}

// Only premises of this derivation with an actual incoming engine edge.
function getAttackableSubArgIds(node) {
  const arg = getArgumentById(node.argId);
  if (!arg) return new Set();
  const targets = new Set(((gameBundle || state.bundle).af.attacks || []).map(edge => edge.to));
  return new Set([arg.id, ...(arg.sub_arguments || [])].filter(id => targets.has(id)));
}

// True iff sub-arg with id `subArgId`, or any of its transitive
// sub-arguments, is in the attackable set.
function isRelevantSupport(subArgId, attackableIds) {
  if (attackableIds.has(subArgId)) return true;
  const s = getArgumentById(subArgId);
  if (!s) return false;
  for (const id of s.sub_arguments || []) {
    if (attackableIds.has(id)) return true;
  }
  return false;
}

function generateSupports(arg, attackableIds) {
  const rules = (gameBundle || state.bundle).scenario.rules || {};
  const topRule = rules[arg.top_rule];
  if (!topRule || !topRule.premises || topRule.premises.length === 0) return [];

  return topRule.premises.map((premLit, i) => {
    const subArgId = arg.premises?.[i];
    if (!subArgId) return null;
    if (!isRelevantSupport(subArgId, attackableIds)) return null;
    const subArg = getArgumentById(subArgId);

    let rulesHtml = '';
    if (subArg) {
      const subRule = rules[subArg.top_rule];
      rulesHtml = subRule
        ? `<div class="support-rule-line">${renderRuleText(subArg.top_rule, subRule, (gameBundle || state.bundle).scenario)}</div>`
        : `<div class="support-rule-line"><span class="inline-id">[${escapeHtml(subArg.top_rule)}]</span> ${escapeHtml(subArg.conclusion_nl)}</div>`;
    }

    let factsHtml = '';
    if (subArg) {
      const factArgs = [subArg, ...(subArg.sub_arguments || []).map(getArgumentById).filter(Boolean)]
        .filter(a => a.is_fact);
      // Dedupe by top_rule id (facts appear once per argument chain).
      const seen = new Set();
      const lines = [];
      for (const fa of factArgs) {
        if (seen.has(fa.top_rule)) continue;
        seen.add(fa.top_rule);
        lines.push(`<span class="inline-id">[${escapeHtml(fa.top_rule)}]</span> ${escapeHtml(fa.conclusion_nl)} <span class="fact-tag">fact</span>`);
      }
      factsHtml = lines.join('<br>');
    }

    return { label: literalInScenario(premLit, (gameBundle || state.bundle).scenario), rules: rulesHtml, facts: factsHtml };
  }).filter(Boolean);
}

// --- Moves panel -----------------------------------------------------

function renderGameMoves() {
  const panel = document.getElementById('game-moves');
  if (!panel) return;
  if (!gameFocusId || !gameNodes[gameFocusId]) {
    panel.innerHTML = '<div class="game-moves-header">Exploration complete</div><div class="game-moves-empty">All branches have been explored.</div>';
    return;
  }

  _renderGuard++;
  if (_renderGuard > 5) {
    _renderGuard = 0;
    panel.innerHTML = '<div class="game-moves-header">Exploration complete</div><div class="game-moves-empty">All branches have been explored.</div>';
    return;
  }

  const node = gameNodes[gameFocusId];

  if (node.resolution) {
    const hasMoves = (node.type === 'htb' && getGameCBs(node).length > 0) ||
                     (node.type === 'cb'  && getGameHTBs(node).length > 0);
    if (!hasMoves) {
      const nextId = findGameOpen(gameNodes[gameRootId]);
      if (nextId && nextId !== gameFocusId) { gameFocusId = nextId; tidyOffPath(); renderGame(); return; }
      panel.innerHTML = '<div class="game-moves-header">Exploration complete</div><div class="game-moves-empty">All branches have been explored.</div>';
      _renderGuard = 0;
      return;
    }
  }
  _renderGuard = 0;

  const byId = (argId) => {
    const a = getArgumentById(argId);
    // Disambiguate: multiple arguments can share a conclusion (different
    // Cartesian-product derivations), so append the arg id as a quiet suffix.
    return a
      ? `${escapeHtml(a.conclusion_nl)} <span class="inline-id">[${escapeHtml(argId)}]</span>`
      : escapeHtml(argId);
  };

  // Backtracking affordance: list every still-open node in the tree that
  // isn't the current focus. Appended to EVERY non-resolving leaf (cycle,
  // uncontested, undefended) and to the main moves list, so the user can
  // jump to any open branch at any depth without having to click through
  // Continue first.
  const otherOpenHtml = () => {
    const allOpen = findAllGameOpen(gameNodes[gameRootId], []);
    const otherOpen = allOpen.filter(n => n.id !== gameFocusId);
    if (otherOpen.length === 0) return '';
    return `<div class="game-other-branches">
      <div class="game-moves-header">Other open branches:</div>
      ${otherOpen.map(n => {
        const action = n.type === 'htb' ? 'Challenge' : 'Defend';
        return `<button type="button" class="game-move-card game-move-other" data-focus-id="${escapeAttr(n.id)}">
          <span class="game-move-label"><em>${action}:</em> ${byId(n.argId)}</span>
        </button>`;
      }).join('')}
    </div>`;
  };

  if (node.type === 'htb') {
    const cbs = getGameCBs(node);
    if (cbs.length === 0) {
      const cyc = getGameCycleAttackers(node);
      if (cyc.length > 0) {
        panel.innerHTML = '<div class="game-moves-header">Cycle detected</div><div class="game-moves-empty">The following challenge creates a cycle.</div>' +
          cyc.map(a => `<button type="button" class="game-move-card" data-cycle-cb="${escapeAttr(a)}" data-parent="${escapeAttr(node.id)}">
            <span class="game-move-type game-bar-cycle">↺</span>
            <span class="game-move-label">${byId(a)} <em class="game-node-dim">(cycle)</em></span>
          </button>`).join('') +
          otherOpenHtml();
        wireMoveCardHandlers(panel);
        return;
      }
      const hasUnresolved = node.children.some(cid => !gameNodes[cid].resolution);
      if (hasUnresolved) {
        const nextId = findGameOpen(node);
        if (nextId && nextId !== node.id) { gameFocusId = nextId; tidyOffPath(); renderGame(); return; }
        // Fallback: unresolved descendants exist but none has moves available --
        // user skipped Continue somewhere. Jump focus to one so they can finish
        // the resolution cascade rather than landing on a dead "Resolving…" panel.
        const stuckId = findStuckUnresolved(node);
        if (stuckId && stuckId !== node.id) { gameFocusId = stuckId; tidyOffPath(); renderGame(); return; }
        panel.innerHTML = '<div class="game-moves-header">Resolving…</div>';
        return;
      }
      const opposingNote = opposingDerivationsDisclosureFor(node.argId);
      panel.innerHTML = '<div class="game-moves-header">No challenges available</div>' +
        '<div class="game-moves-empty">This claim has no remaining challenges. It is accepted.</div>' +
        opposingNote +
        otherOpenHtml() +
        `<div style="margin-top:.5rem"><button class="btn btn-small" data-resolve="uncontested" data-node="${escapeAttr(node.id)}">Continue</button></div>`;
      wireMoveCardHandlers(panel);
      return;
    }
    panel.innerHTML = '<div class="game-moves-header">Challenge this claim:</div>' +
      cbs.map(a => `<button type="button" class="game-move-card" data-move="cb" data-arg="${escapeAttr(a)}" data-parent="${escapeAttr(node.id)}">
        <span class="game-move-type game-bar-cb">Can be the case that:</span>
        <span class="game-move-label">${byId(a)}</span>
      </button>`).join('');
  } else {
    const htbs = getGameHTBs(node);
    if (htbs.length === 0) {
      const cyc = getGameCycleAttackers(node);
      if (cyc.length > 0) {
        panel.innerHTML = '<div class="game-moves-header">Cycle detected</div><div class="game-moves-empty">The following defense creates a cycle.</div>' +
          cyc.map(a => `<button type="button" class="game-move-card" data-cycle-htb="${escapeAttr(a)}" data-parent="${escapeAttr(node.id)}">
            <span class="game-move-type game-bar-cycle">↺</span>
            <span class="game-move-label">${byId(a)} <em class="game-node-dim">(cycle)</em></span>
          </button>`).join('') +
          otherOpenHtml();
        wireMoveCardHandlers(panel);
        return;
      }
      const hasUnresolved = node.children.some(cid => !gameNodes[cid].resolution);
      if (hasUnresolved) {
        const nextId = findGameOpen(node);
        if (nextId && nextId !== node.id) { gameFocusId = nextId; tidyOffPath(); renderGame(); return; }
        // Fallback: unresolved descendants exist but none has moves available --
        // user skipped Continue somewhere. Jump focus to one so they can finish
        // the resolution cascade rather than landing on a dead "Resolving…" panel.
        const stuckId = findStuckUnresolved(node);
        if (stuckId && stuckId !== node.id) { gameFocusId = stuckId; tidyOffPath(); renderGame(); return; }
        panel.innerHTML = '<div class="game-moves-header">Resolving…</div>';
        return;
      }
      const opposingNote = opposingDerivationsDisclosureFor(node.argId);
      panel.innerHTML = '<div class="game-moves-header">No defense available</div>' +
        '<div class="game-moves-empty">This challenge cannot be defended against. It stands.</div>' +
        opposingNote +
        otherOpenHtml() +
        `<div style="margin-top:.5rem"><button class="btn btn-small" data-resolve="undefended" data-node="${escapeAttr(node.id)}">Continue</button></div>`;
      wireMoveCardHandlers(panel);
      return;
    }
    panel.innerHTML = '<div class="game-moves-header">Defend against this challenge:</div>' +
      htbs.map(a => `<button type="button" class="game-move-card" data-move="htb" data-arg="${escapeAttr(a)}" data-parent="${escapeAttr(node.id)}">
        <span class="game-move-type game-bar-htb">Has to be the case:</span>
        <span class="game-move-label">${byId(a)}</span>
      </button>`).join('');
  }

  panel.innerHTML += otherOpenHtml();
  wireMoveCardHandlers(panel);
}

// Moves-panel handlers. Scoped to `root` (the moves panel, or the modal
// body in explanation-only mode) so re-running on a panel repaint won't
// re-attach duplicate handlers on the game tree.
function wireMoveCardHandlers(root) {
  for (const el of root.querySelectorAll('[data-move]')) {
    el.addEventListener('click', () => playGameMove(el.dataset.move, el.dataset.arg, el.dataset.parent));
  }
  for (const el of root.querySelectorAll('[data-cycle-cb]')) {
    el.addEventListener('click', () => playGameCycleMove('cb', el.dataset.cycleCb, el.dataset.parent));
  }
  for (const el of root.querySelectorAll('[data-cycle-htb]')) {
    el.addEventListener('click', () => playGameCycleMove('htb', el.dataset.cycleHtb, el.dataset.parent));
  }
  for (const el of root.querySelectorAll('.game-move-card[data-focus-id]')) {
    el.addEventListener('click', () => setGameFocus(el.dataset.focusId));
  }
  for (const el of root.querySelectorAll('[data-resolve]')) {
    el.addEventListener('click', () => {
      const node = gameNodes[el.dataset.node];
      if (el.dataset.resolve === 'uncontested') resolveGameUncontested(node);
      else if (el.dataset.resolve === 'undefended') resolveGameUndefended(node);
    });
  }
}

// Game-tree handlers (support-toggle, collapse-caret, and
// focus-on-node-click). Bound once per renderGame() so they survive
// even when the moves panel early-returns with "Exploration complete"
// -- previously those early returns skipped wireMoveCardHandlers and
// left the tree without click handlers.
function bindGameTreeHandlers(root) {
  for (const el of root.querySelectorAll('[data-supports-id]')) {
    el.addEventListener('click', e => { e.stopPropagation(); toggleSupports(el.dataset.supportsId); });
  }
  for (const el of root.querySelectorAll('[data-toggle-collapse-id]')) {
    el.addEventListener('click', e => { e.stopPropagation(); toggleGameCollapse(el.dataset.toggleCollapseId); });
  }
  for (const el of root.querySelectorAll('.game-node-focus[data-focus-id]')) {
    el.addEventListener('click', () => setGameFocus(el.dataset.focusId));
  }
}

function setGameFocus(nodeId) {
  gameFocusId = nodeId;
  tidyOffPath();
  renderGame();
}

function toggleSupports(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById('arrow-' + id);
  if (!el || !arrow) return;
  const button = document.querySelector(`[data-supports-id="${CSS.escape(id)}"]`);
  if (el.style.display === 'none') {
    el.style.display = '';
    arrow.textContent = '▼';
    button?.setAttribute('aria-expanded', 'true');
  } else {
    el.style.display = 'none';
    arrow.textContent = '▶';
    button?.setAttribute('aria-expanded', 'false');
  }
}

// --- Move helpers ----------------------------------------------------

function getGameUsedArgumentIds(node) {
  const used = new Set();
  let cur = node;
  while (cur) {
    const arg = getArgumentById(cur.argId);
    if (arg) used.add(gameArgumentKey(arg));
    cur = cur.parentId ? gameNodes[cur.parentId] : null;
  }
  return used;
}

// Relevance rule (grounded semantics): only surface attackers that
// contribute to the target's label under Caminada's game.
//   target IN    → show OUT attackers (why IN: every attacker defeated)
//   target OUT   → show IN attackers  (why OUT: the winning attackers)
//   target UNDEC → show UNDEC attackers (why UNDEC: the tie-makers;
//                  OUT attackers were defeated elsewhere and aren't
//                  why this is undecided)
function getGameMoves(node) {
  const target = getArgumentById(node.argId);
  const attackerIds = getGameAttackerIds(node.argId);
  const usedKeys = getGameUsedArgumentIds(node);
  const childKeys = new Set();
  for (const cid of node.children) {
    const carg = getArgumentById(gameNodes[cid].argId);
    if (carg) childKeys.add(gameArgumentKey(carg));
  }
  const relevantLabel = target && { in: 'out', out: 'in', undec: 'undec' }[target.label];
  return attackerIds.filter(aid => {
    const a = getArgumentById(aid);
    const key = a ? gameArgumentKey(a) : null;
    if (!key || usedKeys.has(key) || childKeys.has(key)) return false;
    if (!relevantLabel) return true;
    return a.label === relevantLabel;
  });
}

// HTB and CB both face the same structural problem: given this node,
// what attackers have not yet appeared in the branch? The
// HTB/CB distinction is semantic, not structural.
function getGameCBs(htbNode)  { return getGameMoves(htbNode); }
function getGameHTBs(cbNode)  { return getGameMoves(cbNode); }

// Find contrary or rule-negating derivations with no incoming engine edge.
// Edge absence alone does not identify a cause such as a rule preference.
function getNonAttackingOpposingDerivations(targetArgId) {
  const af = (gameBundle || state.bundle).af;
  const target = getArgumentById(targetArgId);
  if (!target) return [];
  const negConclusion = target.conclusion.startsWith('-')
    ? target.conclusion.slice(1)
    : '-' + target.conclusion;
  const undercutTarget = '-' + target.top_rule;
  const opposing = (af.arguments || []).filter(
    a => a.conclusion === negConclusion || a.conclusion === undercutTarget
  );
  const actual = new Set(
    (af.attacks || []).filter(e => e.to === targetArgId).map(e => e.from)
  );
  const nonAttacking = opposing.filter(a => !actual.has(a.id));
  const seen = new Set();
  const out = [];
  for (const a of nonAttacking) {
    const k = gameArgumentKey(a);
    if (!seen.has(k)) { seen.add(k); out.push(a); }
  }
  return out;
}

function opposingDerivationsDisclosureFor(argId) {
  const opposing = getNonAttackingOpposingDerivations(argId);
  if (opposing.length === 0) return '';
  const items = opposing.map(a => {
    const rule = (gameBundle || state.bundle).scenario.rules?.[a.top_rule];
    const body = rule
      ? renderRuleText(a.top_rule, rule, (gameBundle || state.bundle).scenario)
      : `<em>"${escapeHtml(a.conclusion_nl)}"</em> <span class="inline-id">[${escapeHtml(a.top_rule)}]</span>`;
    return `<li>${body}</li>`;
  }).join('');
  const lead = opposing.length === 1
    ? 'This opposing derivation has no attack on this argument in the computed framework:'
    : `These ${opposing.length} opposing derivations have no attack on this argument in the computed framework:`;
  return `<div class="game-opposing-disclosure">
    <div class="game-opposing-lead">${lead}</div>
    <ul class="game-opposing-list">${items}</ul>
  </div>`;
}

function getGameCycleAttackers(node) {
  const attackerIds = getGameAttackerIds(node.argId);
  const usedKeys = getGameUsedArgumentIds(node);
  return attackerIds.filter(aid => {
    const a = getArgumentById(aid);
    return a && usedKeys.has(gameArgumentKey(a));
  });
}

function findGameOpen(node) {
  if (!node || node.type === 'cycle') return null;
  for (const cid of node.children) {
    const child = gameNodes[cid];
    const deep = findGameOpen(child);
    if (deep) return deep;
  }
  const hasMoves = (node.type === 'htb' && getGameCBs(node).length > 0) ||
                   (node.type === 'cb'  && getGameHTBs(node).length > 0);
  if (!node.resolution && hasMoves) return node.id;
  return null;
}

// Find any unresolved descendant regardless of move availability. Used
// as a fallback when findGameOpen returns nothing but the subtree still
// has unresolved leaves -- those are "stuck on Continue" nodes (user
// saw a No-defense / No-challenges panel but never clicked Continue).
// Focusing to one lets the user finish the resolution cascade instead
// of landing on a permanent "Resolving…" placeholder.
function findStuckUnresolved(node) {
  if (!node || node.type === 'cycle') return null;
  for (const cid of node.children) {
    const child = gameNodes[cid];
    const deep = findStuckUnresolved(child);
    if (deep) return deep;
  }
  if (!node.resolution) return node.id;
  return null;
}

function findAllGameOpen(node, results) {
  if (!node || node.type === 'cycle') return results;
  for (const cid of node.children) findAllGameOpen(gameNodes[cid], results);
  const hasMoves = (node.type === 'htb' && getGameCBs(node).length > 0) ||
                   (node.type === 'cb'  && getGameHTBs(node).length > 0);
  if (!node.resolution && hasMoves && !results.find(r => r.id === node.id)) results.push(node);
  return results;
}

function playGameMove(type, argId, parentId) {
  const parent = gameNodes[parentId];
  if (!parent) return;
  const child = makeGameNode(type, argId, parentId);
  parent.children.push(child.id);
  gameFocusId = child.id;
  // Playing a new move counts as navigating into a fresh branch; fold
  // any resolved subtrees that are now off the ancestor path. The new
  // child's own subtree is empty, so it isn't affected.
  tidyOffPath();
  renderGame();
}

function playGameCycleMove(type, argId, parentId) {
  const parent = gameNodes[parentId];
  if (!parent) return;
  const child = makeGameNode('cycle', argId, parentId);
  child.resolution = 'undecided';
  parent.children.push(child.id);
  propagateGameUndecided(parent);
  renderGame();
}

function resolveGameUncontested(htbNode) {
  // HTB with no remaining challenges = proponent's claim stands = conceded.
  // (Previously set 'uncontested' here, which is CB terminology and made the
  // propagation cascade classify the parent as defeated instead of retracted.)
  htbNode.resolution = 'conceded';
  propagateGame(htbNode);
  renderGame();
}

function resolveGameUndefended(cbNode) {
  // CB with no defense = challenge stands = uncontested; parent HTB defeated.
  cbNode.resolution = 'uncontested';
  propagateGame(cbNode);
  renderGame();
}

function propagateGameUndecided(node) {
  if (!node) return;
  node.resolution = 'undecided';
  if (node.parentId) propagateGameUndecided(gameNodes[node.parentId]);
}

// Bubble resolutions up the tree using grounded-game semantics.
// Ordering matters: undecided > defeated/uncontested > conceded/retracted.
// An HTB is "conceded" (proponent's claim stands) only when every CB
// available to the opponent has been played and retracted -- if more CBs
// remain unplayed, the node is still under consideration. Same symmetric
// rule for CB "uncontested". Without the "all-exhausted" check, a partial
// walk (e.g., user explored only one of three possible CBs) would falsely
// resolve the root as conceded.
function propagateGame(node) {
  if (!node) return;
  const parent = node.parentId ? gameNodes[node.parentId] : null;

  if (node.type === 'htb') {
    if (node.children.some(cid => gameNodes[cid].resolution === 'undecided')) {
      node.resolution = 'undecided';
    } else if (node.children.some(cid => gameNodes[cid].resolution === 'uncontested')) {
      // Any unanswerable CB defeats the HTB.
      node.resolution = 'defeated';
    } else if (
      node.children.length > 0
      && node.children.every(cid => gameNodes[cid].resolution === 'retracted')
      && getGameCBs(node).length === 0
    ) {
      // Every played CB was defended; no further CBs available.
      node.resolution = 'conceded';
    }
  } else if (node.type === 'cb') {
    if (node.children.some(cid => gameNodes[cid].resolution === 'undecided')) {
      node.resolution = 'undecided';
    } else if (node.children.some(cid => gameNodes[cid].resolution === 'conceded')) {
      // Any successful defense retracts the CB.
      node.resolution = 'retracted';
    } else if (
      node.children.length > 0
      && node.children.every(cid => gameNodes[cid].resolution === 'defeated')
      && getGameHTBs(node).length === 0
    ) {
      // Every played HTB failed; no further defenses available.
      node.resolution = 'uncontested';
    }
  }

  if (parent) propagateGame(parent);
}
