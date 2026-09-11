/* Conversation records contain explicitly selected content and scenario data.
   Never serialize application state, auth sessions, or provider options here. */
const conversationStore = { owner: undefined, records: [], activeId: null, error: '', restoring: false,
  epoch: 0, ready: Promise.resolve(), queue: Promise.resolve(), dirty: new Map(), versions: new Map(),
  deleted: new Set(), writing: new Map(), timer: null, refreshTimer: null, bytes: 0, notice: '' };
const conversationChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('abda-conversation-updates') : null;
let inspectorState = null;
let questionSignatureState = null;

function stateForComposer(refs) { state.chatContextRefs = refs; }
function questionReferenceStatus(ref) { return ref.kind === 'conclusion' ? state.bundle?.af?.labels_by_proposition?.[ref.id] || '' : ''; }

function conversationId() {
  return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function activeConversation() {
  return conversationStore.records.find(record => record.id === conversationStore.activeId);
}

function conversationStorageKey(owner) {
  return `abda-conversations-v1:${owner}`;
}

function conversationHasContent(record) {
  return Boolean(record?.messages.length || record?.draft || record?.context_refs?.length);
}

function useConversation(record) {
  conversationStore.activeId = record.id;
  state.chatMessages = record.messages;
  state.chatPending = Boolean(record.pending);
  chatComposer.restore({ text: record.draft || '', segments: record.draft_segments, refs: record.context_refs || [] });
  try { sessionStorage.setItem(`abda-active-conversation:${conversationStore.owner}`, record.id); } catch { /* In-tab history remains usable. */ }
}

function syncConversationIdentity() {
  const owner = state.authSession?.authenticated ? state.authSession.user?.id || null : null;
  if (conversationStore.owner === owner) return false;
  for (const record of chatRequests.keys()) cancelChatRequest(record, { silent: true });
  conversationStore.owner = owner;
  const epoch = ++conversationStore.epoch;
  clearTimeout(conversationStore.timer);
  clearTimeout(conversationStore.refreshTimer);
  conversationStore.records = [];
  conversationStore.activeId = null;
  conversationStore.error = '';
  conversationStore.notice = '';
  conversationStore.restoring = false;
  conversationStore.dirty.clear();
  conversationStore.writing.clear();
  conversationStore.versions.clear();
  conversationStore.deleted.clear();
  conversationStore.bytes = 0;
  try { conversationStore.storageIntroShown = localStorage.getItem(`abda-history-storage-intro:${owner}`) === '1'; }
  catch { conversationStore.storageIntroShown = false; }
  sourceReader.clear();
  announceChat('');
  state.chatDegraded = false;
  if (inspectorState?.historical) {
    closeModal('modal-derivation');
    document.getElementById('derivation-body')?.replaceChildren();
    inspectorState = null;
  }
  let previousSelection;
  try { previousSelection = sessionStorage.getItem(`abda-active-conversation:${owner}`); } catch { /* Optional selection only. */ }
  newConversationRecord();
  conversationStore.ready = owner ? (async () => {
    try {
      const legacyText = localStorage.getItem(conversationStorageKey(owner));
      const legacy = JSON.parse(legacyText || 'null');
      if (legacy?.version === 1 && Array.isArray(legacy.records)) {
        const records = legacy.records.filter(record => record && typeof record.id === 'string'
          && typeof record.title === 'string' && Array.isArray(record.messages)
          && record.snapshots && typeof record.snapshots === 'object');
        if (records.length !== legacy.records.length) throw new Error('Unrecognized saved history');
        await conversationHistory.migrate(owner, records);
        if (localStorage.getItem(conversationStorageKey(owner)) === legacyText) {
          localStorage.removeItem(conversationStorageKey(owner));
        }
      }
      const saved = await conversationHistory.list(owner);
      if (epoch !== conversationStore.epoch) return;
      const draft = activeConversation();
      conversationStore.bytes = saved.bytes;
      conversationStore.records = saved.records.map(item => item.record);
      for (const item of saved.records) conversationStore.versions.set(item.record.id, item.revision);
      conversationStore.deleted = new Set(saved.deleted);
      if (conversationHasContent(draft)) {
        conversationStore.records.unshift(draft);
        useConversation(draft);
      } else {
        const record = conversationStore.records.find(item => item.id === previousSelection)
          || conversationStore.records.find(item => item.id === legacy?.active_id) || conversationStore.records[0];
        if (record) {
          useConversation(record);
          conversationStore.restoring = !state.bundle;
        }
        else newConversationRecord();
      }
    } catch {
      if (epoch === conversationStore.epoch) conversationStore.error = 'Saved history could not be opened. Existing data was retained; export new work and retry saving.';
    }
    if (epoch === conversationStore.epoch) renderChat();
  })() : Promise.resolve();
  return true;
}

function newConversationRecord() {
  const unused = conversationStore.records.find(record => !conversationHasContent(record) && !record.pending);
  if (unused) { useConversation(unused); return unused; }
  const record = {
    id: conversationId(), title: 'Untitled conversation', created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(), messages: [], snapshots: {}, draft: '', draft_segments: [], context_refs: [],
  };
  conversationStore.records.unshift(record);
  useConversation(record);
  return record;
}

function saveConversationDraft() {
  const record = activeConversation();
  if (!record) return;
  const draft = chatComposer.snapshot();
  record.draft = draft.text;
  record.draft_segments = draft.segments;
  record.context_refs = draft.refs;
  record.messages = state.chatMessages;
  record.updated_at = new Date().toISOString();
  const firstQuestion = record.messages.find(message => message.role === 'user');
  if (firstQuestion && !record.fork_of && !record.concurrent_copy_of) record.title = firstQuestion.content.slice(0, 70);
  if (!conversationHasContent(record)) return;
  conversationStore.dirty.set(record.id, record);
  clearTimeout(conversationStore.timer);
  conversationStore.timer = setTimeout(flushConversationWrites, 250);
  renderConversationControls();
}

function persistConversations(record = activeConversation()) {
  if (record && conversationHasContent(record)) conversationStore.dirty.set(record.id, record);
  return flushConversationWrites();
}

function flushConversationWrites() {
  clearTimeout(conversationStore.timer);
  const owner = conversationStore.owner;
  const epoch = conversationStore.epoch;
  const entries = [...conversationStore.dirty.values()];
  conversationStore.dirty.clear();
  if (!owner) return Promise.resolve();
  for (const record of entries) conversationStore.writing.set(record, (conversationStore.writing.get(record) || 0) + 1);
  const release = record => {
    const count = conversationStore.writing.get(record) || 0;
    if (count <= 1) conversationStore.writing.delete(record);
    else conversationStore.writing.set(record, count - 1);
  };
  conversationStore.queue = conversationStore.queue.then(async () => {
    await conversationStore.ready;
    let needsRefresh = false;
    for (const record of entries) {
      if (epoch !== conversationStore.epoch || conversationStore.deleted.has(record.id)) {
        release(record); continue;
      }
      const expectedRevision = conversationStore.versions.get(record.id) || 0;
      try {
        // Capture mutable fields now, retaining the immutable scenario objects
        // so the storage encoder can reuse their source/snapshot digests.
        const snapshot = {
          ...structuredClone({ ...record, snapshots: undefined, pending: undefined }),
          snapshots: { ...record.snapshots },
        };
        const result = await conversationHistory.save(owner, snapshot, expectedRevision,
          () => epoch === conversationStore.epoch && !conversationStore.deleted.has(record.id));
        if (epoch !== conversationStore.epoch || result.cancelled) continue;
        if (result.deleted) {
          needsRefresh = true;
          forgetConversation(record.id);
          conversationStore.notice = 'This conversation was deleted in another tab. Its late updates were discarded.';
        } else {
          if (result.conflict) {
            needsRefresh = true;
            const originalId = record.id;
            if (conversationStore.activeId === originalId) conversationStore.activeId = result.id;
            record.id = result.id;
            record.title = result.title;
            record.concurrent_copy_of = originalId;
            conversationStore.notice = 'Another tab edited this conversation. Both versions were kept; this one is a concurrent copy.';
          }
          conversationStore.versions.set(record.id, result.revision);
          conversationStore.error = '';
          if (!conversationStore.storageIntroShown) {
            conversationStore.storageIntroShown = true;
            try { localStorage.setItem(`abda-history-storage-intro:${owner}`, '1'); } catch { /* Optional one-time explanation. */ }
            conversationStore.notice ||= 'Saved automatically in this browser for your account. Export to keep a separate copy.';
          }
        }
        conversationChannel?.postMessage({ owner });
      } catch {
        conversationStore.dirty.set(record.id, record);
        conversationStore.error = 'History could not be saved on this device. Export your work, delete older conversations to free space, then retry saving.';
      } finally {
        release(record);
      }
    }
    if (epoch === conversationStore.epoch) {
      // Ordinary draft writes do not reload every saved scenario and source.
      // Refresh the list and capacity once typing has settled, or on a conflict.
      clearTimeout(conversationStore.refreshTimer);
      if (needsRefresh) await refreshConversationRecords();
      else conversationStore.refreshTimer = setTimeout(refreshConversationRecords, 1000);
      renderConversationControls();
    }
  });
  return conversationStore.queue;
}

function forgetConversation(id) {
  const record = conversationStore.records.find(item => item.id === id);
  if (record) cancelChatRequest(record, { silent: true });
  conversationStore.deleted.add(id);
  conversationStore.dirty.delete(id);
  conversationStore.records = conversationStore.records.filter(record => record.id !== id);
  if (conversationStore.activeId === id) {
    conversationStore.activeId = null;
    newConversationRecord();
    renderChat();
  }
}

async function refreshConversationRecords() {
  const owner = conversationStore.owner;
  const epoch = conversationStore.epoch;
  if (!owner) return;
  try {
    const saved = await conversationHistory.list(owner);
    if (epoch !== conversationStore.epoch) return;
    conversationStore.bytes = saved.bytes;
    for (const id of saved.deleted) forgetConversation(id);
    for (const { record, revision } of saved.records) {
      const local = conversationStore.records.find(item => item.id === record.id);
      if (!local) { conversationStore.records.push(record); conversationStore.versions.set(record.id, revision); }
      else if (!conversationStore.dirty.has(record.id) && !conversationStore.writing.has(local) && !local.pending
          && revision > (conversationStore.versions.get(record.id) || 0)) {
        Object.assign(local, record);
        conversationStore.versions.set(record.id, revision);
        if (record.id === conversationStore.activeId) { useConversation(local); renderChat(); }
      }
    }
    renderConversationControls();
  } catch { /* A failed save already supplies recovery controls. Keep in-tab content. */ }
}

conversationChannel?.addEventListener('message', event => {
  if (event.data?.owner === conversationStore.owner) refreshConversationRecords();
});

function renderConversationControls() {
  const select = document.getElementById('conversation-select');
  const note = document.getElementById('conversation-storage-note');
  if (!select || !note) return;
  select.replaceChildren();
  for (const record of conversationStore.records) {
    const option = document.createElement('option');
    option.value = record.id;
    const latest = [...record.messages].reverse().find(message => message.snapshot_id);
    const scenarioName = record.snapshots?.[latest?.snapshot_id]?.scenario?.scenario?.title || 'Unsent draft';
    const date = new Date(record.updated_at || record.created_at).toLocaleDateString();
    option.textContent = `${record.title} · ${scenarioName} · ${date}` + (record.pending ? ' (answer pending)' : record.unread ? ' (new answer)' : '');
    option.selected = record.id === conversationStore.activeId;
    select.append(option);
  }
  const size = conversationStore.bytes ? ` About ${(conversationStore.bytes / 1048576).toFixed(1)} MB stored.` : '';
  const routine = conversationStore.owner
    ? `Saved automatically in this browser for your account.${size} Delete removes this conversation from this device.`
    : 'History stays in this tab while signed out. Export to keep a copy.';
  select.title = routine;
  document.getElementById('conversation-storage-description').textContent = routine;
  const status = conversationStore.error || conversationStore.notice || '';
  note.hidden = !status;
  if (note.textContent !== status) note.textContent = status;
  document.getElementById('conversation-recovery').hidden = !conversationStore.error;
  document.getElementById('conversation-export').disabled = !conversationHasContent(activeConversation());
  document.getElementById('conversation-delete').disabled = !conversationHasContent(activeConversation());
  const degraded = document.getElementById('chat-degraded-note');
  degraded.hidden = !state.chatDegraded;
  degraded.textContent = state.chatDegraded
    ? 'AI is unavailable. Your scenario is still usable: explore derivations, toggle assumptions, or edit it manually. Your question is retained; choose Ask to retry.'
    : '';
}

function startNewConversation() {
  saveConversationDraft();
  newConversationRecord();
  state.chatDegraded = false;
  renderChat();
  document.getElementById('chat-input').focus();
}

function selectConversation(id) {
  saveConversationDraft();
  const record = conversationStore.records.find(item => item.id === id);
  if (!record) return;
  record.unread = false;
  conversationStore.notice = '';
  useConversation(record);
  state.chatDegraded = false;
  renderChat();
}

async function deleteConversation() {
  const record = activeConversation();
  if (!record) return;
  if (conversationHasContent(record) && !window.confirm('Delete this conversation and its saved scenario snapshots from this browser? A pending answer will also be discarded.')) return;
  const owner = conversationStore.owner;
  const epoch = conversationStore.epoch;
  // In-memory suppression is immediate; the transaction settles deletion
  // against writes already in flight and prevents stale tabs resurrecting it.
  conversationStore.deleted.add(record.id);
  conversationStore.dirty.delete(record.id);
  cancelChatRequest(record, { silent: true });
  try {
    if (owner) await conversationHistory.remove(owner, record.id);
    if (epoch !== conversationStore.epoch) return;
    forgetConversation(record.id);
    conversationStore.error = '';
    conversationChannel?.postMessage({ owner });
    await refreshConversationRecords();
    if (conversationStore.dirty.size) await flushConversationWrites();
    renderChat();
  } catch {
    conversationStore.deleted.delete(record.id);
    conversationStore.error = 'Deletion could not be saved. Export your work and retry when browser storage is available.';
    renderConversationControls();
  }
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

async function exportConversation() {
  saveConversationDraft();
  const record = activeConversation();
  if (!record) return;
  const ownerEpoch = conversationStore.epoch;
  await persistConversations(record);
  if (ownerEpoch !== conversationStore.epoch || conversationStore.deleted.has(record.id)) return;
  const { pending, ...exported } = record;
  downloadConversationJSON({ format: 'abda-conversation', version: 1, exported_at: new Date().toISOString(),
    conversation: structuredClone(exported) }, `abda-conversation-${record.id}.json`);
}

async function captureConversationSnapshot(context, signal) {
  const scenario = structuredClone(context.bundle.scenario);
  const pendingOps = structuredClone(context.diffOps || []);
  const example = state.scenarios.find(item => item.id === context.scenarioId);
  const sourceId = context.activeProject?.source_scenario_id || context.sharedProject?.source_scenario_id
    || (context.viewKind === 'example' ? example?.source_scenario_id || context.scenarioId : null);
  const portable = await apiRequest('/api/scenarios/export', { method: 'POST', signal,
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
  const fork = document.createElement('button');
  fork.type = 'button';
  fork.className = 'btn btn-small conversation-edit-turn';
  fork.textContent = 'Edit in new chat';
  fork.title = 'Edit this question in a new conversation using the current scenario';
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
  const saved = parent.snapshots?.[turn.snapshot_id];
  const bundle = saved ? { scenario: saved.scenario.scenario, af: saved.af } : null;
  const refs = (turn.context_refs || []).map(ref => ({ ...ref,
    description: describeQuestionReference(ref, bundle) || `${ref.kind} ${ref.id}` }));
  const segments = composerModel.restore({ text: turn.content, segments: turn.segments, refs }).map(segment =>
    segment.type === 'reference' ? { ...segment, ref: { ...segment.ref, scenario_signature: '', view_key: '' } } : segment);
  chatComposer.restore({ text: composerModel.text(segments), segments });
  saveConversationDraft();
  renderChat();
  showGlobalStatus('Fork created. Earlier turns retain their snapshots; your edited question will use the current scenario. Refresh or remove any earlier context items before asking.', 'info');
  chatComposer.focus();
}

function currentScenarioSignature() {
  const scenario = state.bundle?.scenario || null;
  if (questionSignatureState?.scenario === scenario) return questionSignatureState;
  const entry = { scenario, text: JSON.stringify(scenario), value: null };
  entry.promise = conversationHistory.signature(entry.text).then(value => {
    entry.value = value;
    if (questionSignatureState === entry) {
      chatComposer.compactSignatures(entry.text, value);
      renderQuestionContext();
    }
    return value;
  }).catch(() => null); // In-tab context remains usable if browser storage is unavailable.
  questionSignatureState = entry;
  return entry;
}

function questionContextIsCurrent(ref) {
  const signature = currentScenarioSignature();
  return (ref.scenario_signature === signature.text || ref.scenario_signature === signature.value)
    && ref.view_key === conversationViewKey();
}

function currentQuestionReference(kind, id) {
  const description = describeQuestionReference({ kind, id }, state.bundle);
  if (!description) return null;
  const signature = currentScenarioSignature();
  return { kind, id, description,
    scenario_signature: signature.value || signature.text, view_key: conversationViewKey() };
}

function conversationViewKey() {
  return `${state.viewKind}:${state.activeProject?.id || state.sharedProject?.id || state.scenario_id || ''}`;
}

function addQuestionDraft(description, kind, id) {
  syncConversationIdentity();
  const signature = currentScenarioSignature();
  const ref = { kind, id, description, scenario_signature: signature.value || signature.text, view_key: conversationViewKey() };
  if (chatComposer.insertReference(ref)) {
    revealChatForNarrowLayout(); chatComposer.focus();
  }
}

function renderQuestionContext() {
  chatComposer.refreshPresentation();
  const scenario = state.bundle?.scenario;
  const note = document.getElementById('chat-no-documents');
  if (note) note.hidden = !scenario || Boolean(scenario.corpus?.length || scenario.sources?.length);
}

function describeQuestionReference(ref, bundle) {
  if (!bundle?.scenario || !['rule', 'fact', 'assumption', 'conclusion', 'argument'].includes(ref.kind)) return null;
  const scenario = bundle.scenario;
  if (ref.kind === 'argument') {
    const arg = bundle.af?.arguments?.find(item => item.id === ref.id);
    return arg ? `${arg.conclusion_nl || literalInScenario(arg.conclusion, scenario)} (${arg.id})` : null;
  }
  if (ref.kind === 'rule') {
    const rule = Object.hasOwn(scenario.rules || {}, ref.id) ? scenario.rules[ref.id] : null;
    if (!rule) return null;
    return rule.description || `${(rule.premises || []).map(id => literalInScenario(id, scenario)).join(' and ')}${rule.premises?.length ? ', therefore ' : ''}${rule.type === 'strict' ? 'necessarily' : 'normally'} ${literalInScenario(rule.conclusion, scenario)}`;
  }
  const id = ref.id.startsWith('-') ? ref.id.slice(1) : ref.id;
  const sections = ref.kind === 'fact' ? ['facts'] : ref.kind === 'assumption' ? ['assumptions'] : ['facts', 'assumptions', 'propositions', 'conclusions'];
  return sections.some(section => Object.hasOwn(scenario[section] || {}, id)) || Object.hasOwn(bundle.af?.labels_by_proposition || {}, ref.id)
    ? literalInScenario(ref.id, scenario) : null;
}

function savedBundleForMessage(message) {
  const snapshot = activeConversation()?.snapshots?.[message.snapshot_id];
  return snapshot?.scenario?.scenario && snapshot.af ? { scenario: snapshot.scenario.scenario, af: snapshot.af } : null;
}

function formalReferenceButton(ref, bundle, label = null) {
  const button = document.createElement('button'); button.type = 'button'; button.className = 'chat-formal-reference';
  const description = describeQuestionReference(ref, bundle);
  button.textContent = label || description || `${ref.kind} ${ref.id}`;
  button.title = `${ref.kind} ${ref.id}: ${description || 'Unavailable in the saved scenario'}`;
  button.setAttribute('aria-label', `Inspect ${ref.kind} ${ref.id}: ${description || 'Unavailable in the saved scenario'}`);
  button.disabled = !description;
  if (description) button.addEventListener('click', () => {
    if (ref.kind === 'argument') openDerivationInspector(ref.id, bundle, true);
    else openElementInspector(ref.kind, ref.id, bundle, true);
  });
  return button;
}

function appendVerifiedEvidence(bubble, message) {
  const sources = (message.evidence || []).filter(item => item?.verified === true && item.kind === 'source' && typeof item.quote === 'string');
  const snapshot = activeConversation()?.snapshots?.[message.snapshot_id];
  if (sources.length) {
    const details = document.createElement('details'); details.className = 'chat-evidence'; details.open = true;
    const summary = document.createElement('summary'); summary.textContent = `Sources (${sources.length})`; details.append(summary);
    for (const item of sources) {
      const card = document.createElement('article'); card.className = 'chat-source-card';
      const heading = document.createElement('div'); heading.className = 'chat-source-heading';
      const name = document.createElement('strong'); name.textContent = item.source;
      const assurance = document.createElement('details'); assurance.className = 'source-assurance';
      const tag = document.createElement('summary'); tag.textContent = item.evidence_role === 'quotation' ? 'Quotation' : item.evidence_role === 'context' ? 'Context' : 'Excerpt';
      const meaning = item.evidence_role === 'quotation'
        ? 'Quotation matched to this supplied source span. This verifies the wording, not the claim.'
        : item.evidence_role === 'context'
          ? 'Suggested reading context from the supplied source. This is not a matched quotation or verified support for the claim.'
          : 'Supplied source excerpt. This verifies the source span, not quotation matching or support for the claim.';
      tag.title = meaning; const explanation = document.createElement('p'); explanation.textContent = meaning;
      assurance.append(tag, explanation); heading.append(name, assurance); card.append(heading);
      const source = sourceReaderData.sources(snapshot).find(source => source.filename === item.source);
      const location = sourceReaderData.locate(source, item);
      const paragraph = sourceReaderData.paragraph(source, location);
      const quote = document.createElement('blockquote');
      if (paragraph && sources.length <= 2) sourceReader.markedText(quote, paragraph.text, paragraph);
      else quote.textContent = item.quote;
      card.append(quote);
      if (paragraph && sources.length > 2) {
        const context = document.createElement('details'); context.className = 'chat-source-context';
        const label = document.createElement('summary'); label.textContent = 'Surrounding passage';
        const passage = document.createElement('blockquote'); sourceReader.markedText(passage, paragraph.text, paragraph);
        context.append(label, passage); card.append(context);
      }
      if (!location) { const missing = document.createElement('p'); missing.className = 'source-location-note'; missing.textContent = 'Location in the saved document could not be confirmed.'; card.append(missing); }
      const open = document.createElement('button'); open.type = 'button'; open.className = 'btn btn-small'; open.textContent = 'Open in Sources';
      open.setAttribute('aria-label', `Open ${item.source} in Sources`);
      open.addEventListener('click', () => openSourcesReader({ snapshot, historical: true, evidence: item, selectedSource: item.source }));
      card.append(open); details.append(card);
    }
    bubble.append(details);
  }

}

function appendUserQuestion(bubble, message) {
  if (!Array.isArray(message.segments) || composerModel.text(message.segments) !== message.content) {
    bubble.textContent = String(message.content || ''); return;
  }
  const bundle = savedBundleForMessage(message);
  for (const item of composerModel.normalize(message.segments)) {
    if (item.type === 'text') bubble.append(document.createTextNode(item.text));
    else bubble.append(formalReferenceButton(item.ref, bundle, `"${item.ref.description}"`));
  }
}

function appendInlineReferenceLinks(container, message) {
  const bundle = savedBundleForMessage(message); if (!bundle) return;
  const resolve = id => {
    const candidates = [];
    for (const [kind, section] of [['rule', 'rules'], ['fact', 'facts'], ['assumption', 'assumptions'], ['conclusion', 'conclusions']]) {
      if (Object.hasOwn(bundle.scenario[section] || {}, id)) candidates.push({ kind, id });
    }
    const base = id.startsWith('-') ? id.slice(1) : id;
    const knownNegation = id.startsWith('-') && ['facts', 'assumptions', 'propositions', 'conclusions', 'rules'].some(section => Object.hasOwn(bundle.scenario[section] || {}, base));
    if (!candidates.length && (knownNegation || Object.hasOwn(bundle.scenario.propositions || {}, id) || Object.hasOwn(bundle.af.labels_by_proposition || {}, id)
        || bundle.af.arguments?.some(arg => arg.conclusion === id))) candidates.push({ kind: 'conclusion', id });
    if (bundle.af.arguments?.some(arg => arg.id === id)) candidates.push({ kind: 'argument', id });
    return candidates.length === 1 ? candidates[0] : null;
  };
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT); const texts = [];
  while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('a,button,code,pre,.chat-evidence,.chat-formal-context')) texts.push(walker.currentNode);
  for (const text of texts) {
    const matches = [...text.data.matchAll(/\[(-?[A-Za-z_][A-Za-z0-9_]*)\]/g)];
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment(); let at = 0;
    for (const match of matches) {
      fragment.append(document.createTextNode(text.data.slice(at, match.index)));
      const ref = resolve(match[1]); fragment.append(ref ? formalReferenceButton(ref, bundle, match[0]) : document.createTextNode(match[0]));
      at = match.index + match[0].length;
    }
    fragment.append(document.createTextNode(text.data.slice(at))); text.replaceWith(fragment);
  }
}

function literalInScenario(literal, scenario) {
  const negated = literal.startsWith('-');
  const id = negated ? literal.slice(1) : literal;
  for (const section of ['facts', 'assumptions', 'propositions', 'conclusions']) {
    const entry = Object.hasOwn(scenario[section] || {}, id) ? scenario[section][id] : null;
    if (entry) return negated ? entry.negated_description || `it is not the case that ${entry.description}` : entry.description;
  }
  const rule = Object.hasOwn(scenario.rules || {}, id) ? scenario.rules[id] : null;
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
  openElementInspector('conclusion', id);
}

function preferredElementArgument(kind, id, bundle) {
  const args = bundle.af?.arguments || [];
  const candidates = kind === 'rule' ? args.filter(arg => arg.top_rule === id)
    : args.filter(arg => arg.conclusion === id);
  const preferred = { accepted: 'in', rejected: 'out', undecided: 'undec' }[bundle.af?.labels_by_proposition?.[id]];
  return candidates.find(arg => arg.label === preferred) || candidates[0] || null;
}

function openElementInspector(kind, id, bundle = state.bundle, historical = false, navigation = null) {
  if (!bundle) return;
  argumentNavigation = navigation || newArgumentNavigation(bundle, historical);
  if (!navigation) graphContext = null;
  inspectorState = { bundle, historical, argId: preferredElementArgument(kind, id, bundle)?.id || null,
    element: { kind, id }, scope: { kind, id }, showAll: false };
  renderDerivationInspector();
  openModal('modal-derivation', '#derivation-argument-select');
}

function openDerivationInspector(argId, bundle = state.bundle, historical = false, navigation = null) {
  if (!bundle) return;
  argumentNavigation = navigation || newArgumentNavigation(bundle, historical);
  if (!navigation) graphContext = null;
  const argument = bundle.af?.arguments?.find(arg => arg.id === argId);
  inspectorState = { bundle, historical, argId, element: null,
    scope: { kind: 'conclusion', id: argument?.conclusion }, showAll: false };
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
  const scope = inspectorState.scope || element;
  const scoped = scope ? args.filter(item => scope.kind === 'rule'
    ? item.top_rule === scope.id : item.conclusion === scope.id) : args;
  const options = inspectorState.showAll ? args : scoped;
  const argById = new Map(args.map(arg => [arg.id, arg]));
  const arg = argById.get(argId);
  const attacks = bundle.af?.attacks || [];
  const statusLabel = { in: 'Accepted', out: 'Rejected', undec: 'Undecided' };
  const argumentList = ids => ids.length ? `<ul>${ids.map(id => `<li>${inspectArgumentLink(argById.get(id))}</li>`).join('')}</ul>` : '<p class="derivation-note">None.</p>';
  const attackList = (edges, incoming) => edges.length ? `<ul>${edges.map(edge => `<li><span class="attack-kind">${escapeHtml(edge.type)}</span> ${inspectArgumentLink(argById.get(incoming ? edge.from : edge.to))}</li>`).join('')}</ul>` : '<p class="derivation-note">None. No attack edges in this direction.</p>';
  body.innerHTML = `${argumentNavigationMarkup('derivation', arg?.id)}
    <p class="derivation-note">${historical ? 'Saved scenario at the time of this answer. ' : ''}Each ID is one individual derivation. Premise links show construction; attack links show conflicts.</p>
    ${element ? renderInspectorElement(element.kind, element.id, bundle) : ''}
    <label for="derivation-argument-select">${inspectorState.showAll ? 'All derivations in this scenario' : scope?.kind === 'rule' ? 'Derivations using this top rule' : 'Derivations of this exact conclusion'} (${options.length})</label>
    <select id="derivation-argument-select">${!arg ? '<option value="" selected>No matching derivation.</option>' : ''}${options.map((item, index) => `<option value="${escapeAttr(item.id)}"${item.id === argId ? ' selected' : ''}>${index + 1}. ${escapeHtml(item.id)}: ${escapeHtml(item.conclusion_nl)} [${escapeHtml(item.top_rule)}; ${escapeHtml(statusLabel[item.label] || item.label)}]${item.premises?.length ? ` via ${escapeHtml(item.premises.join(', '))}` : ''}</option>`).join('')}</select>
    ${scoped.length !== args.length ? `<label class="state-filter"><input type="checkbox" id="derivation-show-all" ${inspectorState.showAll ? 'checked' : ''}> Browse all ${args.length} derivations</label>` : ''}
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
    inspectorState.argId = event.target.value; renderDerivationInspector();
    body.querySelector('#derivation-argument-select')?.focus();
  });
  body.querySelector('#derivation-show-all')?.addEventListener('change', event => {
    inspectorState.showAll = event.target.checked;
    if (!inspectorState.showAll && !scoped.some(item => item.id === inspectorState.argId)) inspectorState.argId = scoped[0]?.id || null;
    renderDerivationInspector(); body.querySelector('#derivation-show-all')?.focus();
  });
  body.querySelectorAll('[data-inspect-argument]').forEach(button => button.addEventListener('click', () => {
    const selected = argById.get(button.dataset.inspectArgument);
    if (!selected) return;
    inspectorState.argId = selected.id; inspectorState.element = null;
    inspectorState.scope = { kind: 'conclusion', id: selected.conclusion }; inspectorState.showAll = false;
    renderDerivationInspector();
    body.scrollTop = 0; body.querySelector('#derivation-argument-select')?.focus();
  }));
  body.querySelectorAll('[data-locate-id]').forEach(button => button.addEventListener('click', () => locateExplorerElement(button.dataset.locateKind, button.dataset.locateId)));
  bindArgumentNavigation(body, 'derivation', arg?.id);
}

function locateExplorerElement(kind, id) {
  closeModal('modal-derivation');
  closeModal('modal-af');
  closeModal('modal-game');
  if (kind === 'rule') {
    state.kbTab = 'all'; state.searchQuery = ''; document.getElementById('kb-search-input').value = '';
    state.rulesChangedOnly = false; state.rulesSuspendedOnly = false;
    document.getElementById('rules-changed').checked = false; document.getElementById('rules-suspended').checked = false;
    switchKBTab('all');
  } else if (kind === 'fact' || kind === 'assumption') {
    state.factsChangedOnly = false; state.factsSuspendedOnly = false;
    document.getElementById('facts-changed').checked = false; document.getElementById('facts-suspended').checked = false;
    switchFactsFilter(kind === 'fact' ? 'facts' : 'assumptions');
  }
  else switchConclusionFilter('all');
  const target = document.querySelector(`[data-element-kind="${CSS.escape(kind)}"][data-element-id="${CSS.escape(id)}"]`);
  if (!target) return;
  target.classList.add('explorer-highlight');
  target.setAttribute('tabindex', '-1');
  target.scrollIntoView({ block: 'center' });
  target.focus({ preventScroll: true });
  setTimeout(() => target.classList.remove('explorer-highlight'), 3000);
}

async function exportAllConversations() {
  const epoch = conversationStore.epoch;
  saveConversationDraft();
  await refreshConversationRecords();
  if (epoch !== conversationStore.epoch) return;
  downloadConversationJSON({ format: 'abda-conversations', version: 1,
    conversations: structuredClone(conversationStore.records).map(({ pending, ...record }) => record) }, 'abda-conversations.json');
}

document.addEventListener('DOMContentLoaded', () => {
  chatComposer.init();
  document.getElementById('conversation-new')?.addEventListener('click', startNewConversation);
  document.getElementById('conversation-select')?.addEventListener('change', event => selectConversation(event.target.value));
  document.getElementById('conversation-export')?.addEventListener('click', exportConversation);
  document.getElementById('conversation-delete')?.addEventListener('click', deleteConversation);
  document.getElementById('conversation-retry-save')?.addEventListener('click', () => persistConversations());
  document.getElementById('conversation-export-all')?.addEventListener('click', exportAllConversations);
  document.getElementById('conversation-recovery-export')?.addEventListener('click', exportAllConversations);
  window.addEventListener('pagehide', () => { saveConversationDraft(); flushConversationWrites(); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') { saveConversationDraft(); flushConversationWrites(); }
    else refreshConversationRecords();
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.conversation-actions') || event.target.closest('.conversation-actions button')) {
      document.querySelectorAll('.conversation-actions[open]').forEach(menu => { menu.open = false; });
    }
    const button = event.target.closest('[data-inspect-conclusion]');
    if (button) openDerivationForConclusion(button.dataset.inspectConclusion);
    const element = event.target.closest('[data-open-element-kind]');
    if (element) openElementInspector(element.dataset.openElementKind, element.dataset.openElementId);
  });
});
