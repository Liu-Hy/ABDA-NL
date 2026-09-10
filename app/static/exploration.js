/* Conversation records contain explicitly selected content and scenario data.
   Never serialize application state, auth sessions, or provider options here. */
const conversationStore = { owner: undefined, records: [], activeId: null, error: '', restoring: false };
let inspectorState = null;

function conversationId() {
  return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function activeConversation() {
  return conversationStore.records.find(record => record.id === conversationStore.activeId);
}

function conversationStorageKey(owner) {
  return `abda-conversations-v1:${owner}`;
}

function syncConversationIdentity() {
  const owner = state.authSession?.authenticated ? state.authSession.user?.id || null : null;
  if (conversationStore.owner === owner) return false;
  // Account changes detach in-flight responses and never copy a previous
  // account's draft or shared-project content into the new account's history.
  conversationStore.owner = owner;
  conversationStore.records = [];
  conversationStore.activeId = null;
  conversationStore.error = '';
  conversationStore.restoring = false;
  state.chatMessages = [];
  state.chatPending = false;
  state.chatContextRefs = [];
  state.chatDegraded = false;
  if (inspectorState?.historical) {
    closeModal('modal-derivation');
    document.getElementById('derivation-body')?.replaceChildren();
    inspectorState = null;
  }
  const input = document.getElementById('chat-input');
  if (input) input.value = '';
  if (owner) {
    try {
      const saved = JSON.parse(localStorage.getItem(conversationStorageKey(owner)) || 'null');
      if (saved?.version === 1 && Array.isArray(saved.records)) {
        conversationStore.records = saved.records.filter(record => record && typeof record.id === 'string'
          && typeof record.title === 'string' && Array.isArray(record.messages)
          && record.snapshots && typeof record.snapshots === 'object');
        conversationStore.activeId = saved.active_id;
      }
    } catch {
      conversationStore.error = 'Saved history could not be opened. New messages remain in this tab until storage is available.';
    }
  }
  const record = activeConversation();
  if (record) {
    state.chatMessages = record.messages;
    state.chatContextRefs = record.context_refs || [];
    if (input) input.value = record.draft || '';
    conversationStore.restoring = true;
  } else {
    newConversationRecord();
  }
  return true;
}

function newConversationRecord() {
  const record = {
    id: conversationId(), title: 'New conversation', created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(), messages: [], snapshots: {}, draft: '', context_refs: [],
  };
  conversationStore.records.unshift(record);
  conversationStore.activeId = record.id;
  state.chatMessages = record.messages;
  state.chatContextRefs = record.context_refs;
  state.chatPending = false;
  return record;
}

function saveConversationDraft() {
  const record = activeConversation();
  if (!record) return;
  record.draft = document.getElementById('chat-input')?.value || '';
  record.context_refs = structuredClone(state.chatContextRefs || []);
  record.messages = state.chatMessages;
  record.updated_at = new Date().toISOString();
  const firstQuestion = record.messages.find(message => message.role === 'user');
  if (firstQuestion && !record.fork_of) record.title = firstQuestion.content.slice(0, 70);
  persistConversations();
}

function persistConversations() {
  if (!conversationStore.owner) return;
  try {
    localStorage.setItem(conversationStorageKey(conversationStore.owner), JSON.stringify({
      version: 1, active_id: conversationStore.activeId, records: conversationStore.records,
    }));
    conversationStore.error = '';
  } catch {
    conversationStore.error = 'History could not be saved on this device. Export it now, or delete older conversations to free space.';
  }
  renderConversationControls();
}

function renderConversationControls() {
  const select = document.getElementById('conversation-select');
  const note = document.getElementById('conversation-storage-note');
  if (!select || !note) return;
  select.replaceChildren();
  for (const record of conversationStore.records) {
    const option = document.createElement('option');
    option.value = record.id;
    option.textContent = record.title;
    option.selected = record.id === conversationStore.activeId;
    select.append(option);
  }
  note.textContent = conversationStore.error || (conversationStore.owner
    ? 'Saved automatically in this browser for your account. Delete removes this conversation from this device.'
    : 'History stays in this tab while signed out. Export to keep a copy.');
  const busy = state.chatPending;
  select.disabled = busy;
  for (const id of ['conversation-new', 'conversation-delete']) document.getElementById(id).disabled = busy;
  document.getElementById('conversation-export').disabled = !activeConversation()?.messages.length;
  const degraded = document.getElementById('chat-degraded-note');
  degraded.hidden = !state.chatDegraded;
  degraded.textContent = state.chatDegraded
    ? 'AI is unavailable. Your scenario is still usable: explore derivations, toggle assumptions, or edit it manually. Your question is retained; choose Ask to retry.'
    : '';
}

function startNewConversation() {
  if (state.chatPending) return;
  saveConversationDraft();
  newConversationRecord();
  const input = document.getElementById('chat-input');
  input.value = '';
  state.chatDegraded = false;
  persistConversations();
  renderChat();
  input.focus();
}

function selectConversation(id) {
  if (state.chatPending) return;
  saveConversationDraft();
  const record = conversationStore.records.find(item => item.id === id);
  if (!record) return;
  conversationStore.activeId = id;
  state.chatMessages = record.messages;
  state.chatContextRefs = structuredClone(record.context_refs || []);
  document.getElementById('chat-input').value = record.draft || '';
  state.chatDegraded = false;
  persistConversations();
  renderChat();
}

function deleteConversation() {
  if (state.chatPending) return;
  const record = activeConversation();
  if (!record) return;
  if ((record.messages.length || record.draft) && !window.confirm('Delete this conversation and its saved scenario snapshots from this browser?')) return;
  conversationStore.records = conversationStore.records.filter(item => item.id !== record.id);
  conversationStore.activeId = null;
  newConversationRecord();
  document.getElementById('chat-input').value = '';
  persistConversations();
  renderChat();
}

function downloadConversationJSON(payload, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportConversation() {
  saveConversationDraft();
  const record = activeConversation();
  if (!record) return;
  downloadConversationJSON({ format: 'abda-conversation', version: 1, exported_at: new Date().toISOString(),
    conversation: structuredClone(record) }, `abda-conversation-${record.id}.json`);
}

async function captureConversationSnapshot(context) {
  const scenario = structuredClone(context.bundle.scenario);
  const pendingOps = structuredClone(context.diffOps || []);
  const example = state.scenarios.find(item => item.id === context.scenarioId);
  const sourceId = context.activeProject?.source_scenario_id || context.sharedProject?.source_scenario_id
    || (context.viewKind === 'example' ? example?.source_scenario_id || context.scenarioId : null);
  const portable = await apiRequest('/api/scenarios/export', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario, source_scenario_id: sourceId || null }) });
  return { captured_at: new Date().toISOString(), scenario: portable, af: structuredClone(context.bundle.af),
    pending_ops: pendingOps, view_kind: context.viewKind,
    project_id: context.activeProject?.id || null, project_version: context.activeProject?.version || null };
}

function appendConversationTurnControls(messageElement, message, index) {
  if (message.role !== 'user') return;
  const controls = document.createElement('div');
  controls.className = 'conversation-turn-controls';
  const record = activeConversation();
  const snapshot = record?.snapshots?.[message.snapshot_id];
  if (snapshot) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Scenario used for this question';
    const text = document.createElement('p');
    text.textContent = `${snapshot.scenario?.scenario?.title || 'Scenario'}, ${snapshot.pending_ops?.length || 0} pending changes, ${new Date(snapshot.captured_at).toLocaleString()}.`;
    const download = document.createElement('button');
    download.className = 'btn btn-small';
    download.type = 'button';
    download.textContent = 'Download scenario snapshot';
    download.addEventListener('click', () => downloadConversationJSON(snapshot.scenario, 'conversation-scenario.abda.json'));
    details.append(summary, text, download);
    controls.append(details);
  }
  const fork = document.createElement('button');
  fork.type = 'button';
  fork.className = 'btn btn-small';
  fork.textContent = 'Edit and fork with current scenario';
  fork.disabled = state.chatPending;
  fork.addEventListener('click', () => forkConversationAt(index));
  controls.append(fork);
  messageElement.append(controls);
}

function forkConversationAt(index) {
  if (state.chatPending) return;
  saveConversationDraft();
  const parent = activeConversation();
  const turn = parent?.messages[index];
  if (!turn || turn.role !== 'user') return;
  const fork = newConversationRecord();
  fork.fork_of = { conversation_id: parent.id, message_index: index, new_question_scenario: 'current' };
  fork.title = `Fork: ${turn.content.slice(0, 60)}`;
  fork.messages = structuredClone(parent.messages.slice(0, index));
  const used = new Set(fork.messages.map(message => message.snapshot_id));
  fork.snapshots = Object.fromEntries(Object.entries(parent.snapshots).filter(([id]) => used.has(id)));
  state.chatMessages = fork.messages;
  state.chatContextRefs = [];
  document.getElementById('chat-input').value = turn.content;
  saveConversationDraft();
  renderChat();
  showGlobalStatus('Fork created. Earlier turns retain their snapshots; your edited question will use the current scenario.', 'info');
  document.getElementById('chat-input').focus();
}

function questionContextIsCurrent(ref) {
  return ref.scenario_signature === JSON.stringify(state.bundle?.scenario || null)
    && ref.view_key === conversationViewKey();
}

function conversationViewKey() {
  return `${state.viewKind}:${state.activeProject?.id || state.sharedProject?.id || state.scenario_id || ''}`;
}

function addQuestionDraft(description, kind, id) {
  const input = document.getElementById('chat-input');
  if (!input) return;
  syncConversationIdentity();
  const question = `Can you explain "${description}"?`;
  const start = input.selectionStart ?? input.value.length;
  const before = input.value.slice(0, start);
  // Inserting context never removes a selected portion of an existing draft.
  const after = input.value.slice(start);
  const inserted = `${before && !/\n\n$/.test(before) ? '\n\n' : ''}${question}${after && !/^\n\n/.test(after) ? '\n\n' : ''}`;
  input.value = before + inserted + after;
  input.setSelectionRange(start + inserted.length, start + inserted.length);
  if (kind && id && !(state.chatContextRefs || []).some(ref => ref.kind === kind && ref.id === id && questionContextIsCurrent(ref))) {
    state.chatContextRefs ||= [];
    state.chatContextRefs.push({ kind, id, description, scenario_signature: JSON.stringify(state.bundle?.scenario || null), view_key: conversationViewKey() });
  }
  renderQuestionContext();
  saveConversationDraft();
  revealChatForNarrowLayout();
  input.focus({ preventScroll: !window.matchMedia('(max-width: 780px)').matches });
}

function renderQuestionContext() {
  const container = document.getElementById('chat-context-items');
  if (!container) return;
  container.replaceChildren();
  (state.chatContextRefs || []).forEach((ref, index) => {
    const chip = document.createElement('span');
    chip.className = `chat-context-chip${questionContextIsCurrent(ref) ? '' : ' chat-context-stale'}`;
    const label = document.createElement('span');
    label.textContent = `${ref.kind} ${ref.id}${questionContextIsCurrent(ref) ? '' : ' (earlier scenario)'}`;
    label.title = ref.description;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = '×';
    remove.setAttribute('aria-label', `Remove ${ref.kind} ${ref.id} from question context`);
    remove.addEventListener('click', () => { state.chatContextRefs.splice(index, 1); renderQuestionContext(); saveConversationDraft(); });
    chip.append(label, remove);
    container.append(chip);
  });
}

function appendVerifiedEvidence(bubble, message) {
  const evidence = (message.evidence || []).filter(item => item && item.verified === true);
  if (!evidence.length) return;
  const details = document.createElement('details');
  details.className = 'chat-evidence';
  const summary = document.createElement('summary');
  summary.textContent = `Inspect evidence (${evidence.length})`;
  details.append(summary);
  for (const item of evidence) {
    const block = document.createElement('div');
    block.className = 'chat-evidence-item';
    if (item.kind === 'source' && typeof item.quote === 'string') {
      const citation = document.createElement('p');
      citation.textContent = `${item.source || 'Source'}, characters ${item.start} to ${item.end}. Exact excerpt verified against the supplied source.`;
      const quote = document.createElement('blockquote');
      quote.textContent = item.quote;
      block.append(citation, quote);
    } else if (['rule', 'argument', 'conclusion'].includes(item.kind) && typeof item.id === 'string') {
      const link = document.createElement('button');
      link.type = 'button';
      link.className = 'btn btn-small';
      link.textContent = `Inspect ${item.kind} ${item.id}`;
      link.addEventListener('click', () => {
        const snapshot = activeConversation()?.snapshots?.[message.snapshot_id];
        const bundle = snapshot ? { scenario: snapshot.scenario.scenario, af: snapshot.af } : state.bundle;
        if (item.kind === 'argument') openDerivationInspector(item.id, bundle, Boolean(snapshot));
        else openElementInspector(item.kind, item.id, bundle, Boolean(snapshot));
      });
      block.append(link);
    } else continue;
    details.append(block);
  }
  bubble.append(details);
}

function literalInScenario(literal, scenario) {
  const negated = literal.startsWith('-');
  const id = negated ? literal.slice(1) : literal;
  for (const section of ['facts', 'assumptions', 'propositions', 'conclusions']) {
    const entry = scenario[section]?.[id];
    if (entry) return negated ? entry.negated_description || `it is not the case that ${entry.description}` : entry.description;
  }
  const rule = scenario.rules?.[id];
  if (rule) return negated ? rule.negated_description || `rule ${id} does not apply` : `rule ${id} applies`;
  return literal;
}

function formalElement(id, scenario) {
  const rule = scenario.rules?.[id];
  if (rule) return `${(rule.premises || []).join(', ')} ${rule.type === 'strict' ? '->' : '=>'} ${rule.conclusion} [${id}]`.trim();
  if (scenario.assumptions?.[id]) return `=> ${id} [${id}]`;
  if (scenario.facts?.[id]) return `-> ${id}`;
  return id;
}

function openDerivationForConclusion(id) {
  const args = state.bundle?.af?.arguments || [];
  const candidates = args.filter(arg => arg.conclusion === id || arg.conclusion === `-${id}`);
  if (!candidates.length) return;
  openDerivationInspector(candidates[0].id);
}

function openElementInspector(kind, id, bundle = state.bundle, historical = false) {
  if (!bundle) return;
  const args = bundle.af?.arguments || [];
  const candidates = kind === 'rule' ? args.filter(arg => arg.rules_used?.includes(id))
    : args.filter(arg => arg.conclusion === id || arg.conclusion === `-${id}`);
  inspectorState = { bundle, historical, argId: candidates[0]?.id || null, element: { kind, id } };
  renderDerivationInspector();
  openModal('modal-derivation', '#derivation-argument-select');
}

function openDerivationInspector(argId, bundle = state.bundle, historical = false) {
  if (!bundle) return;
  inspectorState = { bundle, historical, argId, element: null };
  renderDerivationInspector();
  openModal('modal-derivation', '#derivation-argument-select');
}

function inspectArgumentLink(arg, label) {
  if (!arg) return '<span>Unavailable argument</span>';
  return `<button type="button" class="derivation-link" data-inspect-argument="${escapeAttr(arg.id)}">${escapeHtml(label || arg.id)}: ${escapeHtml(arg.conclusion_nl)} <span class="inline-id">[${escapeHtml(arg.label)}]</span></button>`;
}

function renderInspectorElement(kind, id, bundle) {
  const scenario = bundle.scenario;
  const rule = scenario.rules?.[id];
  const description = rule ? `${(rule.premises || []).map(lit => literalInScenario(lit, scenario)).join(' and ')}${rule.premises?.length ? ', therefore ' : ''}${rule.type === 'strict' ? 'necessarily' : 'normally'} ${literalInScenario(rule.conclusion, scenario)}` : literalInScenario(id, scenario);
  return `<div class="derivation-element" data-inspector-element="${escapeAttr(id)}"><p><strong>${escapeHtml(kind)} ${escapeHtml(id)}</strong>: ${escapeHtml(description)}</p><code>${escapeHtml(formalElement(id, scenario))}</code>${rule ? `<p class="derivation-note">${rule.type === 'strict' ? 'Strict rule' : `Defeasible rule, preference block ${rule.block ?? 1}`}${rule.active === false ? ', suspended' : ''}</p>` : ''}${!inspectorState.historical ? `<button type="button" class="btn btn-small" data-locate-kind="${escapeAttr(kind)}" data-locate-id="${escapeAttr(id)}">Locate in explorer</button>` : ''}</div>`;
}

function renderDerivationInspector() {
  const body = document.getElementById('derivation-body');
  if (!body || !inspectorState) return;
  const { bundle, argId, historical, element } = inspectorState;
  const args = bundle.af?.arguments || [];
  const argById = new Map(args.map(arg => [arg.id, arg]));
  const arg = argById.get(argId);
  const attacks = bundle.af?.attacks || [];
  const statusLabel = { in: 'Accepted', out: 'Rejected', undec: 'Undecided' };
  const argumentList = ids => ids.length ? `<ul>${ids.map(id => `<li>${inspectArgumentLink(argById.get(id))}</li>`).join('')}</ul>` : '<p class="derivation-note">None.</p>';
  const attackList = (edges, incoming) => edges.length ? `<ul>${edges.map(edge => `<li><span class="attack-kind">${escapeHtml(edge.type)}</span> ${inspectArgumentLink(argById.get(incoming ? edge.from : edge.to))}</li>`).join('')}</ul>` : '<p class="derivation-note">None. No attack edges in this direction.</p>';
  body.innerHTML = `<p class="derivation-note">${historical ? 'Saved scenario at the time of this answer. ' : ''}Each ID is one individual derivation. Premise links show construction; attack links show conflicts.</p>
    ${element ? renderInspectorElement(element.kind, element.id, bundle) : ''}
    <label for="derivation-argument-select">Individual derivation (${args.length} in this scenario)</label>
    <select id="derivation-argument-select">${args.map(item => `<option value="${escapeAttr(item.id)}"${item.id === argId ? ' selected' : ''}>${escapeHtml(item.id)}: ${escapeHtml(item.conclusion_nl)} [${escapeHtml(item.top_rule)}; ${escapeHtml(statusLabel[item.label] || item.label)}]</option>`).join('')}</select>
    ${arg ? `<section class="derivation-summary"><h3>${escapeHtml(arg.id)}: ${escapeHtml(arg.conclusion_nl)}</h3>
      <p><strong>${escapeHtml(statusLabel[arg.label] || arg.label)}</strong>, computed by ABDA. Conclusion: <code>${escapeHtml(arg.conclusion)}</code>.</p>
      <p class="derivation-note">${arg.label === 'undec' ? 'Undecided is a formal label: this argument is neither accepted nor rejected under grounded semantics.' : ''}</p></section>
      <h3>Applied top rule</h3>${renderInspectorElement(bundle.scenario.rules?.[arg.top_rule] ? 'rule' : (bundle.scenario.assumptions?.[arg.top_rule] ? 'assumption' : 'fact'), arg.top_rule, bundle)}
      <h3>Direct premises</h3>${argumentList(arg.premises || [])}
      <details open><summary>All proper subarguments (${arg.sub_arguments?.length || 0})</summary>${argumentList(arg.sub_arguments || [])}</details>
      <details><summary>All rules used (${arg.rules_used?.length || 0})</summary>${(arg.rules_used || []).map(id => renderInspectorElement(bundle.scenario.rules?.[id] ? 'rule' : (bundle.scenario.assumptions?.[id] ? 'assumption' : 'fact'), id, bundle)).join('')}</details>
      <h3>Incoming attacks</h3>${attackList(attacks.filter(edge => edge.to === arg.id), true)}
      <h3>Outgoing attacks</h3>${attackList(attacks.filter(edge => edge.from === arg.id), false)}
      <details><summary>Other derivations of this exact conclusion</summary>${argumentList(args.filter(other => other.conclusion === arg.conclusion && other.id !== arg.id).map(other => other.id))}</details>` : '<p>No derivation uses this element in the current state.</p>'}`;
  body.querySelector('#derivation-argument-select')?.addEventListener('change', event => {
    inspectorState.argId = event.target.value; inspectorState.element = null; renderDerivationInspector();
    body.querySelector('#derivation-argument-select')?.focus();
  });
  body.querySelectorAll('[data-inspect-argument]').forEach(button => button.addEventListener('click', () => {
    inspectorState.argId = button.dataset.inspectArgument; inspectorState.element = null; renderDerivationInspector();
    body.scrollTop = 0; body.querySelector('#derivation-argument-select')?.focus();
  }));
  body.querySelectorAll('[data-locate-id]').forEach(button => button.addEventListener('click', () => locateExplorerElement(button.dataset.locateKind, button.dataset.locateId)));
}

function locateExplorerElement(kind, id) {
  closeModal('modal-derivation');
  closeModal('modal-af');
  closeModal('modal-game');
  if (kind === 'rule') {
    state.kbTab = 'all'; state.searchQuery = ''; document.getElementById('kb-search-input').value = '';
    switchKBTab('all');
  } else if (kind === 'fact' || kind === 'assumption') switchFactsFilter(kind === 'fact' ? 'facts' : 'assumptions');
  else switchConclusionFilter('all');
  const target = document.querySelector(`[data-element-kind="${CSS.escape(kind)}"][data-element-id="${CSS.escape(id)}"]`);
  if (!target) return;
  target.classList.add('explorer-highlight');
  target.setAttribute('tabindex', '-1');
  target.scrollIntoView({ block: 'center' });
  target.focus({ preventScroll: true });
  setTimeout(() => target.classList.remove('explorer-highlight'), 3000);
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('conversation-new')?.addEventListener('click', startNewConversation);
  document.getElementById('conversation-select')?.addEventListener('change', event => selectConversation(event.target.value));
  document.getElementById('conversation-export')?.addEventListener('click', exportConversation);
  document.getElementById('conversation-delete')?.addEventListener('click', deleteConversation);
  document.getElementById('chat-input')?.addEventListener('input', saveConversationDraft);
  window.addEventListener('pagehide', saveConversationDraft);
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-inspect-conclusion]');
    if (button) openDerivationForConclusion(button.dataset.inspectConclusion);
    const element = event.target.closest('[data-open-element-kind]');
    if (element) openElementInspector(element.dataset.openElementKind, element.dataset.openElementId);
  });
});
