/* Fixed public snapshots. Display-name attribution requires explicit opt-in. */
const curation = { generation: 0, publicRefreshGeneration: 0, reviewGeneration: 0, offset: 0, review: null, busy: false, account: null, admin: false, confirmPublish: false, counts: {}, publishedNotice: null };

function initCurationUI() {
  byId('examples-refresh-btn').addEventListener('click', () => refreshExampleSubmissions());
  byId('examples-filter').addEventListener('change', () => { curation.offset = 0; refreshExampleSubmissions(); });
  byId('examples-filter-segments').addEventListener('click', event => {
    const filter = event.target.closest('[data-example-filter]')?.dataset.exampleFilter;
    if (!filter) return;
    byId('examples-filter').value = filter;
    curation.offset = 0;
    refreshExampleSubmissions();
  });
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
  byId('example-publish-confirmation').addEventListener('click', handleExampleDecision);
  for (const id of ['example-public-title', 'example-public-summary', 'example-attribute-author']) {
    byId(id).addEventListener('input', () => {
      byId('example-public-consent').checked = false;
      renderPublicSnapshot(); renderExampleActions();
    });
  }
  byId('examples-list').addEventListener('click', event => {
    const button = event.target.closest('[data-example-review]');
    if (button) openExampleReview(button.dataset.exampleReview);
    const open = event.target.closest('[data-public-example]');
    if (open) { requestCloseModal('modal-workspace'); requestScenarioLoad(open.dataset.publicExample); }
  });
}

function clearCurationState() {
  const focusWasCleared = ['modal-example-review', 'examples-list', 'examples-filter-field']
    .some(id => byId(id).contains(document.activeElement));
  curation.generation += 1;
  curation.publicRefreshGeneration += 1;
  curation.offset = 0;
  curation.busy = false;
  curation.counts = {};
  curation.publishedNotice = null;
  closeExampleReview();
  byId('examples-list').replaceChildren();
  byId('example-review-snapshot').replaceChildren();
  byId('example-review-actions').replaceChildren();
  byId('example-review-subtitle').textContent = '';
  byId('example-review-note').value = '';
  for (const id of ['example-public-title', 'example-public-summary', 'example-author-note']) byId(id).value = '';
  byId('example-snapshot-summary').replaceChildren();
  byId('example-attribution-name').textContent = '';
  byId('example-attribution-note').textContent = '';
  byId('examples-filter-segments').replaceChildren();
  byId('examples-tab-count').textContent = '';
  byId('example-public-consent').checked = false;
  setWorkspaceStatus('examples-status', '', 'info');
  setWorkspaceStatus('example-review-status', '', 'info');
  if (focusWasCleared) {
    (byId('modal-workspace').classList.contains('visible')
      ? byId('workspace-tab-examples') : byId('workspace-btn')).focus();
  }
}

function closeExampleReview() {
  curation.reviewGeneration += 1;
  curation.review = null;
  curation.busy = false;
  curation.confirmPublish = false;
  byId('example-publish-confirmation').hidden = true;
  closeModal('modal-example-review');
}

function renderCurationAccess() {
  const session = state.authSession;
  const account = session.authenticated ? session.user?.id : null;
  const admin = Boolean(session.scenario_admin);
  if (curation.account !== account || curation.admin !== admin) {
    clearCurationState(); curation.account = account; curation.admin = admin;
  }
  const available = !!account && session.community_catalog_enabled !== false;
  byId('workspace-tab-examples').hidden = !available;
  byId('scenario-example-submissions').hidden = !available;
  byId('examples-filter-field').hidden = !session.scenario_admin;
  byId('scenario-example-submissions').textContent = 'Community examples';
  byId('examples-introduction').textContent = session.scenario_admin
    ? 'Review submitted snapshots here. To publish your own scenario directly, open its private project and choose Publish as example.'
    : 'Open a private project, then choose Suggest as a community example. Your project stays private; only the snapshot you approve is submitted for review.';
}

async function refreshPublicExampleList() {
  const generation = ++curation.publicRefreshGeneration;
  const account = state.authSession.user?.id;
  const body = await apiRequest('/scenarios');
  if (generation !== curation.publicRefreshGeneration || account !== state.authSession.user?.id) return;
  state.scenarios = body.scenarios || [];
  // The shell derives selection from the loaded scenario/project, without loading it again.
  populateScenarioSelect();
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
    curation.counts = body.counts || {};
    byId('examples-tab-count').textContent = `(${state.authSession.scenario_admin ? curation.counts.pending || 0 : body.own_count || 0})`;
    renderExampleFilters();
    byId('examples-list').innerHTML = body.submissions.length ? body.submissions.map(item => `
      <article class="project-card">
        <div class="project-card-main"><div>
          <div class="project-card-name">${escapeHtml(item.title)}</div>
          <div class="project-card-meta">${state.authSession.scenario_admin ? `${escapeHtml(item.submitter_display_name || 'Community contributor')} · ` : ''}Submitted ${escapeHtml(formatDate(item.created_at))} · snapshot v${item.project_version}</div>
          ${item.status === 'published' && item.reviewed_at ? `<div class="project-card-meta">Published ${escapeHtml(formatDate(item.reviewed_at))}</div>` : ''}
        </div><span class="example-status example-status-${escapeAttr(item.status)}">${exampleStatusLabel(item.status)}</span></div>
        ${item.review_note ? `<p class="example-note">${escapeHtml(item.review_note)}</p>` : ''}
        <div class="project-card-actions">
          <button class="btn btn-small" type="button" data-example-review="${escapeAttr(item.id)}">${filter === 'pending' ? 'Review' : 'View suggestion'}</button>
          ${item.public_scenario_id ? `<button class="btn btn-small" type="button" data-public-example="${escapeAttr(item.public_scenario_id)}">Open example</button>` : ''}
        </div>
      </article>`).join('') : '<div class="empty-list">No submissions in this view.</div>';
    byId('examples-previous').hidden = curation.offset === 0;
    byId('examples-next').hidden = !body.has_more;
    setWorkspaceStatus('examples-status', '', 'info');
    if (curation.publishedNotice) {
      const publicId = curation.publishedNotice;
      setWorkspaceStatus('examples-status', 'Published. ', 'success');
      const open = document.createElement('button');
      open.type = 'button'; open.className = 'btn btn-small'; open.textContent = 'Open example';
      open.addEventListener('click', () => { requestCloseModal('modal-workspace'); requestScenarioLoad(publicId); });
      const dismiss = document.createElement('button');
      dismiss.type = 'button'; dismiss.className = 'btn btn-small'; dismiss.textContent = 'Dismiss';
      dismiss.addEventListener('click', () => { curation.publishedNotice = null; setWorkspaceStatus('examples-status'); });
      byId('examples-status').append(open, ' ', dismiss);
    }
    await refreshPublicExampleList();
  } catch (error) {
    if (generation === curation.generation) setWorkspaceStatus('examples-status', error.message, 'error');
  }
}

function renderExampleFilters() {
  const selected = byId('examples-filter').value;
  byId('examples-filter-segments').innerHTML = [['pending', 'Awaiting review'], ['published', 'Published'], ['rejected', 'Declined'], ['withdrawn', 'Withdrawn'], ['mine', 'Mine']].map(([value, label]) =>
    `<button class="btn btn-small" type="button" data-example-filter="${value}" aria-pressed="${value === selected}">${label} <span>${curation.counts[value] || 0}</span></button>`).join('');
}

function exampleStatusLabel(status) {
  return { pending: 'Awaiting review', published: 'Published', rejected: 'Declined', withdrawn: 'Withdrawn' }[status] || status;
}

function exampleSnapshotHTML(scenario, metadata = {}) {
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
    <details class="example-raw"><summary>Inspect portable public content and metadata</summary><pre tabindex="0">${escapeHtml(JSON.stringify({ scenario, ...metadata }, null, 2))}</pre></details>`;
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
    const portable = await apiRequest('/api/scenarios/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: saved.scenario, source_scenario_id: saved.source_scenario_id }),
    });
    if (generation !== curation.reviewGeneration || state.activeProject !== project || state.authSession.user?.id !== account) return;
    curation.review = { kind: 'submit', project: saved, account, scenario: { ...portable.scenario, title: saved.name } };
    showExampleReview(curation.review.scenario, `Saved version ${saved.version}, ${formatDate(saved.updated_at)}`);
  } catch (error) {
    if (generation === curation.reviewGeneration && state.authSession.user?.id === account) setWorkspaceStatus('projects-status', error.message, 'error');
  }
}

async function openExampleReview(id) {
  const account = state.authSession.user?.id;
  const generation = ++curation.reviewGeneration;
  try {
    const item = await apiRequest(`/api/scenario-submissions/${encodeURIComponent(id)}`);
    if (generation !== curation.reviewGeneration || state.authSession.user?.id !== account) return;
    curation.review = { kind: 'review', item, account, scenario: item.portable_scenario || item.scenario };
    showExampleReview(curation.review.scenario, `${exampleStatusLabel(item.status)} · Snapshot of version ${item.project_version}`);
    if (item.review_note) setWorkspaceStatus('example-review-status', item.review_note, 'info');
  } catch (error) {
    if (generation === curation.reviewGeneration && state.authSession.user?.id === account) setWorkspaceStatus('examples-status', error.message, 'error');
  }
}

function showExampleReview(scenario, subtitle) {
  const submitting = curation.review.kind === 'submit';
  const item = curation.review.item;
  byId('example-review-title').textContent = submitting
    ? state.authSession.scenario_admin ? 'Publish as example' : 'Suggest as a community example' : 'Suggestion';
  byId('example-review-subtitle').textContent = subtitle;
  byId('example-public-title').value = submitting ? curation.review.project.name : item.title;
  byId('example-public-summary').value = submitting
    ? ((scenario.description || '').match(/^.*?[.!?](?:\s|$)/s)?.[0] || scenario.description || '').trim().slice(0, 400)
    : item.public_summary || '';
  byId('example-public-title').readOnly = !submitting;
  byId('example-public-summary').readOnly = !submitting;
  byId('example-author-note').value = submitting ? '' : item.author_note || '';
  byId('example-author-note').readOnly = !submitting;
  byId('example-author-note-field').hidden = submitting ? state.authSession.scenario_admin : !item.author_note;
  const name = (state.authSession.user?.display_name || '').trim().replace(/\s+/g, ' ');
  const canAttribute = Boolean(name && !name.includes('@'));
  byId('example-attribution-field').hidden = !submitting || !canAttribute;
  byId('example-attribution-name').textContent = canAttribute ? name : '';
  byId('example-attribute-author').checked = false;
  byId('example-attribute-author').disabled = !submitting || !canAttribute;
  byId('example-attribution-note').textContent = submitting
    ? 'Attribution is optional. Your account email and note to the reviewer stay private.'
    : item.attribution_name ? `Public attribution: ${item.attribution_name}` : 'No public attribution was requested.';
  const counts = [['facts', 'facts'], ['assumptions', 'assumptions'], ['propositions', 'statements'], ['conclusions', 'conclusions'], ['rules', 'rules']]
    .map(([section, label]) => `${Object.keys(scenario[section] || {}).length} ${label}`).join(' · ');
  const documents = scenario.sources || [];
  byId('example-snapshot-summary').innerHTML = `<p class="example-counts">${counts}</p>
    <div class="example-background"><strong>Full public background</strong><p>${escapeHtml(scenario.description || 'No background provided.')}</p></div>
    <strong>${documents.length} reference ${documents.length === 1 ? 'document' : 'documents'}</strong>
    ${documents.length ? `<p class="field-hint">Published in full, including source URLs.</p><ul>${documents.map(source => `<li>${escapeHtml(source.filename)} · ${new TextEncoder().encode(source.text).length.toLocaleString()} bytes of text</li>`).join('')}</ul>`
      : '<p class="field-hint">No reference documents. This is a complete scenario without a corpus.</p>'}`;
  byId('example-consent-panel').hidden = !submitting;
  byId('example-public-consent').checked = false;
  byId('example-full-snapshot').open = false;
  curation.confirmPublish = false;
  byId('example-review-note').value = '';
  byId('example-review-note').removeAttribute('aria-invalid');
  byId('example-review-note-field').hidden = submitting || !state.authSession.scenario_admin
    || !['pending', 'published'].includes(item.status);
  byId('example-review-note-requirement').textContent = item?.is_own && item.status === 'published'
    ? 'optional when removing your own example' : 'required when declining or removing someone else’s example';
  setWorkspaceStatus('example-review-status', '', 'info');
  renderPublicSnapshot();
  renderExampleActions();
  openModal('modal-example-review', submitting ? '#example-public-title' : '#example-review-close');
}

function renderPublicSnapshot() {
  const review = curation.review;
  if (!review) return;
  const title = byId('example-public-title').value;
  const attribution = review.kind === 'submit'
    ? byId('example-attribute-author').checked ? byId('example-attribution-name').textContent : null
    : review.item.attribution_name;
  byId('example-review-snapshot').innerHTML = exampleSnapshotHTML({ ...review.scenario, title }, {
    public_summary: byId('example-public-summary').value, attribution_name: attribution || null,
  });
}

function renderExampleActions() {
  const review = curation.review;
  if (!review) return;
  byId('example-publish-confirmation').hidden = !curation.confirmPublish;
  byId('example-review-actions').hidden = curation.confirmPublish;
  for (const button of byId('example-publish-confirmation').querySelectorAll('button')) button.disabled = curation.busy;
  const buttons = [];
  const button = (action, text, primary = false, disabled = false) => buttons.push(
    `<button class="btn${primary ? ' btn-primary' : ''}" type="button" data-example-action="${action}" ${curation.busy || disabled ? 'disabled' : ''}>${text}</button>`);
  if (review.kind === 'submit') {
    button('submit', state.authSession.scenario_admin ? 'Publish' : 'Submit', true,
      !byId('example-public-consent').checked || !byId('example-public-title').value.trim());
  } else {
    const item = review.item;
    if (state.authSession.scenario_admin && item.status === 'pending') {
      button('reject', 'Decline');
      button('approve', 'Approve', true);
    }
    if (state.authSession.scenario_admin && item.status === 'published') button('unpublish', 'Unpublish');
    if (item.is_own && item.status === 'pending') button('withdraw', 'Withdraw');
  }
  button('close', 'Close');
  byId('example-review-actions').innerHTML = buttons.join('');
}

async function handleExampleDecision(event) {
  let action = event.target.closest('[data-example-action]')?.dataset.exampleAction;
  const review = curation.review;
  if (!action || !review || curation.busy || review.account !== state.authSession.user?.id) return;
  if (['approve', 'confirm-publish', 'reject', 'unpublish'].includes(action) && !state.authSession.scenario_admin) return;
  if (action === 'close') return closeExampleReview();
  if (action === 'cancel-publish') {
    curation.confirmPublish = false; renderExampleActions();
    byId('example-review-actions').querySelector('[data-example-action="approve"]')?.focus();
    return;
  }
  if (action === 'approve') {
    curation.confirmPublish = true; renderExampleActions();
    byId('example-publish-confirmation').querySelector('[data-example-action="confirm-publish"]').focus();
    return;
  }
  if (action === 'confirm-publish') {
    if (!curation.confirmPublish) return;
    action = 'approve';
  }
  const note = byId('example-review-note').value.trim();
  if ((action === 'reject' || (action === 'unpublish' && !review.item.is_own)) && !note) {
    setWorkspaceStatus('example-review-status', 'Add a short reason for the author.', 'error');
    byId('example-review-note').setAttribute('aria-invalid', 'true');
    byId('example-review-note').focus();
    return;
  }
  if (action === 'submit' && !byId('example-public-consent').checked) return;
  if (action === 'unpublish' && !window.confirm('Remove this snapshot from the public examples? Existing private copies are not changed.')) return;
  curation.busy = true;
  const generation = curation.reviewGeneration;
  renderExampleActions();
  setWorkspaceStatus('example-review-status', 'Saving...', 'info');
  try {
    const path = action === 'submit' ? '/api/scenario-submissions' : `/api/scenario-submissions/${encodeURIComponent(review.item.id)}/review`;
    const payload = action === 'submit'
      ? { project_id: review.project.id, expected_version: review.project.version, public_consent: true, publish: !!state.authSession.scenario_admin,
        public_title: byId('example-public-title').value.trim(), public_summary: byId('example-public-summary').value.trim(),
        author_note: byId('example-author-note').value.trim(), attribute_author: byId('example-attribute-author').checked }
      : { expected_version: review.item.version, action, note };
    const item = await apiRequest(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (review.account !== state.authSession.user?.id || generation !== curation.reviewGeneration) return;
    const stillReviewing = curation.review === review;
    if (stillReviewing) closeExampleReview();
    const completedReviewGeneration = curation.reviewGeneration;
    await refreshProjects({ quiet: true });
    if (review.account !== state.authSession.user?.id || completedReviewGeneration !== curation.reviewGeneration) return;
    const message = item.status === 'published' ? 'Published. The scenario is now in Community examples.'
      : item.status === 'pending' ? 'Submitted for review. Check Community examples for updates.'
      : `${exampleStatusLabel(item.status)}. To submit a revised snapshot, edit and save the project first.`;
    curation.publishedNotice = item.public_scenario_id || null;
    showGlobalStatus(message, 'success', item.public_scenario_id ? {
      label: 'Open example', onClick: () => { requestCloseModal('modal-workspace'); requestScenarioLoad(item.public_scenario_id); },
    } : null);
    if (!stillReviewing) { await refreshPublicExampleList(); return; }
    if (state.authSession.scenario_admin) byId('examples-filter').value = action === 'approve' ? 'pending' : 'mine';
    curation.offset = 0;
    openWorkspace('examples');
  } catch (error) {
    if (curation.review === review) setWorkspaceStatus('example-review-status', error.message, 'error');
  } finally {
    if (generation === curation.reviewGeneration) { curation.busy = false; renderExampleActions(); }
  }
}
