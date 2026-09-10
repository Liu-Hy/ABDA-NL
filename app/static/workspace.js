/* Account, project, AI access, sharing, and MCP controls for ABDA-NL. */

let globalStatusTimer = null;
const modalOpeners = new Map();
const modalStack = [];
const modalBackgroundState = new Map();
let globalStatusGeneration = 0;
let externalLoginRefreshPending = false;
let trialRefreshGeneration = 0;
let projectRefreshGeneration = 0;
let mcpTokenRefreshGeneration = 0;
const projectShareRefreshGenerations = new Map();
const workspaceProjects = { archived: false, archivedProjects: [], shareProject: null, shareExpiry: '7', renameProject: null, account: null };
const accountView = { busy: false, revision: 0, refreshGeneration: 0, refreshNeeded: false };
const accountViewChannel = typeof BroadcastChannel === 'function'
  ? new BroadcastChannel('abda-account-view-updates') : null;

window.addEventListener('pageshow', event => {
  if (event.persisted) window.location.reload();
});

function byId(id) {
  return document.getElementById(id);
}

function dismissGlobalStatus(generation = globalStatusGeneration) {
  if (generation !== globalStatusGeneration) return;
  if (globalStatusTimer) window.clearTimeout(globalStatusTimer);
  globalStatusTimer = null;
  const status = byId('global-status');
  if (status) { status.hidden = true; status.replaceChildren(); }
}

function showGlobalStatus(message, kind = 'info', action = null) {
  const status = byId('global-status');
  if (!status) return;
  const generation = ++globalStatusGeneration;
  status.replaceChildren();
  const text = document.createElement('span');
  text.textContent = message;
  status.append(text);
  status.className = `global-status status-${kind}`;
  status.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  if (action?.label && typeof action.onClick === 'function') {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn btn-small'; button.textContent = action.label;
    button.addEventListener('click', action.onClick);
    status.append(button);
  }
  const dismiss = document.createElement('button');
  dismiss.type = 'button'; dismiss.className = 'status-dismiss'; dismiss.textContent = '×';
  dismiss.setAttribute('aria-label', 'Dismiss notification');
  dismiss.addEventListener('click', () => dismissGlobalStatus(generation));
  status.append(dismiss);
  status.hidden = false;
  if (globalStatusTimer) window.clearTimeout(globalStatusTimer);
  globalStatusTimer = null;
  if (kind !== 'error' && !action) {
    globalStatusTimer = window.setTimeout(() => dismissGlobalStatus(generation), kind === 'success' ? 5000 : 6000);
  }
  return () => dismissGlobalStatus(generation);
}

function setWorkspaceStatus(id, message = '', kind = 'info') {
  const status = byId(id);
  if (!status) return;
  status.textContent = message;
  status.className = `workspace-status${message ? ` status-${kind}` : ''}`;
}

function initModalAccessibility() {
  for (const [index, backdrop] of [...document.querySelectorAll('.modal-backdrop')].entries()) {
    const content = backdrop.querySelector('.modal-content');
    if (!content) continue;
    content.setAttribute('role', content.getAttribute('role') || 'dialog');
    content.setAttribute('aria-modal', 'true');
    const title = content.querySelector('.modal-title');
    if (title) {
      if (!title.id) title.id = `${backdrop.id || `modal-${index}`}-title`;
      content.setAttribute('aria-labelledby', title.id);
    }
    backdrop.setAttribute('aria-hidden', 'true');
    backdrop.inert = true;
    const closeButton = content.querySelector('.modal-close');
    if (closeButton && !closeButton.getAttribute('aria-label')) closeButton.setAttribute('aria-label', 'Close dialog');
    backdrop.addEventListener('mousedown', event => {
      if (event.target === backdrop && topModal() === backdrop) requestCloseModal(backdrop.id);
    });
  }

  document.addEventListener('keydown', event => {
    // Editors and comboboxes may consume Escape before it reaches the dialog.
    if (event.defaultPrevented) return;
    const top = topModal();
    if (!top) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      requestCloseModal(top.id);
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = modalFocusableElements(top);
    if (focusable.length === 0) {
      event.preventDefault();
      top.querySelector('.modal-content')?.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!focusable.includes(document.activeElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  document.addEventListener('focusin', event => {
    const top = topModal();
    if (top && !top.contains(event.target)) focusModal(top);
  });
}

function topModal() { return byId(modalStack[modalStack.length - 1]); }

function syncModalStack() {
  const top = topModal();
  for (const [index, id] of modalStack.entries()) {
    const modal = byId(id);
    modal.style.zIndex = String(100 + index);
    modal.inert = modal !== top;
    modal.setAttribute('aria-hidden', modal === top ? 'false' : 'true');
    modal.querySelector('.modal-content')?.setAttribute('aria-modal', modal === top ? 'true' : 'false');
  }
  for (const element of document.body.children) {
    if (element.matches('.modal-backdrop, script, style, link')) continue;
    if (top) {
      if (!modalBackgroundState.has(element)) modalBackgroundState.set(element, {
        inert: element.inert, hidden: element.getAttribute('aria-hidden'),
      });
      element.inert = true;
      element.setAttribute('aria-hidden', 'true');
    } else if (modalBackgroundState.has(element)) {
      const original = modalBackgroundState.get(element);
      element.inert = original.inert;
      if (original.hidden === null) element.removeAttribute('aria-hidden');
      else element.setAttribute('aria-hidden', original.hidden);
      modalBackgroundState.delete(element);
    }
  }
  document.body.classList.toggle('modal-open', Boolean(top));
}

function focusModal(modal, selector = null) {
  const requested = selector ? [...modal.querySelectorAll(selector)]
    .find(modalControlIsVisible) : null;
  const content = modal.querySelector('.modal-content');
  if (content && !content.hasAttribute('tabindex')) content.tabIndex = -1;
  (requested || modalFocusableElements(modal)[0] || content)?.focus();
}

function modalControlIsVisible(element) {
  if (!element || element.disabled || element.closest('[hidden], [inert]')
      || !element.getClientRects().length || window.getComputedStyle(element).visibility !== 'visible') return false;
  // Closed details can retain descendant geometry. Only their summary is shown.
  for (let details = element.closest('details:not([open])'); details;
    details = details.parentElement?.closest('details:not([open])')) {
    if (details !== element && !details.querySelector(':scope > summary')?.contains(element)) return false;
  }
  return true;
}

function modalFocusableElements(root) {
  const selector = [
    'a[href]:not([hidden])',
    'button:not([disabled]):not([hidden])',
    'input:not([disabled]):not([hidden])',
    'select:not([disabled]):not([hidden])',
    'textarea:not([disabled]):not([hidden])',
    '[contenteditable="true"]:not([hidden])',
    'summary:not([hidden]):not([tabindex="-1"])',
    '[tabindex]:not([tabindex="-1"]):not([hidden])',
  ].join(',');
  return [...root.querySelectorAll(selector)].filter(element => element.tabIndex >= 0 && modalControlIsVisible(element));
}

function openModal(id, focusSelector = null) {
  const modal = byId(id);
  if (!modal) return;
  if (!modal.classList.contains('visible')) modalOpeners.set(id,
    typeof shellModalOpener === 'function' ? shellModalOpener() : document.activeElement);
  const oldIndex = modalStack.indexOf(id);
  if (oldIndex !== -1) modalStack.splice(oldIndex, 1);
  modalStack.push(id);
  modal.classList.add('visible');
  modal.inert = false;
  modal.setAttribute('aria-hidden', 'false');
  focusModal(modal, focusSelector);
  syncModalStack();
  window.setTimeout(() => {
    if (topModal() === modal && !modal.contains(document.activeElement)) focusModal(modal, focusSelector);
  }, 0);
}

function restoreModalFocus(id) {
  const wasTop = topModal()?.id === id;
  const index = modalStack.indexOf(id);
  if (index !== -1) modalStack.splice(index, 1);
  const closed = byId(id);
  if (closed) { closed.inert = true; closed.style.removeProperty('z-index'); }
  const opener = modalOpeners.get(id);
  modalOpeners.delete(id);
  syncModalStack();
  if (!wasTop) return;
  const top = topModal();
  if (opener?.isConnected && opener !== document.body && modalControlIsVisible(opener)
      && (!top || top.contains(opener))) opener.focus();
  else if (top) focusModal(top);
  else byId('workspace-btn')?.focus();
}

function requestCloseModal(id) {
  if (id === 'modal-edit') {
    closeEditModal();
  } else if (id === 'modal-suspend-impact') {
    cancelSuspendImpact();
  } else if (id === 'modal-workspace') {
    clearWorkspaceOneTimeSecrets();
    closeModal(id);
  } else if (id === 'modal-example-review') {
    closeExampleReview();
  } else if (id === 'modal-scenario-materials') {
    closeScenarioMaterials();
  } else {
    closeModal(id);
  }
}

function initWorkspaceUI() {
  byId('save-btn')?.addEventListener('click', saveCurrentWork);

  for (const tab of document.querySelectorAll('[data-workspace-tab]')) {
    tab.addEventListener('click', () => switchWorkspaceTab(tab.dataset.workspaceTab));
    tab.addEventListener('keydown', handleWorkspaceTabKeydown);
  }

  byId('dev-login-form')?.addEventListener('submit', handleDevelopmentLogin);
  byId('logout-form')?.addEventListener('submit', handleLogout);
  byId('account-view-toggle-btn')?.addEventListener('click', toggleAccountView);
  byId('restore-admin-view-btn')?.addEventListener('click', toggleAccountView);
  byId('trial-activate-btn')?.addEventListener('click', activateTrial);
  byId('projects-refresh-btn')?.addEventListener('click', () => refreshProjects());
  byId('project-create-form')?.addEventListener('submit', createProjectFromCurrentView);
  byId('project-list')?.addEventListener('click', handleProjectAction);
  byId('project-list')?.addEventListener('submit', renameProject);
  byId('current-project-card')?.addEventListener('click', handleProjectAction);
  byId('current-project-card')?.addEventListener('change', event => {
    if (event.target.id === 'project-share-expiry') workspaceProjects.shareExpiry = event.target.value;
  });
  for (const id of ['project-list', 'current-project-card']) {
    byId(id)?.addEventListener('keydown', event => {
      const menu = event.target.closest('.project-menu[open]');
      if (event.key !== 'Escape' || !menu) return;
      event.preventDefault(); event.stopPropagation();
      menu.open = false; menu.querySelector('summary').focus();
    });
  }
  for (const [id, archived] of [['projects-active-filter', false], ['projects-archived-filter', true]]) {
    byId(id)?.addEventListener('click', () => { workspaceProjects.archived = archived; refreshProjects(); });
  }

  byId('ai-access-form')?.addEventListener('submit', applyAISettings);
  for (const radio of document.querySelectorAll('input[name="ai-mode"]')) {
    radio.addEventListener('change', toggleAIFormMode);
  }
  byId('funded-profile-select')?.addEventListener('change', updateFundedProfileDescription);
  byId('byok-provider-select')?.addEventListener('change', handleBYOKProviderChange);
  byId('byok-reveal-btn')?.addEventListener('click', () => toggleSecretVisibility('byok-api-key', 'byok-reveal-btn'));
  byId('byok-clear-btn')?.addEventListener('click', clearBYOKKey);

  byId('mcp-token-form')?.addEventListener('submit', createMCPToken);
  byId('mcp-refresh-btn')?.addEventListener('click', () => refreshMCPTokens());
  byId('mcp-token-list')?.addEventListener('click', handleMCPAction);
  byId('mcp-secret-reveal-btn')?.addEventListener('click', () => toggleSecretVisibility('mcp-secret-value', 'mcp-secret-reveal-btn'));
  byId('mcp-secret-copy-btn')?.addEventListener('click', () => copyElementText('mcp-secret-value', 'Token copied.'));
  byId('mcp-codex-copy-btn')?.addEventListener('click', () => copyElementText('mcp-codex-config', 'Codex config copied.'));
  byId('mcp-claude-copy-btn')?.addEventListener('click', () => copyElementText('mcp-claude-command', 'Claude Code command copied.'));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      refreshExternalOIDCLogin();
      if (state.authSession.can_switch_admin_view) refreshAccountView();
    }
  });
  accountViewChannel?.addEventListener('message', event => {
    if (event.data?.type !== 'view-mode-changed') return;
    accountView.revision += 1;
    if (!state.authSession.authenticated) return;
    if (event.data.normal_user_view === true) suppressAdministratorView();
    refreshAccountView();
  });
}

function openWorkspace(tab = 'account', options = {}) {
  switchWorkspaceTab(tab);
  if (options.prepareSave) prepareProjectCreateForm();
  openModal(
    'modal-workspace',
    '.workspace-panel.active input, .workspace-panel.active button, .workspace-panel.active a[href]',
  );
  if (tab === 'projects' && state.authSession.authenticated) refreshProjects({ quiet: true });
  if (tab === 'mcp' && state.authSession.authenticated) refreshMCPTokens({ quiet: true });
}

function switchWorkspaceTab(name) {
  byId('workspace-modal-title').textContent = {
    account: 'Account', projects: 'Manage projects', examples: 'Community examples',
    ai: 'AI access', mcp: 'Agent access',
  }[name] || 'Account';
  if (name === 'examples') refreshExampleSubmissions();
  for (const tab of document.querySelectorAll('[data-workspace-tab]')) {
    const active = tab.dataset.workspaceTab === name;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.tabIndex = active ? 0 : -1;
  }
  for (const panel of document.querySelectorAll('.workspace-panel')) {
    const active = panel.id === `workspace-panel-${name}`;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  }
}

function handleWorkspaceTabKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  const tabs = [...document.querySelectorAll('[data-workspace-tab]:not([hidden])')];
  const current = tabs.indexOf(event.currentTarget);
  let next = current;
  if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
  if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
  if (event.key === 'Home') next = 0;
  if (event.key === 'End') next = tabs.length - 1;
  event.preventDefault();
  switchWorkspaceTab(tabs[next].dataset.workspaceTab);
  tabs[next].focus();
}

function renderAccountUI() {
  if (syncConversationIdentity()) renderChat();
  const session = state.authSession || { authenticated: false, auth_mode: 'disabled' };
  const signedOut = byId('account-signed-out');
  const signedIn = byId('account-signed-in');
  signedOut.hidden = session.authenticated;
  signedIn.hidden = !session.authenticated;

  const oidcLink = byId('oidc-login-link');
  const sharedLoginNote = byId('shared-login-note');
  const devForm = byId('dev-login-form');
  oidcLink.hidden = session.authenticated || session.auth_mode !== 'oidc';
  devForm.hidden = session.authenticated || session.auth_mode !== 'dev';
  if (session.login_url) {
    const next = window.location.pathname;
    oidcLink.href = `${session.login_url}?next=${encodeURIComponent(next)}`;
  }
  const preserveSharedFragment = !session.authenticated
    && session.auth_mode === 'oidc'
    && state.viewKind === 'shared';
  if (preserveSharedFragment) {
    oidcLink.target = '_blank';
    oidcLink.rel = 'noopener';
  } else {
    oidcLink.removeAttribute('target');
    oidcLink.removeAttribute('rel');
  }
  if (sharedLoginNote) sharedLoginNote.hidden = !preserveSharedFragment;

  const user = session.user;
  if (user) {
    byId('account-display-name').textContent = user.display_name || 'ABDA-NL researcher';
    byId('account-email').textContent = user.email;
  }
  renderAccountView();

  byId('projects-signin-required').hidden = session.authenticated;
  byId('projects-authenticated').hidden = !session.authenticated;
  byId('mcp-signin-required').hidden = session.authenticated;
  byId('mcp-authenticated').hidden = !session.authenticated;
  renderTrialUI();
  renderProjectsUI();
  renderMCPTokens();
  renderChatAccess();
  renderScenarioLibraryAccess();
  renderCurationAccess();
  if (typeof renderShellControls === 'function') renderShellControls();
}

async function authSessionForCurrentView(session, revision) {
  // A mode change can arrive while another request delays initial page setup
  // or while a sign-in response is still being read. Recheck the shared cookie.
  while (revision !== accountView.revision) {
    revision = accountView.revision;
    session = await apiRequest('/api/auth/session');
  }
  return session;
}

function renderAccountView() {
  const session = state.authSession;
  const available = Boolean(session.authenticated && session.can_switch_admin_view);
  const normal = available && session.normal_user_view === true;
  const restoreHadFocus = document.activeElement === byId('restore-admin-view-btn');
  byId('account-view-card').hidden = !available;
  byId('normal-user-view-indicator').hidden = !normal;
  byId('restore-admin-view-btn').hidden = !normal;
  byId('restore-admin-view-btn').disabled = accountView.busy;
  byId('account-view-toggle-btn').disabled = accountView.busy;
  byId('account-view-toggle-btn').textContent = normal ? 'Restore administrator view' : 'Demonstrate as a normal user';
  byId('account-view-heading').textContent = normal ? 'Normal user view' : 'Administrator view';
  byId('account-view-description').textContent = 'The review queue and Publish as example are hidden in normal user view. Your suggestions go through review. Projects, credit, and conversations are unchanged.';
  if (restoreHadFocus && !normal) byId('workspace-btn').focus();
  if (typeof renderShellControls === 'function') renderShellControls();
}

function suppressAdministratorView() {
  if (!state.authSession.scenario_admin) return;
  // Stop displaying privileged content before a downgrade request settles.
  // The server remains authoritative for all permissions.
  state.authSession = { ...state.authSession, scenario_admin: false };
  renderAccountUI();
}

function applyAccountViewSession(session, account) {
  if (state.authSession.user?.id !== account) return false;
  if (!session.authenticated || session.user?.id !== account) {
    clearCurationState();
    window.location.reload();
    return false;
  }
  const changed = Boolean(session.scenario_admin) !== Boolean(state.authSession.scenario_admin)
    || Boolean(session.normal_user_view) !== Boolean(state.authSession.normal_user_view);
  state.authSession = session;
  renderAccountUI();
  if (changed && !byId('workspace-panel-examples').hidden) refreshExampleSubmissions();
  return true;
}

async function refreshAccountView() {
  if (!state.authSession.authenticated) return;
  if (accountView.busy) { accountView.refreshNeeded = true; return; }
  const generation = ++accountView.refreshGeneration;
  const account = state.authSession.user?.id;
  try {
    const session = await apiRequest('/api/auth/session');
    if (generation === accountView.refreshGeneration) applyAccountViewSession(session, account);
  } catch {
    // A failed refresh never restores privileges hidden by a mode change.
  }
}

async function toggleAccountView(event) {
  if (accountView.busy || !state.authSession.authenticated || !state.authSession.can_switch_admin_view) return;
  const trigger = event?.currentTarget;
  const account = state.authSession.user.id;
  const normal = state.authSession.normal_user_view !== true;
  accountView.busy = true;
  accountView.revision += 1;
  accountView.refreshGeneration += 1;
  if (normal) suppressAdministratorView();
  renderAccountView();
  setWorkspaceStatus('account-view-status', 'Changing account view...', 'info');
  try {
    const session = await apiRequest('/api/auth/view-mode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ normal_user_view: normal }),
    });
    if (!applyAccountViewSession(session, account)) return;
    accountViewChannel?.postMessage({ type: 'view-mode-changed', normal_user_view: session.normal_user_view === true });
    const message = session.normal_user_view ? 'Normal user view is active.' : 'Administrator view restored.';
    setWorkspaceStatus('account-view-status', message, 'success');
    showGlobalStatus(message, 'success');
  } catch (error) {
    if (state.authSession.user?.id === account) {
      setWorkspaceStatus('account-view-status', error.message, 'error');
      accountView.refreshNeeded = true;
    }
  } finally {
    accountView.busy = false;
    renderAccountView();
    if (accountView.refreshNeeded) { accountView.refreshNeeded = false; await refreshAccountView(); }
    if (trigger && state.authSession.user?.id === account
        && (document.activeElement === trigger || document.activeElement === document.body)) {
      (trigger.isConnected && modalControlIsVisible(trigger)
        ? trigger : byId('workspace-btn')).focus();
    }
  }
}

async function refreshExternalOIDCLogin() {
  if (
    externalLoginRefreshPending
    || state.authSession.authenticated
    || state.authSession.auth_mode !== 'oidc'
  ) return;
  externalLoginRefreshPending = true;
  const revision = accountView.revision;
  try {
    const response = await apiRequest('/api/auth/session');
    const session = await authSessionForCurrentView(response, revision);
    if (!session.authenticated || state.authSession.authenticated) return;
    state.authSession = session;
    renderAccountUI();
    await refreshAuthenticatedWorkspace({ quiet: true });
    showGlobalStatus('Signed in. You can now create, import, and save private projects.', 'success');
  } catch (_error) {
    // Returning to an offline or still-signed-out tab requires no error banner.
  } finally {
    externalLoginRefreshPending = false;
  }
}

async function handleDevelopmentLogin(event) {
  event.preventDefault();
  const email = byId('dev-login-email').value.trim();
  const displayName = byId('dev-login-name').value.trim();
  if (!email) return;
  setWorkspaceStatus('account-status', 'Signing in locally...', 'info');
  const revision = accountView.revision;
  try {
    const session = await apiRequest('/api/auth/dev/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, display_name: displayName || null }),
    });
    state.authSession = await authSessionForCurrentView(session, revision);
    setWorkspaceStatus('account-status', '', 'info');
    renderAccountUI();
    await refreshAuthenticatedWorkspace({ quiet: true });
    showGlobalStatus('Signed in to the local development workspace.', 'success');
  } catch (error) {
    setWorkspaceStatus('account-status', error.message, 'error');
  }
}

async function handleLogout(event) {
  event.preventDefault();
  saveConversationDraft();
  setWorkspaceStatus('account-status', 'Signing out...', 'info');
  resetBYOKKey();
  clearWorkspaceOneTimeSecrets();
  resetScenarioBuilder();
  clearScenarioPreview();
  clearCurationState();
  clearScenarioMaterials();
  try {
    const result = await apiRequest('/api/auth/logout', { method: 'POST' });
    if (!result?.logout_url) throw new Error('The sign-out destination is unavailable.');
    state.authSession = { authenticated: false, auth_mode: state.authSession.auth_mode, user: null };
    syncConversationIdentity();
    renderChat();
    window.location.assign(result.logout_url);
  } catch (error) {
    setWorkspaceStatus('account-status', error.message, 'error');
  }
}

async function refreshAuthenticatedWorkspace(options = {}) {
  if (!state.authSession.authenticated) {
    renderAccountUI();
    return;
  }
  const trialGeneration = ++trialRefreshGeneration;
  const projectGeneration = ++projectRefreshGeneration;
  const account = state.authSession.user?.id;
  const trialRequest = apiRequest('/api/trial').then(
    trial => {
      if (trialGeneration !== trialRefreshGeneration || account !== state.authSession.user?.id) return null;
      state.trial = trial;
      renderAccountUI();
      renderAccessSummary();
      return null;
    },
    error => error,
  );
  const projectsRequest = apiRequest('/api/projects').then(
    projects => {
      if (projectGeneration !== projectRefreshGeneration || account !== state.authSession.user?.id) return null;
      state.projects = projects.projects || [];
      renderAccountUI();
      renderAccessSummary();
      return null;
    },
    error => error,
  );
  const [trialError, projectsError] = await Promise.all([
    trialRequest,
    projectsRequest,
  ]);
  if (account !== state.authSession.user?.id) return;
  const currentFailures = [];
  if (trialError && trialGeneration === trialRefreshGeneration) currentFailures.push(trialError);
  if (projectsError && projectGeneration === projectRefreshGeneration) currentFailures.push(projectsError);
  if (currentFailures.length > 0 && !options.quiet) {
    const error = currentFailures[0];
    showGlobalStatus(error?.message || 'The private workspace could not be fully refreshed.', 'error');
  }
}

function formatUSD(microusd) {
  const value = Number(microusd || 0) / 1000000;
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(value);
}

function renderTrialUI() {
  const trial = state.trial;
  const activate = byId('trial-activate-btn');
  const balance = byId('trial-balance');
  if (!state.authSession.authenticated || !trial) {
    activate.hidden = false;
    balance.hidden = true;
    return;
  }
  activate.hidden = trial.active;
  balance.hidden = !trial.active;
  if (!trial.active) return;
  byId('trial-balance-label').textContent = `${formatUSD(trial.available_microusd)} available`;
  byId('trial-spent-label').textContent = `${formatUSD(trial.spent_microusd)} used`;
  const percent = trial.granted_microusd > 0
    ? Math.max(0, Math.min(100, Math.round((trial.available_microusd / trial.granted_microusd) * 100)))
    : 0;
  byId('trial-meter-fill').style.width = `${percent}%`;
  const meter = byId('trial-meter-fill').parentElement;
  meter.setAttribute('aria-valuenow', String(percent));
  meter.setAttribute('aria-valuetext', `${formatUSD(trial.available_microusd)} of ${formatUSD(trial.granted_microusd)} remaining`);
}

async function activateTrial() {
  const button = byId('trial-activate-btn');
  trialRefreshGeneration += 1;
  button.disabled = true;
  setWorkspaceStatus('trial-status', 'Activating trial credit...', 'info');
  try {
    const activated = await apiRequest('/api/trial/activate', { method: 'POST' });
    trialRefreshGeneration += 1;
    state.trial = activated;
    renderTrialUI();
    renderAccessSummary();
    setWorkspaceStatus('trial-status', `${formatUSD(state.trial.granted_microusd)} of trial credit is active.`, 'success');
  } catch (error) {
    trialRefreshGeneration += 1;
    refreshTrialBalanceQuietly();
    setWorkspaceStatus('trial-status', error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function refreshTrialBalanceQuietly() {
  if (!state.authSession.authenticated) return;
  const requestGeneration = ++trialRefreshGeneration;
  try {
    const trial = await apiRequest('/api/trial');
    if (requestGeneration !== trialRefreshGeneration) return;
    state.trial = trial;
    renderTrialUI();
    renderAccessSummary();
  } catch (_error) {
    // The completed model response remains useful if a balance refresh fails.
  }
}

function initializeLLMAccess(config) {
  const profiles = config.profiles || [];
  state.llmAccess.profile = profiles.some(item => item.id === config.default_profile)
    ? config.default_profile
    : profiles[0]?.id || null;
  const provider = (config.byok_providers || [])[0] || null;
  state.llmAccess.provider = provider?.id || null;
  state.llmAccess.model = provider?.default_model || provider?.models?.[0]?.id || null;
}

function renderAISettings() {
  const config = state.config;
  if (!config) return;
  const profileSelect = byId('funded-profile-select');
  profileSelect.innerHTML = '';
  for (const profile of config.profiles || []) {
    const option = document.createElement('option');
    option.value = profile.id;
    option.textContent = profile.display_name;
    profileSelect.appendChild(option);
  }
  profileSelect.value = state.llmAccess.profile || '';
  updateFundedProfileDescription();

  const providerSelect = byId('byok-provider-select');
  providerSelect.innerHTML = '';
  for (const provider of config.byok_providers || []) {
    const option = document.createElement('option');
    option.value = provider.id;
    option.textContent = provider.display_name;
    providerSelect.appendChild(option);
  }
  providerSelect.value = state.llmAccess.provider || providerSelect.options[0]?.value || '';
  populateBYOKModels(state.llmAccess.model);
  byId('byok-api-key').value = state.llmAccess.apiKey || '';
  byId('byok-choice-card').hidden = !config.byok_enabled;
  if (!config.byok_enabled && state.llmAccess.mode === 'byok') state.llmAccess.mode = 'funded';
  const selectedMode = state.llmAccess.mode;
  const radio = document.querySelector(`input[name="ai-mode"][value="${selectedMode}"]`);
  if (radio) radio.checked = true;
  toggleAIFormMode();
}

function updateFundedProfileDescription() {
  const id = byId('funded-profile-select')?.value;
  const profile = (state.config?.profiles || []).find(item => item.id === id);
  byId('funded-profile-description').textContent = profile?.description || '';
}

function populateBYOKModels(preferred = null) {
  const providerId = byId('byok-provider-select')?.value;
  const provider = (state.config?.byok_providers || []).find(item => item.id === providerId);
  const modelSelect = byId('byok-model-select');
  modelSelect.innerHTML = '';
  for (const model of provider?.models || []) {
    const option = document.createElement('option');
    option.value = model.id;
    option.textContent = model.display_name;
    modelSelect.appendChild(option);
  }
  const selected = preferred && (provider?.models || []).some(item => item.id === preferred)
    ? preferred
    : provider?.default_model || provider?.models?.[0]?.id || '';
  modelSelect.value = selected;
}

function handleBYOKProviderChange() {
  const keyInput = byId('byok-api-key');
  const hadKey = Boolean(state.llmAccess.apiKey || keyInput?.value);
  resetBYOKKey();
  populateBYOKModels();
  if (hadKey) {
    setWorkspaceStatus(
      'ai-access-status',
      'The provider changed, so the previous provider key was cleared.',
      'info',
    );
  }
  renderChatAccess();
}

function toggleAIFormMode() {
  const mode = document.querySelector('input[name="ai-mode"]:checked')?.value || 'funded';
  byId('funded-settings').hidden = mode !== 'funded';
  byId('byok-settings').hidden = mode !== 'byok';
}

function applyAISettings(event) {
  event.preventDefault();
  const mode = document.querySelector('input[name="ai-mode"]:checked')?.value || 'funded';
  if (mode === 'byok') {
    const apiKey = byId('byok-api-key').value.trim();
    if (!apiKey) {
      setWorkspaceStatus('ai-access-status', 'Paste a provider API key or choose funded access.', 'error');
      byId('byok-api-key').focus();
      return;
    }
    state.llmAccess.mode = 'byok';
    state.llmAccess.provider = byId('byok-provider-select').value;
    state.llmAccess.model = byId('byok-model-select').value;
    state.llmAccess.apiKey = apiKey;
  } else {
    state.llmAccess.mode = 'funded';
    state.llmAccess.profile = byId('funded-profile-select').value;
  }
  setWorkspaceStatus('ai-access-status', 'AI access setting applied to this browser tab.', 'success');
  renderAccessSummary();
  renderChatAccess();
}

function currentLLMOptions() {
  if (state.llmAccess.mode === 'byok') {
    return {
      byok: {
        provider: state.llmAccess.provider,
        model: state.llmAccess.model,
        api_key: state.llmAccess.apiKey,
      },
    };
  }
  return state.llmAccess.profile ? { profile: state.llmAccess.profile } : null;
}

function llmAccessIssue() {
  if (!state.config?.llm_enabled) return { tab: 'ai', message: 'Language-model features are disabled on this server.' };
  if (state.readOnly) return { tab: null, message: 'Chat and edits are disabled in a shared read-only view.' };
  if (state.config.llm_auth_required && !state.authSession.authenticated) {
    return { tab: 'account', message: 'Sign in with a verified email to use language models.' };
  }
  if (state.llmAccess.mode === 'byok') {
    if (!state.llmAccess.apiKey) return { tab: 'ai', message: 'Add a provider API key for this browser tab.' };
    return null;
  }
  if (state.config.llm_auth_required && !state.trial?.active) {
    return { tab: 'account', message: 'Activate trial credit or choose your own API key.' };
  }
  if (state.config.llm_auth_required && state.trial.available_microusd <= 0) {
    return { tab: 'ai', message: 'Trial credit is exhausted. You can continue with your own API key.' };
  }
  return null;
}

function renderAccessSummary() {
  if (!state.config) return;
  renderChatAccess();
  if (typeof renderShellControls === 'function') renderShellControls();
}

function renderChatAccess() {
  const note = byId('chat-access-note');
  const input = byId('chat-input');
  const button = byId('chat-send-btn');
  if (!note || !input || !button) return;
  const issue = llmAccessIssue();
  // A user can draft questions before obtaining access and while an answer
  // is pending. Only explicit submission depends on access or availability.
  input.setAttribute('aria-disabled', 'false');
  button.disabled = Boolean(issue) || state.chatPending;
  if (!issue) {
    note.classList.remove('visible');
    note.textContent = '';
    return;
  }
  note.classList.add('visible');
  note.textContent = issue.message;
  if (issue.tab) {
    note.append(' ');
    const settingsButton = document.createElement('button');
    settingsButton.type = 'button';
    settingsButton.textContent = 'Open settings';
    settingsButton.addEventListener('click', () => openWorkspace(issue.tab));
    note.append(settingsButton);
  }
}

function toggleSecretVisibility(inputId, buttonId) {
  const input = byId(inputId);
  const button = byId(buttonId);
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  button.textContent = reveal ? 'Hide' : 'Show';
  button.setAttribute('aria-pressed', reveal ? 'true' : 'false');
}

function resetBYOKKey() {
  state.llmAccess.apiKey = '';
  const input = byId('byok-api-key');
  const revealButton = byId('byok-reveal-btn');
  if (input) {
    input.value = '';
    input.type = 'password';
  }
  if (revealButton) {
    revealButton.textContent = 'Show';
    revealButton.setAttribute('aria-pressed', 'false');
  }
}

function clearBYOKKey() {
  resetBYOKKey();
  setWorkspaceStatus('ai-access-status', 'The in-memory provider key was cleared.', 'success');
  renderChatAccess();
}

async function refreshProjects(options = {}) {
  if (!state.authSession.authenticated) return;
  const requestGeneration = ++projectRefreshGeneration;
  const account = state.authSession.user?.id;
  if (!options.quiet) setWorkspaceStatus('projects-status', 'Refreshing projects...', 'info');
  try {
    const [body, archivedBody] = await Promise.all([
      apiRequest('/api/projects'),
      workspaceProjects.archived ? apiRequest('/api/projects?archived=true') : Promise.resolve(null),
    ]);
    if (requestGeneration !== projectRefreshGeneration || account !== state.authSession.user?.id) return;
    state.projects = body.projects || [];
    if (archivedBody) workspaceProjects.archivedProjects = archivedBody.projects || [];
    renderProjectsUI();
    if (!options.quiet) setWorkspaceStatus('projects-status', '', 'info');
  } catch (error) {
    if (requestGeneration !== projectRefreshGeneration || account !== state.authSession.user?.id) return;
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

function renderProjectsUI() {
  const authenticated = state.authSession.authenticated;
  if (workspaceProjects.account !== state.authSession.user?.id) {
    workspaceProjects.account = state.authSession.user?.id;
    workspaceProjects.archived = false;
    workspaceProjects.archivedProjects = [];
    workspaceProjects.shareProject = null;
    workspaceProjects.renameProject = null;
  }
  byId('projects-signin-required').hidden = authenticated;
  byId('projects-authenticated').hidden = !authenticated;
  if (!authenticated) { byId('project-list').replaceChildren(); return; }

  const current = byId('current-project-card');
  current.hidden = !state.activeProject;
  if (state.activeProject) current.innerHTML = currentProjectHTML();

  const projects = workspaceProjects.archived ? workspaceProjects.archivedProjects : state.projects || [];
  byId('projects-active-filter').setAttribute('aria-pressed', String(!workspaceProjects.archived));
  byId('projects-archived-filter').setAttribute('aria-pressed', String(workspaceProjects.archived));
  byId('projects-archive-hint').hidden = !workspaceProjects.archived;
  byId('project-count').textContent = `${projects.length} ${projects.length === 1 ? 'project' : 'projects'}`;
  const list = byId('project-list');
  if (projects.length === 0) {
    list.innerHTML = workspaceProjects.archived ? '<div class="empty-list">No archived projects.</div>'
      : '<div class="empty-list">No private projects yet. Create a scenario or save a copy of the current example.</div>';
    if (typeof renderShellControls === 'function') renderShellControls();
    return;
  }
  list.innerHTML = projects.map(project => `
    <article class="project-card" data-project-card="${escapeAttr(project.id)}">
      <div class="project-card-main">
        <div>
          <div class="project-card-name">${escapeHtml(project.name)}</div>
          ${project.description ? `<div class="project-card-description">${escapeHtml(project.description)}</div>` : ''}
          <div class="project-card-meta">Version ${project.version}, updated ${escapeHtml(formatDate(project.updated_at))}</div>
          <div class="project-card-meta">${project.source_scenario_id ? `From ${escapeHtml(state.scenarios.find(item => item.id === project.source_scenario_id)?.title || project.source_scenario_id)}` : 'Original scenario'}</div>
          <div class="project-status-chips">${projectStatusHTML(project)}</div>
        </div>
        <div class="project-card-actions">
          ${project.archived_at ? `<button class="btn btn-small" type="button" data-project-action="restore" data-project-id="${escapeAttr(project.id)}" data-project-name="${escapeAttr(project.name)}" data-project-version="${project.version}">Restore privately</button>`
            : `<button class="btn btn-small" type="button" data-project-action="open" data-project-id="${escapeAttr(project.id)}">Open</button>${projectMenuHTML(project)}`}
        </div>
      </div>
      ${workspaceProjects.renameProject === project.id ? `<form class="project-rename-form" data-project-id="${escapeAttr(project.id)}" data-project-version="${project.version}"><label>Project name<input name="name" value="${escapeAttr(project.name)}" maxlength="120" required></label><button class="btn btn-small" type="submit">Save name</button><button class="btn btn-small" type="button" data-project-action="rename-cancel">Cancel</button></form>` : ''}
    </article>
  `).join('');
  if (typeof renderShellControls === 'function') renderShellControls();
}

function projectStatusHTML(project) {
  const chips = [];
  if (project.archived_at) chips.push('<span class="project-status-chip">Archived</span>');
  if (project.active_share_count) chips.push(`<span class="project-status-chip">Shared · ${project.active_share_count} ${project.active_share_count === 1 ? 'link' : 'links'}</span>`);
  for (const item of project.submissions || []) {
    if (!['pending', 'published'].includes(item.status)) continue;
    chips.push(`<span class="project-status-chip">${item.status === 'published' ? 'Published' : 'Suggested, awaiting review'} · snapshot v${item.project_version}${item.project_version !== project.version ? ' (earlier version)' : ''}</span>`);
  }
  return chips.join('');
}

function projectMenuHTML(project) {
  const action = (value, label) => `<button class="btn btn-small" type="button" data-project-action="${value}" data-project-id="${escapeAttr(project.id)}" data-project-name="${escapeAttr(project.name)}" data-project-version="${project.version}">${label}</button>`;
  return `<details class="project-menu"><summary aria-label="Actions for ${escapeAttr(project.name)}">...</summary><div class="project-menu-items">
    ${action('rename', 'Rename')}${action('share', 'Share')}
    ${state.authSession.community_catalog_enabled !== false ? action('suggest-example', state.authSession.scenario_admin ? 'Publish as example' : 'Suggest as a community example') : ''}
    ${action('download', 'Download')}${action('archive', 'Archive')}
  </div></details>`;
}

function currentProjectHTML() {
  const project = state.activeProject;
  const unsaved = state.diff_ops.length;
  const shares = state.activeShares || [];
  const latest = state.latestShare?.projectId === project.id ? state.latestShare : null;
  const shareRows = shares.length
    ? shares.map(link => `
      <div class="credential-card">
        <div class="credential-card-main">
          <div>
            <div class="credential-card-name">Read-only link ${escapeHtml(link.id.slice(0, 8))}</div>
            <div class="credential-card-meta">Created ${escapeHtml(formatDate(link.created_at))}${link.expires_at ? `, expires ${escapeHtml(formatDate(link.expires_at))}` : ', no expiration'}${link.revoked_at ? ', revoked' : link.expires_at && new Date(link.expires_at) <= new Date() ? ', expired' : ', active'}</div>
          </div>
          ${!link.revoked_at && (!link.expires_at || new Date(link.expires_at) > new Date()) ? `<button class="btn btn-small" type="button" data-project-action="share-revoke" data-share-id="${escapeAttr(link.id)}">Revoke</button>` : ''}
        </div>
      </div>
    `).join('')
    : '<div class="empty-list">No share links have been loaded.</div>';
  return `
    <div class="workspace-section-heading">
      <div>
        <h3>Open project: ${escapeHtml(project.name)}</h3>
        <p>Version ${project.version}${unsaved ? `, ${unsaved} unsaved ${unsaved === 1 ? 'change' : 'changes'}` : ', all changes saved'}</p>
      </div>
      <div class="project-card-actions">
        <button class="btn btn-primary" type="button" data-project-action="save-current" ${unsaved && !state.projectSavePending ? '' : 'disabled'}>${state.projectSavePending ? 'Saving...' : 'Save changes'}</button>
        ${projectMenuHTML(project)}
      </div>
    </div>
    <div class="project-share-controls" ${workspaceProjects.shareProject === project.id || latest ? '' : 'hidden'}>
      <h4>Read-only sharing</h4>
      <p class="field-hint">Anyone with a link can read the latest saved version. Unsaved changes are saved before creating a link.</p>
      <label for="project-share-expiry">Link expires after</label>
      <select id="project-share-expiry">${[['1', '1 day'], ['7', '7 days'], ['30', '30 days'], ['never', 'No expiration']].map(([value, label]) => `<option value="${value}" ${workspaceProjects.shareExpiry === value ? 'selected' : ''}>${label}</option>`).join('')}</select>
      <button class="btn btn-small" type="button" data-project-action="share-create">Create share link</button>
      <button class="btn btn-small" type="button" data-project-action="share-refresh">Refresh links</button>
    ${latest ? `
      <div class="share-panel">
        <strong>New link, shown until this workspace closes</strong>
        <div class="share-url-row">
          <input id="latest-share-url" type="text" readonly value="${escapeAttr(latest.url)}" aria-label="New read-only share link">
          <button class="btn" type="button" data-project-action="share-copy">Copy link</button>
        </div>
      </div>
    ` : ''}
    <div class="share-panel" ${state.sharesLoadedFor === project.id ? '' : 'hidden'}>
      <h3>Existing links</h3>
      <div class="credential-list">${shareRows}</div>
    </div>
    </div>
  `;
}

function prepareProjectCreateForm() {
  const scenario = state.bundle?.scenario;
  if (!scenario) return;
  byId('project-copy-panel').open = true;
  const suffix = state.viewKind === 'shared' ? ' copy' : ' exploration';
  byId('project-name-input').value = `${scenario.title || 'Untitled'}${suffix}`.slice(0, 120);
  byId('project-description-input').value = state.viewKind === 'shared'
    ? 'Private copy of a shared ABDA-NL project.'
    : '';
}

async function saveCurrentWork() {
  if (!state.authSession.authenticated) {
    openWorkspace('account');
    showGlobalStatus('Sign in with a verified email to save a private project.', 'info');
    return;
  }
  if (state.activeProject) {
    await saveProjectChanges();
    return;
  }
  openWorkspace('projects', { prepareSave: true });
}

async function createProjectFromCurrentView(event) {
  event.preventDefault();
  const name = byId('project-name-input').value.trim();
  const description = byId('project-description-input').value.trim();
  if (!name || !state.bundle) return;
  const sourceView = {
    kind: state.viewKind,
    activeProject: state.activeProject,
    sharedProject: state.sharedProject,
    scenarioId: state.scenario_id,
    bundle: state.bundle,
    diffOps: state.diff_ops,
  };
  const button = byId('project-create-btn');
  button.disabled = true;
  setWorkspaceStatus('projects-status', 'Creating private project...', 'info');
  try {
    let project;
    if (state.viewKind === 'example') {
      project = await apiRequest('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          source_scenario_id: state.scenario_id,
          diff_ops: state.diff_ops,
        }),
      });
    } else {
      const sourceScenarioId = state.activeProject?.source_scenario_id || state.sharedProject?.source_scenario_id || null;
      project = await apiRequest('/api/projects/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          source_scenario_id: sourceScenarioId,
          scenario: state.bundle.scenario,
        }),
      });
    }
    const viewChanged = (
      state.viewKind !== sourceView.kind
      || state.activeProject !== sourceView.activeProject
      || state.sharedProject !== sourceView.sharedProject
      || state.scenario_id !== sourceView.scenarioId
      || state.bundle !== sourceView.bundle
      || state.diff_ops !== sourceView.diffOps
    );
    if (viewChanged) {
      await refreshProjects({ quiet: true });
      showGlobalStatus(
        `Created private project "${project.name}". Open it from the Projects list when ready.`,
        'success',
      );
      return;
    }
    setViewContext('project', project);
    state.scenario_id = project.source_scenario_id;
    state.baseline = project.scenario;
    state.diff_ops = [];
    setBundle({ scenario: project.scenario, af: project.af });
    resetChatConversation();
    indexBundle();
    populateScenarioSelect();
    renderAll();
    await refreshProjects({ quiet: true });
    requestCloseModal('modal-workspace');
    showGlobalStatus(`Created private project "${project.name}".`, 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function saveProjectChanges() {
  const project = state.activeProject;
  if (!project) return null;
  if (state.projectSavePending) {
    showGlobalStatus('Wait for the current project save to finish.', 'info');
    return null;
  }
  if (hasPendingStateRequest()) {
    showGlobalStatus('Wait for the current change to finish before saving the project.', 'info');
    return null;
  }
  if (state.diff_ops.length === 0) {
    showGlobalStatus('This project already contains the current state.', 'info');
    return project;
  }
  const saveButton = byId('save-btn');
  state.projectSavePending = true;
  saveButton.disabled = true;
  renderProjectsUI();
  try {
    const updated = await apiRequest(`/api/projects/${encodeURIComponent(project.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_version: project.version, scenario: state.bundle.scenario }),
    });
    if (state.activeProject !== project) {
      await refreshProjects({ quiet: true });
      showGlobalStatus(
        `Saved project "${updated.name}" as version ${updated.version}. The current view was not changed.`,
        'success',
      );
      return updated;
    }
    state.activeProject = updated;
    state.baseline = updated.scenario;
    state.diff_ops = [];
    setBundle({ scenario: updated.scenario, af: updated.af });
    indexBundle();
    populateScenarioSelect();
    renderAll();
    await refreshProjects({ quiet: true });
    showGlobalStatus(`Saved project "${updated.name}" as version ${updated.version}.`, 'success');
    return updated;
  } catch (error) {
    if (error.code === 'project_version_conflict' && state.activeProject === project) {
      openWorkspace('projects');
      setWorkspaceStatus('projects-status', 'This project changed in another editor or connected tool. Reopen it before saving again.', 'error');
    } else if (error.code === 'project_version_conflict') {
      showGlobalStatus(`Project "${project.name}" changed before the save completed. Reopen it before saving again.`, 'error');
    } else {
      showGlobalStatus(error.message, 'error');
    }
    return null;
  } finally {
    state.projectSavePending = false;
    saveButton.disabled = false;
    renderProjectsUI();
  }
}

async function handleProjectAction(event) {
  const button = event.target.closest('[data-project-action]');
  if (!button) return;
  const action = button.dataset.projectAction;
  const projectId = button.dataset.projectId || state.activeProject?.id;
  const menu = button.closest('.project-menu');
  if (menu) { menu.querySelector('summary')?.focus(); menu.removeAttribute('open'); }
  if (action === 'open') return loadProject(button.dataset.projectId);
  if (action === 'archive') return archiveProject(button.dataset.projectId, button.dataset.projectName, Number(button.dataset.projectVersion));
  if (action === 'save-current') return saveProjectChanges();
  if (action === 'restore') return restoreArchivedProject(button);
  if (action === 'rename' || action === 'rename-cancel') {
    if (action === 'rename') workspaceProjects.archived = false;
    workspaceProjects.renameProject = action === 'rename' ? projectId : null;
    renderProjectsUI();
    byId('project-list').querySelector('.project-rename-form input')?.focus();
    return;
  }
  if (action === 'download') return downloadSavedProject(projectId);
  if (['share', 'suggest-example'].includes(action) && state.activeProject?.id !== projectId) {
    await loadProject(projectId);
    if (state.activeProject?.id !== projectId) return;
    openWorkspace('projects');
  }
  if (action === 'share') {
    return openProjectSharing(projectId);
  }
  if (action === 'share-create') return createProjectShare();
  if (action === 'share-refresh') return refreshProjectShares();
  if (action === 'share-copy') return copyElementText('latest-share-url', 'Share link copied.');
  if (action === 'share-revoke') return revokeProjectShare(button.dataset.shareId);
  if (action === 'suggest-example') return beginExampleSubmission();
}

async function openProjectSharing(projectId = state.activeProject?.id) {
  if (!projectId) return;
  if (state.activeProject?.id !== projectId) await loadProject(projectId);
  if (state.activeProject?.id !== projectId) return;
  workspaceProjects.shareProject = projectId;
  openWorkspace('projects');
  renderProjectsUI();
  await refreshProjectShares({ quiet: true });
  if (workspaceProjects.shareProject === state.activeProject?.id) byId('project-share-expiry')?.focus();
}

async function renameProject(event) {
  const form = event.target.closest('.project-rename-form');
  if (!form) return;
  event.preventDefault();
  const account = state.authSession.user?.id;
  const viewRevision = accountView.revision;
  const project = state.activeProject;
  try {
    const updated = await apiRequest(`/api/projects/${encodeURIComponent(form.dataset.projectId)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_version: Number(form.dataset.projectVersion), name: form.elements.name.value.trim() }),
    });
    if (account !== state.authSession.user?.id) return;
    if (state.activeProject === project && project?.id === updated.id) state.activeProject = updated;
    workspaceProjects.renameProject = null;
    await refreshProjects({ quiet: true });
    if (account !== state.authSession.user?.id || viewRevision !== accountView.revision) return;
    showGlobalStatus('Project renamed.', 'success');
  } catch (error) {
    if (account === state.authSession.user?.id) setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function downloadSavedProject(projectId) {
  const account = state.authSession.user?.id;
  try {
    const project = await apiRequest(`/api/projects/${encodeURIComponent(projectId)}`);
    if (account !== state.authSession.user?.id) return;
    await downloadScenarioFile({ ...project.scenario, title: project.name }, project.source_scenario_id);
  } catch (error) {
    if (account === state.authSession.user?.id) setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function restoreArchivedProject(button) {
  const account = state.authSession.user?.id;
  const viewRevision = accountView.revision;
  const projectId = button.dataset.projectId;
  if (!window.confirm(`Restore "${button.dataset.projectName}" privately? All old share links will be revoked. Create new links to share it again.`)) return;
  button.disabled = true;
  try {
    await apiRequest(`/api/projects/${encodeURIComponent(projectId)}/restore`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_version: Number(button.dataset.projectVersion) }),
    });
    if (account !== state.authSession.user?.id) return;
    await refreshProjects({ quiet: true });
    if (account !== state.authSession.user?.id || viewRevision !== accountView.revision) return;
    showGlobalStatus('Project restored privately. Old share links are revoked.', 'success', {
      label: 'Open project', onClick: () => { if (account === state.authSession.user?.id) loadProject(projectId); },
    });
  } catch (error) {
    if (account === state.authSession.user?.id) setWorkspaceStatus('projects-status', error.message, 'error');
  } finally { button.disabled = false; }
}

async function archiveProject(projectId, name, version) {
  if (!window.confirm(`Archive the private project "${name}"? Existing share links will stop working. You can restore it privately from Archived; any published example snapshot stays public.`)) return;
  const account = state.authSession.user?.id;
  const viewRevision = accountView.revision;
  try {
    await apiRequest(`/api/projects/${encodeURIComponent(projectId)}?expected_version=${encodeURIComponent(version)}`, { method: 'DELETE' });
    if (account !== state.authSession.user?.id) return;
    await refreshProjects({ quiet: true });
    if (account !== state.authSession.user?.id || viewRevision !== accountView.revision) return;
    if (state.activeProject?.id === projectId) {
      const defaultId = state.scenarios.some(item => item.id === 'popov_v_hayashi')
        ? 'popov_v_hayashi'
        : state.scenarios[0]?.id;
      if (defaultId) await loadScenario(defaultId);
    }
    if (account !== state.authSession.user?.id || viewRevision !== accountView.revision) return;
    showGlobalStatus(`Archived project "${name}".`, 'success');
  } catch (error) {
    if (account === state.authSession.user?.id) setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function createProjectShare() {
  if (!state.activeProject) return;
  if (state.diff_ops.length > 0) {
    const saved = await saveProjectChanges();
    if (!saved || state.activeProject !== saved) return;
  }
  const project = state.activeProject;
  const days = workspaceProjects.shareExpiry === 'never' ? null : Number(workspaceProjects.shareExpiry);
  const expiresAt = days ? new Date(Date.now() + days * 86400000).toISOString() : null;
  const secretGeneration = state.oneTimeSecretGeneration;
  try {
    const share = await apiRequest(`/api/projects/${encodeURIComponent(project.id)}/shares`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expires_at: expiresAt }),
    });
    if (
      state.activeProject !== project
      || state.oneTimeSecretGeneration !== secretGeneration
    ) {
      await refreshProjectShares({ quiet: true, project });
      showGlobalStatus(
        'A share link was created, but its one-time URL was discarded after the view changed.',
        'info',
      );
      return;
    }
    state.latestShare = { projectId: project.id, url: share.url };
    workspaceProjects.shareProject = project.id;
    await refreshProjectShares({ quiet: true, project });
    renderProjectsUI();
    setWorkspaceStatus('projects-status', 'A new read-only link is ready. Copy it now.', 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function refreshProjectShares(options = {}) {
  const project = options.project || state.activeProject;
  if (!project) return;
  const account = state.authSession.user?.id;
  const requestGeneration = (projectShareRefreshGenerations.get(project.id) || 0) + 1;
  projectShareRefreshGenerations.set(project.id, requestGeneration);
  try {
    const body = await apiRequest(`/api/projects/${encodeURIComponent(project.id)}/shares`);
    if (
      state.activeProject !== project
      || account !== state.authSession.user?.id
      || projectShareRefreshGenerations.get(project.id) !== requestGeneration
    ) return;
    state.activeShares = body.share_links || [];
    state.sharesLoadedFor = project.id;
    renderProjectsUI();
    if (!options.quiet) setWorkspaceStatus('projects-status', 'Share-link status refreshed.', 'success');
  } catch (error) {
    if (
      state.activeProject !== project
      || account !== state.authSession.user?.id
      || projectShareRefreshGenerations.get(project.id) !== requestGeneration
    ) return;
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function revokeProjectShare(shareId) {
  if (!state.activeProject || !window.confirm('Revoke this read-only share link?')) return;
  const project = state.activeProject;
  try {
    await apiRequest(`/api/projects/${encodeURIComponent(project.id)}/shares/${encodeURIComponent(shareId)}`, { method: 'DELETE' });
    if (state.activeProject !== project) return;
    if (state.latestShare?.projectId === project.id) state.latestShare = null;
    await refreshProjectShares({ quiet: true, project });
    setWorkspaceStatus('projects-status', 'Share link revoked.', 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function refreshMCPTokens(options = {}) {
  if (!state.authSession.authenticated) return;
  const requestGeneration = ++mcpTokenRefreshGeneration;
  if (!options.quiet) setWorkspaceStatus('mcp-status', 'Refreshing credentials...', 'info');
  try {
    const body = await apiRequest('/api/mcp/tokens');
    if (requestGeneration !== mcpTokenRefreshGeneration) return;
    state.mcpTokens = body.tokens || [];
    renderMCPTokens();
    if (!options.quiet) setWorkspaceStatus('mcp-status', '', 'info');
  } catch (error) {
    if (requestGeneration !== mcpTokenRefreshGeneration) return;
    setWorkspaceStatus('mcp-status', error.message, 'error');
  }
}

function renderMCPTokens() {
  const list = byId('mcp-token-list');
  if (!list || !state.authSession.authenticated) return;
  const tokens = state.mcpTokens || [];
  if (tokens.length === 0) {
    list.innerHTML = '<div class="empty-list">No agent credentials yet.</div>';
    return;
  }
  list.innerHTML = tokens.map(token => `
    <article class="credential-card">
      <div class="credential-card-main">
        <div>
          <div class="credential-card-name">${escapeHtml(token.name)}</div>
          <div class="credential-card-meta">${escapeHtml(token.token_prefix)}..., ${escapeHtml(token.scopes.join(', '))}</div>
          <div class="credential-card-meta">Expires ${escapeHtml(formatDate(token.expires_at))}${token.last_used_at ? `, last used ${escapeHtml(formatDate(token.last_used_at))}` : ''}${token.active ? '' : ', inactive'}</div>
        </div>
        <div class="credential-card-actions">
          ${token.active ? `<button class="btn btn-small" type="button" data-mcp-action="revoke" data-token-id="${escapeAttr(token.id)}" data-token-name="${escapeAttr(token.name)}">Revoke</button>` : ''}
        </div>
      </div>
    </article>
  `).join('');
}

async function createMCPToken(event) {
  event.preventDefault();
  const scopes = [...document.querySelectorAll('input[name="mcp-scope"]:checked')].map(input => input.value);
  if (scopes.length === 0) {
    setWorkspaceStatus('mcp-status', 'Select at least one permission.', 'error');
    return;
  }
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  const secretGeneration = state.oneTimeSecretGeneration;
  submit.disabled = true;
  setWorkspaceStatus('mcp-status', 'Creating credential...', 'info');
  try {
    const created = await apiRequest('/api/mcp/tokens', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: byId('mcp-token-name').value.trim(),
        scopes,
        expires_in_days: Number(byId('mcp-token-expiry').value),
      }),
    });
    if (state.oneTimeSecretGeneration !== secretGeneration) {
      await refreshMCPTokens({ quiet: true });
      showGlobalStatus(
        'The credential was created, but its one-time token was discarded after the workspace closed.',
        'info',
      );
      return;
    }
    byId('mcp-secret-value').value = created.token;
    byId('mcp-secret-value').type = 'password';
    byId('mcp-secret-reveal-btn').textContent = 'Show';
    byId('mcp-secret-reveal-btn').setAttribute('aria-pressed', 'false');
    byId('mcp-codex-config').textContent = created.codex_config;
    byId('mcp-claude-command').textContent = created.claude_command;
    byId('mcp-secret-panel').hidden = false;
    await refreshMCPTokens({ quiet: true });
    setWorkspaceStatus('mcp-status', 'Credential created. Save the one-time token now.', 'success');
    byId('mcp-secret-value').focus();
  } catch (error) {
    setWorkspaceStatus('mcp-status', error.message, 'error');
  } finally {
    submit.disabled = false;
  }
}

async function handleMCPAction(event) {
  const button = event.target.closest('[data-mcp-action]');
  if (!button || button.dataset.mcpAction !== 'revoke') return;
  if (!window.confirm(`Revoke the agent credential "${button.dataset.tokenName}"?`)) return;
  try {
    await apiRequest(`/api/mcp/tokens/${encodeURIComponent(button.dataset.tokenId)}`, { method: 'DELETE' });
    await refreshMCPTokens({ quiet: true });
    setWorkspaceStatus('mcp-status', 'Credential revoked.', 'success');
  } catch (error) {
    setWorkspaceStatus('mcp-status', error.message, 'error');
  }
}

function clearMCPSecretPanel() {
  const panel = byId('mcp-secret-panel');
  if (!panel) return;
  const value = byId('mcp-secret-value');
  const revealButton = byId('mcp-secret-reveal-btn');
  value.value = '';
  value.type = 'password';
  revealButton.textContent = 'Show';
  revealButton.setAttribute('aria-pressed', 'false');
  byId('mcp-codex-config').textContent = '';
  byId('mcp-claude-command').textContent = '';
  panel.hidden = true;
}

function clearWorkspaceOneTimeSecrets() {
  state.oneTimeSecretGeneration += 1;
  state.latestShare = null;
  const shareInput = byId('latest-share-url');
  if (shareInput) shareInput.value = '';
  clearMCPSecretPanel();
  renderProjectsUI();
}

async function copyElementText(id, successMessage) {
  const element = byId(id);
  const value = 'value' in element ? element.value : element.textContent;
  try {
    await copyText(value);
    showGlobalStatus(successMessage, 'success');
  } catch (_error) {
    showGlobalStatus('Copy failed. Select the text and copy it manually.', 'error');
  }
}

async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  if (!copied) throw new Error('copy failed');
}

function formatDate(value) {
  if (!value) return 'never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}
