/* Consent-based publication of fixed snapshots. Account data is never public. */
const curation = { generation: 0, reviewGeneration: 0, offset: 0, review: null, busy: false, account: null };

function initCurationUI() {
  byId('examples-refresh-btn').addEventListener('click', () => refreshExampleSubmissions());
  byId('examples-filter').addEventListener('change', () => { curation.offset = 0; refreshExampleSubmissions(); });
  for (const [id, delta] of [['examples-previous', -50], ['examples-next', 50]]) {
    byId(id).addEventListener('click', () => { curation.offset = Math.max(0, curation.offset + delta); refreshExampleSubmissions(); });
  }
  byId('scenario-example-submissions').addEventListener('click', () => {
    requestCloseModal('modal-scenario-library');
    openWorkspace('examples');
  });
  byId('example-review-close').addEventListener('click', closeExampleReview);
  byId('example-public-consent').addEventListener('change', renderExampleActions);
  byId('example-review-actions').addEventListener('click', handleExampleDecision);
  byId('examples-list').addEventListener('click', event => {
    const button = event.target.closest('[data-example-review]');
    if (button) openExampleReview(button.dataset.exampleReview);
    const open = event.target.closest('[data-public-example]');
    if (open) { requestCloseModal('modal-workspace'); requestScenarioLoad(open.dataset.publicExample); }
  });
}

function clearCurationState() {
  curation.generation += 1;
  curation.offset = 0;
  closeExampleReview();
  byId('examples-list').replaceChildren();
  byId('example-review-snapshot').replaceChildren();
  byId('example-review-note').value = '';
  byId('example-public-consent').checked = false;
}

function closeExampleReview() {
  curation.reviewGeneration += 1;
  curation.review = null;
  closeModal('modal-example-review');
}

function renderCurationAccess() {
  const session = state.authSession;
  const account = session.authenticated ? session.user?.id : null;
  if (curation.account !== account) { clearCurationState(); curation.account = account; }
  const available = !!account && session.community_catalog_enabled !== false;
  byId('workspace-tab-examples').hidden = !available;
  byId('scenario-example-submissions').hidden = !available;
  byId('examples-filter-field').hidden = !session.scenario_admin;
  byId('scenario-example-submissions').textContent = session.scenario_admin ? 'Review examples' : 'Example submissions';
  byId('examples-introduction').textContent = session.scenario_admin
    ? 'Review submitted snapshots here. To publish your own scenario directly, open its private project and choose Publish as example.'
    : 'Open a private project, then choose Suggest as example. Your project stays private; only the snapshot you approve is submitted for review.';
}

async function refreshPublicExampleList() {
  const body = await apiRequest('/scenarios');
  const selected = byId('scenario-select').value;
  state.scenarios = body.scenarios || [];
  populateScenarioSelect();
  if ([...byId('scenario-select').options].some(option => option.value === selected)) byId('scenario-select').value = selected;
}

async function refreshExampleSubmissions() {
  if (!state.authSession.authenticated || state.authSession.community_catalog_enabled === false) return;
  const generation = ++curation.generation;
  const filter = state.authSession.scenario_admin ? byId('examples-filter').value : 'mine';
  const params = new URLSearchParams({ offset: String(curation.offset) });
  if (filter !== 'mine') { params.set('queue', 'true'); params.set('status', filter); }
  setWorkspaceStatus('examples-status', 'Loading submissions...', 'info');
  try {
    const body = await apiRequest(`/api/scenario-submissions?${params}`);
    if (generation !== curation.generation) return;
    byId('examples-list').innerHTML = body.submissions.length ? body.submissions.map(item => `
      <article class="project-card">
        <div class="project-card-main"><div>
          <div class="project-card-name">${escapeHtml(item.title)}</div>
          <div class="project-card-meta">Snapshot of version ${item.project_version} · ${escapeHtml(formatDate(item.created_at))}</div>
        </div><span class="example-status example-status-${escapeAttr(item.status)}">${exampleStatusLabel(item.status)}</span></div>
        ${item.review_note ? `<p class="example-note">${escapeHtml(item.review_note)}</p>` : ''}
        <div class="project-card-actions">
          <button class="btn btn-small" type="button" data-example-review="${escapeAttr(item.id)}">${filter === 'pending' ? 'Review snapshot' : 'View snapshot'}</button>
          ${item.public_scenario_id ? `<button class="btn btn-small" type="button" data-public-example="${escapeAttr(item.public_scenario_id)}">Open example</button>` : ''}
        </div>
      </article>`).join('') : '<div class="empty-list">No submissions in this view.</div>';
    byId('examples-previous').hidden = curation.offset === 0;
    byId('examples-next').hidden = !body.has_more;
    setWorkspaceStatus('examples-status', '', 'info');
    await refreshPublicExampleList();
  } catch (error) {
    if (generation === curation.generation) setWorkspaceStatus('examples-status', error.message, 'error');
  }
}

function exampleStatusLabel(status) {
  return { pending: 'Awaiting review', published: 'Published', rejected: 'Declined', withdrawn: 'Withdrawn or removed' }[status] || status;
}

function exampleSnapshotHTML(scenario) {
  const statements = ['facts', 'assumptions', 'propositions', 'conclusions'].map(section => {
    const entries = Object.entries(scenario[section] || {});
    if (!entries.length) return '';
    return `<h4>${section[0].toUpperCase() + section.slice(1)}</h4><ul>${entries.map(([id, value]) =>
      `<li>${escapeHtml(value.description || id)}${value.active === false ? ' (suspended)' : ''}</li>`).join('')}</ul>`;
  }).join('');
  const vocabulary = Object.assign({}, scenario.facts, scenario.assumptions, scenario.propositions, scenario.conclusions);
  const literal = id => {
    const negative = id.startsWith('-');
    const name = negative ? id.slice(1) : id;
    const value = vocabulary[name];
    return negative ? value?.negated_description || `Not: ${value?.description || name}` : value?.description || name;
  };
  const rules = Object.entries(scenario.rules || {}).map(([id, rule]) => {
    const premise = rule.premises.length ? `If ${rule.premises.map(literal).join(' AND ')}, ` : '';
    return `<li>${escapeHtml(premise)}${rule.type === 'strict' ? 'always' : 'usually'}: ${escapeHtml(literal(rule.conclusion))}
      <span class="project-card-meta">(${escapeHtml(id)}, priority ${rule.block ?? 1}${rule.active === false ? ', suspended' : ''})</span></li>`;
  }).join('');
  return `<h3>${escapeHtml(scenario.title)}</h3>
    ${scenario.description ? `<p class="example-background">${escapeHtml(scenario.description)}</p>` : ''}
    <div class="example-snapshot-statements">${statements}</div>
    ${rules ? `<h4>Rules</h4><ol class="example-rules">${rules}</ol>` : ''}
    ${scenario.sources?.length ? `<h4>Reference documents (published in full)</h4>${scenario.sources.map(source =>
      `<details class="source-card"><summary>${escapeHtml(source.filename)}</summary><p class="scenario-hint">${escapeHtml(source.url || '')}</p><pre tabindex="0">${escapeHtml(source.text)}</pre></details>`).join('')}` : ''}
    <details class="example-raw"><summary>Inspect complete snapshot data</summary><pre tabindex="0">${escapeHtml(JSON.stringify(scenario, null, 2))}</pre></details>`;
}

async function beginExampleSubmission() {
  if (curation.busy || !state.activeProject) return;
  const originalProjectId = state.activeProject.id;
  if (state.diff_ops.length) {
    if (!window.confirm('Save your current project changes before reviewing the public snapshot?')) return;
    const saved = await saveProjectChanges();
    if (!saved || state.activeProject?.id !== originalProjectId) return;
  }
  if (hasPendingStateRequest()) {
    showGlobalStatus('Wait for the current change to finish before submitting.', 'info');
    return;
  }
  const project = state.activeProject;
  const account = state.authSession.user?.id;
  const generation = ++curation.reviewGeneration;
  try {
    const saved = await apiRequest(`/api/projects/${encodeURIComponent(project.id)}`);
    if (generation !== curation.reviewGeneration || state.activeProject !== project || state.authSession.user?.id !== account) return;
    curation.review = { kind: 'submit', project: saved, account };
    showExampleReview({ ...saved.scenario, title: saved.name }, `Saved project version ${saved.version}`);
  } catch (error) { setWorkspaceStatus('projects-status', error.message, 'error'); }
}

async function openExampleReview(id) {
  const account = state.authSession.user?.id;
  const generation = ++curation.reviewGeneration;
  try {
    const item = await apiRequest(`/api/scenario-submissions/${encodeURIComponent(id)}`);
    if (generation !== curation.reviewGeneration || state.authSession.user?.id !== account) return;
    curation.review = { kind: 'review', item, account };
    showExampleReview(item.scenario, `${exampleStatusLabel(item.status)} · Snapshot of version ${item.project_version}`);
    if (item.review_note) setWorkspaceStatus('example-review-status', item.review_note, 'info');
  } catch (error) { setWorkspaceStatus('examples-status', error.message, 'error'); }
}

function showExampleReview(scenario, subtitle) {
  byId('example-review-title').textContent = curation.review.kind === 'submit'
    ? state.authSession.scenario_admin ? 'Publish as example' : 'Suggest as example' : 'Submitted snapshot';
  byId('example-review-subtitle').textContent = subtitle;
  byId('example-review-snapshot').innerHTML = exampleSnapshotHTML(scenario);
  byId('example-consent-panel').hidden = curation.review.kind !== 'submit';
  byId('example-public-consent').checked = false;
  byId('example-review-note').value = '';
  byId('example-review-note-field').hidden = curation.review.kind === 'submit' || !state.authSession.scenario_admin
    || !['pending', 'published'].includes(curation.review.item.status);
  setWorkspaceStatus('example-review-status', '', 'info');
  renderExampleActions();
  openModal('modal-example-review', '#example-review-close');
}

function renderExampleActions() {
  const review = curation.review;
  if (!review) return;
  const buttons = [];
  const button = (action, text, primary = false, disabled = false) => buttons.push(
    `<button class="btn${primary ? ' btn-primary' : ''}" type="button" data-example-action="${action}" ${curation.busy || disabled ? 'disabled' : ''}>${text}</button>`);
  if (review.kind === 'submit') {
    button('submit', state.authSession.scenario_admin ? 'Publish example' : 'Submit for review', true, !byId('example-public-consent').checked);
  } else {
    const item = review.item;
    if (state.authSession.scenario_admin && item.status === 'pending') {
      button('reject', 'Decline');
      button('approve', 'Approve & publish', true);
    }
    if (state.authSession.scenario_admin && item.status === 'published') button('unpublish', 'Remove from examples');
    if (item.is_own && item.status === 'pending') button('withdraw', 'Withdraw request');
  }
  button('close', 'Close');
  byId('example-review-actions').innerHTML = buttons.join('');
}

async function handleExampleDecision(event) {
  const action = event.target.closest('[data-example-action]')?.dataset.exampleAction;
  const review = curation.review;
  if (!action || !review || curation.busy || review.account !== state.authSession.user?.id) return;
  if (action === 'close') return closeExampleReview();
  const note = byId('example-review-note').value.trim();
  if (['reject', 'unpublish'].includes(action) && !note) {
    setWorkspaceStatus('example-review-status', 'Please add a short reason for the author.', 'error');
    byId('example-review-note').focus();
    return;
  }
  if (action === 'submit' && !byId('example-public-consent').checked) return;
  if (action === 'approve' && !window.confirm('Publish this exact snapshot as a public, downloadable example?')) return;
  if (action === 'unpublish' && !window.confirm('Remove this snapshot from the public examples? Existing private copies are not changed.')) return;
  curation.busy = true;
  renderExampleActions();
  setWorkspaceStatus('example-review-status', 'Saving...', 'info');
  try {
    const path = action === 'submit' ? '/api/scenario-submissions' : `/api/scenario-submissions/${encodeURIComponent(review.item.id)}/review`;
    const payload = action === 'submit'
      ? { project_id: review.project.id, expected_version: review.project.version, public_consent: true, publish: !!state.authSession.scenario_admin }
      : { expected_version: review.item.version, action, note };
    const item = await apiRequest(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (review.account !== state.authSession.user?.id) return;
    const stillReviewing = curation.review === review;
    if (stillReviewing) closeExampleReview();
    const message = item.status === 'published' ? 'Published. The scenario is now in Community examples.'
      : item.status === 'pending' ? 'Submitted for review. Check Examples for updates.'
      : `${exampleStatusLabel(item.status)}. To submit a revised snapshot, edit and save the project first.`;
    showGlobalStatus(message, 'success');
    if (!stillReviewing) { await refreshPublicExampleList(); return; }
    if (state.authSession.scenario_admin) byId('examples-filter').value = action === 'approve' ? 'pending' : 'mine';
    curation.offset = 0;
    openWorkspace('examples');
  } catch (error) {
    if (curation.review === review) setWorkspaceStatus('example-review-status', error.message, 'error');
  } finally { curation.busy = false; renderExampleActions(); }
}
