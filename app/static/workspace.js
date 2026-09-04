/* Account, project, AI access, sharing, and MCP controls for ABDA-NL. */

let globalStatusTimer = null;
const modalOpeners = new Map();
let externalLoginRefreshPending = false;

function byId(id) {
  return document.getElementById(id);
}

function showGlobalStatus(message, kind = 'info') {
  const status = byId('global-status');
  if (!status) return;
  status.textContent = message;
  status.className = `global-status status-${kind}`;
  status.hidden = false;
  if (globalStatusTimer) window.clearTimeout(globalStatusTimer);
  globalStatusTimer = window.setTimeout(() => {
    status.hidden = true;
    globalStatusTimer = null;
  }, kind === 'error' ? 9000 : 6000);
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
    const closeButton = content.querySelector('.modal-close');
    if (closeButton && !closeButton.getAttribute('aria-label')) closeButton.setAttribute('aria-label', 'Close dialog');
    backdrop.addEventListener('mousedown', event => {
      if (event.target === backdrop) requestCloseModal(backdrop.id);
    });
  }

  document.addEventListener('keydown', event => {
    const visible = [...document.querySelectorAll('.modal-backdrop.visible')];
    const top = visible[visible.length - 1];
    if (!top) return;
    if (event.key === 'Escape') {
      event.preventDefault();
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
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
}

function modalFocusableElements(root) {
  const selector = [
    'a[href]:not([hidden])',
    'button:not([disabled]):not([hidden])',
    'input:not([disabled]):not([hidden])',
    'select:not([disabled]):not([hidden])',
    'textarea:not([disabled]):not([hidden])',
    '[tabindex]:not([tabindex="-1"]):not([hidden])',
  ].join(',');
  return [...root.querySelectorAll(selector)].filter(element => element.offsetParent !== null);
}

function openModal(id, focusSelector = null) {
  const modal = byId(id);
  if (!modal) return;
  if (!modal.classList.contains('visible')) modalOpeners.set(id, document.activeElement);
  modal.classList.add('visible');
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
  window.setTimeout(() => {
    const requested = focusSelector
      ? [...modal.querySelectorAll(focusSelector)].find(element => (
        !element.disabled && element.offsetParent !== null
      ))
      : null;
    const target = requested || modalFocusableElements(modal)[0];
    const content = modal.querySelector('.modal-content');
    if (content && !content.hasAttribute('tabindex')) content.setAttribute('tabindex', '-1');
    (target || content)?.focus();
  }, 0);
}

function restoreModalFocus(id) {
  const anyVisible = document.querySelector('.modal-backdrop.visible');
  if (!anyVisible) document.body.classList.remove('modal-open');
  const opener = modalOpeners.get(id);
  modalOpeners.delete(id);
  if (!anyVisible && opener && document.contains(opener)) opener.focus();
}

function requestCloseModal(id) {
  if (id === 'modal-edit') {
    closeEditModal();
  } else if (id === 'modal-suspend-impact') {
    cancelSuspendImpact();
  } else if (id === 'modal-workspace') {
    clearWorkspaceOneTimeSecrets();
    closeModal(id);
  } else {
    closeModal(id);
  }
}

function initWorkspaceUI() {
  byId('workspace-btn')?.addEventListener('click', () => openWorkspace('account'));
  byId('ai-access-btn')?.addEventListener('click', () => openWorkspace('ai'));
  byId('chat-access-button')?.addEventListener('click', () => openWorkspace('ai'));
  byId('save-btn')?.addEventListener('click', saveCurrentWork);

  for (const tab of document.querySelectorAll('[data-workspace-tab]')) {
    tab.addEventListener('click', () => switchWorkspaceTab(tab.dataset.workspaceTab));
    tab.addEventListener('keydown', handleWorkspaceTabKeydown);
  }

  byId('dev-login-form')?.addEventListener('submit', handleDevelopmentLogin);
  byId('logout-form')?.addEventListener('submit', handleLogout);
  byId('trial-activate-btn')?.addEventListener('click', activateTrial);
  byId('projects-refresh-btn')?.addEventListener('click', () => refreshProjects());
  byId('project-create-form')?.addEventListener('submit', createProjectFromCurrentView);
  byId('project-list')?.addEventListener('click', handleProjectAction);
  byId('current-project-card')?.addEventListener('click', handleProjectAction);

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
    if (document.visibilityState === 'visible') refreshExternalOIDCLogin();
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

  byId('projects-signin-required').hidden = session.authenticated;
  byId('projects-authenticated').hidden = !session.authenticated;
  byId('mcp-signin-required').hidden = session.authenticated;
  byId('mcp-authenticated').hidden = !session.authenticated;
  renderTrialUI();
  renderProjectsUI();
  renderMCPTokens();
  renderChatAccess();
}

async function refreshExternalOIDCLogin() {
  if (
    externalLoginRefreshPending
    || state.authSession.authenticated
    || state.authSession.auth_mode !== 'oidc'
  ) return;
  externalLoginRefreshPending = true;
  try {
    const session = await apiRequest('/api/auth/session');
    if (!session.authenticated) return;
    state.authSession = session;
    renderAccountUI();
    await refreshAuthenticatedWorkspace({ quiet: true });
    showGlobalStatus('Signed in. You can now save a private copy of this shared project.', 'success');
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
  try {
    state.authSession = await apiRequest('/api/auth/dev/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, display_name: displayName || null }),
    });
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
  setWorkspaceStatus('account-status', 'Signing out...', 'info');
  resetBYOKKey();
  clearWorkspaceOneTimeSecrets();
  try {
    const result = await apiRequest('/api/auth/logout', { method: 'POST' });
    if (!result?.logout_url) throw new Error('The sign-out destination is unavailable.');
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
  try {
    const [trial, projects] = await Promise.all([
      apiRequest('/api/trial'),
      apiRequest('/api/projects'),
    ]);
    state.trial = trial;
    state.projects = projects.projects || [];
    renderAccountUI();
    renderAccessSummary();
  } catch (error) {
    if (!options.quiet) showGlobalStatus(error.message, 'error');
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
  button.disabled = true;
  setWorkspaceStatus('trial-status', 'Activating trial credit...', 'info');
  try {
    state.trial = await apiRequest('/api/trial/activate', { method: 'POST' });
    renderTrialUI();
    renderAccessSummary();
    setWorkspaceStatus('trial-status', `${formatUSD(state.trial.granted_microusd)} of trial credit is active.`, 'success');
  } catch (error) {
    setWorkspaceStatus('trial-status', error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function refreshTrialBalanceQuietly() {
  if (!state.authSession.authenticated) return;
  try {
    state.trial = await apiRequest('/api/trial');
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
  let label;
  if (state.llmAccess.mode === 'byok') {
    const provider = (state.config.byok_providers || []).find(item => item.id === state.llmAccess.provider);
    const model = provider?.models?.find(item => item.id === state.llmAccess.model);
    label = `Own key: ${model?.display_name || provider?.display_name || 'Provider'}`;
  } else {
    const profile = (state.config.profiles || []).find(item => item.id === state.llmAccess.profile);
    label = `Funded: ${profile?.display_name || 'Default'}`;
  }
  byId('ai-access-btn').textContent = `AI: ${label.replace(/^Funded: /, '')}`;
  byId('chat-access-button').textContent = label;
  byId('chat-access-button').setAttribute('aria-label', `AI access setting, ${label}. Open settings.`);
  renderChatAccess();
}

function renderChatAccess() {
  const note = byId('chat-access-note');
  const input = byId('chat-input');
  const button = byId('chat-send-btn');
  if (!note || !input || !button) return;
  const issue = llmAccessIssue();
  input.disabled = Boolean(issue) || state.chatPending;
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
  if (!options.quiet) setWorkspaceStatus('projects-status', 'Refreshing projects...', 'info');
  try {
    const body = await apiRequest('/api/projects');
    state.projects = body.projects || [];
    renderProjectsUI();
    if (!options.quiet) setWorkspaceStatus('projects-status', '', 'info');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

function renderProjectsUI() {
  const authenticated = state.authSession.authenticated;
  byId('projects-signin-required').hidden = authenticated;
  byId('projects-authenticated').hidden = !authenticated;
  if (!authenticated) return;

  const current = byId('current-project-card');
  current.hidden = !state.activeProject;
  if (state.activeProject) current.innerHTML = currentProjectHTML();

  const projects = state.projects || [];
  byId('project-count').textContent = `${projects.length} ${projects.length === 1 ? 'project' : 'projects'}`;
  const list = byId('project-list');
  if (projects.length === 0) {
    list.innerHTML = '<div class="empty-list">No private projects yet. Save the current example to create one.</div>';
    return;
  }
  list.innerHTML = projects.map(project => `
    <article class="project-card">
      <div class="project-card-main">
        <div>
          <div class="project-card-name">${escapeHtml(project.name)}</div>
          ${project.description ? `<div class="project-card-description">${escapeHtml(project.description)}</div>` : ''}
          <div class="project-card-meta">Version ${project.version}, updated ${escapeHtml(formatDate(project.updated_at))}</div>
        </div>
        <div class="project-card-actions">
          <button class="btn btn-small" type="button" data-project-action="open" data-project-id="${escapeAttr(project.id)}">Open</button>
          <button class="btn btn-small" type="button" data-project-action="archive" data-project-id="${escapeAttr(project.id)}" data-project-name="${escapeAttr(project.name)}" data-project-version="${project.version}">Archive</button>
        </div>
      </div>
    </article>
  `).join('');
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
            <div class="credential-card-name">Read-only link</div>
            <div class="credential-card-meta">Created ${escapeHtml(formatDate(link.created_at))}${link.expires_at ? `, expires ${escapeHtml(formatDate(link.expires_at))}` : ', no expiration'}${link.revoked_at ? ', revoked' : ''}</div>
          </div>
          ${link.active !== false && !link.revoked_at ? `<button class="btn btn-small" type="button" data-project-action="share-revoke" data-share-id="${escapeAttr(link.id)}">Revoke</button>` : ''}
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
        <button class="btn btn-primary" type="button" data-project-action="save-current" ${unsaved ? '' : 'disabled'}>Save changes</button>
        <button class="btn" type="button" data-project-action="share-create">Create share link</button>
        <button class="btn" type="button" data-project-action="share-refresh">Manage links</button>
      </div>
    </div>
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
  `;
}

function prepareProjectCreateForm() {
  const scenario = state.bundle?.scenario;
  if (!scenario) return;
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
    setViewContext('project', project);
    state.scenario_id = project.source_scenario_id;
    state.baseline = project.scenario;
    state.bundle = { scenario: project.scenario, af: project.af };
    state.diff_ops = [];
    state.chatMessages = [];
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
  if (state.diff_ops.length === 0) {
    showGlobalStatus('This project already contains the current state.', 'info');
    return project;
  }
  const saveButton = byId('save-btn');
  saveButton.disabled = true;
  try {
    const updated = await apiRequest(`/api/projects/${encodeURIComponent(project.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_version: project.version, scenario: state.bundle.scenario }),
    });
    state.activeProject = updated;
    state.baseline = updated.scenario;
    state.bundle = { scenario: updated.scenario, af: updated.af };
    state.diff_ops = [];
    indexBundle();
    populateScenarioSelect();
    renderAll();
    await refreshProjects({ quiet: true });
    showGlobalStatus(`Saved project "${updated.name}" as version ${updated.version}.`, 'success');
    return updated;
  } catch (error) {
    if (error.code === 'project_version_conflict') {
      openWorkspace('projects');
      setWorkspaceStatus('projects-status', 'This project changed in another tab. Reopen it before saving again.', 'error');
    } else {
      showGlobalStatus(error.message, 'error');
    }
    return null;
  } finally {
    saveButton.disabled = false;
  }
}

async function handleProjectAction(event) {
  const button = event.target.closest('[data-project-action]');
  if (!button) return;
  const action = button.dataset.projectAction;
  if (action === 'open') return loadProject(button.dataset.projectId);
  if (action === 'archive') return archiveProject(button.dataset.projectId, button.dataset.projectName, Number(button.dataset.projectVersion));
  if (action === 'save-current') return saveProjectChanges();
  if (action === 'share-create') return createProjectShare();
  if (action === 'share-refresh') return refreshProjectShares();
  if (action === 'share-copy') return copyElementText('latest-share-url', 'Share link copied.');
  if (action === 'share-revoke') return revokeProjectShare(button.dataset.shareId);
}

async function archiveProject(projectId, name, version) {
  if (!window.confirm(`Archive the private project "${name}"? Existing share links will stop working.`)) return;
  try {
    await apiRequest(`/api/projects/${encodeURIComponent(projectId)}?expected_version=${encodeURIComponent(version)}`, { method: 'DELETE' });
    const wasOpen = state.activeProject?.id === projectId;
    await refreshProjects({ quiet: true });
    if (wasOpen) {
      const defaultId = state.scenarios.some(item => item.id === 'popov_v_hayashi')
        ? 'popov_v_hayashi'
        : state.scenarios[0]?.id;
      if (defaultId) await loadScenario(defaultId);
    }
    showGlobalStatus(`Archived project "${name}".`, 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function createProjectShare() {
  if (!state.activeProject) return;
  if (state.diff_ops.length > 0) {
    const saved = await saveProjectChanges();
    if (!saved) return;
  }
  try {
    const share = await apiRequest(`/api/projects/${encodeURIComponent(state.activeProject.id)}/shares`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    state.latestShare = { projectId: state.activeProject.id, url: share.url };
    await refreshProjectShares({ quiet: true });
    renderProjectsUI();
    setWorkspaceStatus('projects-status', 'A new read-only link is ready. Copy it now.', 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function refreshProjectShares(options = {}) {
  if (!state.activeProject) return;
  try {
    const body = await apiRequest(`/api/projects/${encodeURIComponent(state.activeProject.id)}/shares`);
    state.activeShares = body.share_links || [];
    state.sharesLoadedFor = state.activeProject.id;
    renderProjectsUI();
    if (!options.quiet) setWorkspaceStatus('projects-status', 'Share-link status refreshed.', 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function revokeProjectShare(shareId) {
  if (!state.activeProject || !window.confirm('Revoke this read-only share link?')) return;
  try {
    await apiRequest(`/api/projects/${encodeURIComponent(state.activeProject.id)}/shares/${encodeURIComponent(shareId)}`, { method: 'DELETE' });
    if (state.latestShare?.projectId === state.activeProject.id) state.latestShare = null;
    await refreshProjectShares({ quiet: true });
    setWorkspaceStatus('projects-status', 'Share link revoked.', 'success');
  } catch (error) {
    setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function refreshMCPTokens(options = {}) {
  if (!state.authSession.authenticated) return;
  if (!options.quiet) setWorkspaceStatus('mcp-status', 'Refreshing credentials...', 'info');
  try {
    const body = await apiRequest('/api/mcp/tokens');
    state.mcpTokens = body.tokens || [];
    renderMCPTokens();
    if (!options.quiet) setWorkspaceStatus('mcp-status', '', 'info');
  } catch (error) {
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
