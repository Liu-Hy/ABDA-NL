/* Plain prose and explicit, atomic references. No reference is inferred from text. */
const composerModel = (() => {
  const referenceKinds = new Set(['rule', 'fact', 'assumption', 'conclusion', 'argument']);
  function normalize(segments) {
    const result = [];
    for (const segment of segments || []) {
      if (segment?.type === 'text' && typeof segment.text === 'string') {
        if (!segment.text) continue;
        if (result.at(-1)?.type === 'text') result.at(-1).text += segment.text;
        else result.push({ type: 'text', text: segment.text });
      } else if (segment?.type === 'reference' && referenceKinds.has(segment.ref?.kind)
          && typeof segment.ref.id === 'string' && segment.ref.id) {
        const ref = segment.ref;
        result.push({ type: 'reference', ref: {
          kind: ref.kind, id: ref.id,
          description: typeof ref.description === 'string' ? ref.description : `${ref.kind} ${ref.id}`,
          scenario_signature: typeof ref.scenario_signature === 'string' ? ref.scenario_signature : '',
          view_key: typeof ref.view_key === 'string' ? ref.view_key : '',
        } });
      }
    }
    return result;
  }
  const text = segments => normalize(segments).map(item => item.type === 'text' ? item.text : `"${item.ref.description}"`).join('');
  const length = segments => normalize(segments).reduce((sum, item) => sum + (item.type === 'text' ? item.text.length : 1), 0);
  function references(segments) {
    const seen = new Set();
    return normalize(segments).filter(item => {
      if (item.type !== 'reference') return false;
      const key = JSON.stringify([item.ref.kind, item.ref.id]);
      if (seen.has(key)) return false;
      seen.add(key); return true;
    }).map(item => ({ ...item.ref }));
  }
  function slice(segments, start, end = length(segments)) {
    let offset = 0;
    const result = [];
    for (const item of normalize(segments)) {
      const size = item.type === 'text' ? item.text.length : 1;
      if (end > offset && start < offset + size) {
        result.push(item.type === 'reference' ? item : { type: 'text', text: item.text.slice(Math.max(0, start - offset), end - offset) });
      }
      offset += size;
    }
    return normalize(result);
  }
  const replace = (segments, start, end, inserted = []) => normalize([...slice(segments, 0, start), ...inserted, ...slice(segments, end)]);
  function restore({ text: prose = '', segments, refs = [] } = {}) {
    // Older open tabs may change plain text while retaining an obsolete segment field.
    // Never let such a field overwrite the actual draft or archived question.
    if (Array.isArray(segments) && text(segments) === prose) return normalize(segments);
    const result = [{ type: 'text', text: typeof prose === 'string' ? prose : '' }];
    for (const ref of refs) result.push({ type: 'text', text: '\n' }, { type: 'reference', ref });
    return normalize(result);
  }
  return { normalize, text, length, references, slice, replace, restore };
})();

const chatComposer = (() => {
  let editor, segments = [], composing = false, compositionBefore, history = [], redo = [];
  let selection = { start: 0, end: 0 }, pendingSelection, initialized = false;
  const tokenValues = new WeakMap();
  const root = () => editor || (editor = document.getElementById('chat-input'));
  const sizeOf = node => tokenValues.has(node) ? 1 : node.nodeType === 3 ? node.data.length
    : node.nodeName === 'BR' ? 1 : [...node.childNodes].reduce((sum, child) => sum + sizeOf(child), 0);
  function pointOffset(node, offset, endPoint = false) {
    let total = 0, found = false;
    function walk(current) {
      if (found) return;
      if (current === node) {
        total += current.nodeType === 3 ? offset : [...current.childNodes].slice(0, offset).reduce((sum, child) => sum + sizeOf(child), 0);
        found = true; return;
      }
      if (tokenValues.has(current) && current.contains(node)) { total += endPoint ? 1 : 0; found = true; return; }
      if (tokenValues.has(current) || current.nodeType === 3 || current.nodeName === 'BR') total += sizeOf(current);
      else for (const child of current.childNodes) walk(child);
    }
    walk(root());
    return Math.min(total, sizeOf(root()));
  }
  function readSelection() {
    const current = window.getSelection();
    if (!current?.rangeCount) return selection;
    const range = current.getRangeAt(0);
    if (root().contains(range.startContainer) && root().contains(range.endContainer)) {
      selection = { start: pointOffset(range.startContainer, range.startOffset), end: pointOffset(range.endContainer, range.endOffset, true) };
    }
    return selection;
  }
  function setSelection(start, end = start) {
    const limit = composerModel.length(segments);
    start = Math.max(0, Math.min(start, limit)); end = Math.max(start, Math.min(end, limit));
    const point = target => {
      let offset = 0;
      for (const [index, child] of [...root().childNodes].entries()) {
        const size = sizeOf(child);
        if (target <= offset + size) {
          if (child.nodeType === 3) return [child, target - offset];
          return [root(), index + (target > offset ? 1 : 0)];
        }
        offset += size;
      }
      return [root(), root().childNodes.length];
    };
    const range = document.createRange();
    range.setStart(...point(start)); range.setEnd(...point(end));
    const current = window.getSelection(); current.removeAllRanges(); current.addRange(range);
    selection = { start, end };
  }
  const state = () => ({ segments: composerModel.normalize(segments), selection: { ...readSelection() } });
  function snapshot() {
    return { text: composerModel.text(segments), segments: composerModel.normalize(segments), refs: composerModel.references(segments) };
  }
  function changed() {
    if (typeof window !== 'undefined' && typeof saveConversationDraft === 'function') {
      // The public state field remains a derived view for stale-context checks.
      syncQuestionReferences(); saveConversationDraft();
    }
  }
  function syncQuestionReferences() {
    if (typeof stateForComposer === 'function') stateForComposer(snapshot().refs);
  }
  function notice(message = '', undoable = false) {
    const line = document.getElementById('chat-composer-notice');
    if (!line) return;
    line.replaceChildren(); line.hidden = !message;
    if (message) line.append(document.createTextNode(message));
    if (undoable) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-small';
      button.textContent = 'Undo'; button.addEventListener('click', () => undo(false)); line.append(button);
    }
  }
  function commit(next, nextSelection, before = state(), message = '', undoable = false) {
    const normalized = composerModel.normalize(next);
    if (JSON.stringify(normalized) === JSON.stringify(segments)) return;
    history.push(before); if (history.length > 100) history.shift(); redo = [];
    segments = normalized; render(); root().focus(); setSelection(nextSelection.start, nextSelection.end);
    notice(message, undoable); changed();
  }
  function undo(forward) {
    if (composing) return;
    const from = forward ? redo : history, to = forward ? history : redo;
    if (!from.length) return;
    to.push(state()); const previous = from.pop(); segments = previous.segments;
    render(); root().focus(); setSelection(previous.selection.start, previous.selection.end);
    notice(forward ? 'Edit redone.' : 'Edit undone.'); changed();
  }
  function positionOf(token) {
    let offset = 0;
    for (const child of root().childNodes) { if (child === token) return offset; offset += sizeOf(child); }
    return offset;
  }
  function convert(token) {
    if (composing) return;
    const ref = tokenValues.get(token), at = positionOf(token), words = `"${ref.description}"`;
    commit(composerModel.replace(segments, at, at + 1, [{ type: 'text', text: words }]),
      { start: at + 1, end: at + words.length - 1 }, state(), 'Reference converted to text. ', true);
  }
  function remove(token) {
    const at = positionOf(token);
    commit(composerModel.replace(segments, at, at + 1), { start: at, end: at }, state(), 'Reference removed.');
  }
  function tokenElement(ref) {
    const token = document.createElement('span'); token.contentEditable = 'false';
    token.className = 'chat-reference-token'; token.dataset.kind = ref.kind;
    if (typeof questionReferenceStatus === 'function') token.dataset.status = questionReferenceStatus(ref);
    tokenValues.set(token, ref);
    const current = typeof questionContextIsCurrent === 'function' && questionContextIsCurrent(ref);
    token.classList.toggle('chat-reference-stale', !current);
    const label = document.createElement('button'); label.type = 'button'; label.className = 'chat-reference-label';
    label.textContent = ref.description;
    label.setAttribute('aria-label', `${ref.kind} ${ref.id}: ${ref.description}. Click to edit as text${current ? '' : '. Earlier scenario'}.`);
    label.title = `${ref.kind} ${ref.id}: ${ref.description}. Click to edit as text.${current ? '' : ' From an earlier scenario. Refresh or remove before asking.'}`;
    label.addEventListener('click', event => { event.stopPropagation(); convert(token); });
    label.addEventListener('keydown', event => {
      if (event.key === 'Backspace' || event.key === 'Delete') { event.preventDefault(); event.stopPropagation(); remove(token); }
    });
    token.append(label);
    if (!current && typeof currentQuestionReference === 'function' && currentQuestionReference(ref.kind, ref.id)) {
      const refresh = document.createElement('button'); refresh.type = 'button'; refresh.textContent = 'Refresh';
      refresh.className = 'chat-reference-refresh'; refresh.setAttribute('aria-label', `Refresh ${ref.kind} ${ref.id} for the current scenario`);
      refresh.addEventListener('click', event => {
        event.stopPropagation();
        const updated = currentQuestionReference(ref.kind, ref.id);
        if (!updated) return;
        // Refresh identity only. Keep the authored token wording, like ordinary prose.
        const at = positionOf(token);
        commit(composerModel.replace(segments, at, at + 1, [{ type: 'reference', ref: { ...updated, description: ref.description } }]),
          { start: at + 1, end: at + 1 }, state(), 'Reference refreshed for the current scenario.');
      });
      token.append(refresh);
    }
    const detach = document.createElement('button'); detach.type = 'button'; detach.className = 'chat-reference-remove'; detach.textContent = '×';
    detach.setAttribute('aria-label', `Remove ${ref.kind} ${ref.id} from question context`);
    detach.addEventListener('click', event => { event.stopPropagation(); remove(token); }); token.append(detach);
    return token;
  }
  function render() {
    if (!root() || composing) return;
    root().replaceChildren(...segments.map(item => item.type === 'text' ? document.createTextNode(item.text) : tokenElement(item.ref)));
  }
  function readDOM() {
    const result = [];
    const walk = node => {
      if (tokenValues.has(node)) result.push({ type: 'reference', ref: tokenValues.get(node) });
      else if (node.nodeType === 3) result.push({ type: 'text', text: node.data });
      else if (node.nodeName === 'BR') result.push({ type: 'text', text: '\n' });
      else {
        if (node !== root() && ['DIV', 'P'].includes(node.nodeName) && result.length) result.push({ type: 'text', text: '\n' });
        for (const child of node.childNodes) walk(child);
      }
    };
    walk(root()); return composerModel.normalize(result);
  }
  function insertText(words) {
    const before = state(), { start, end } = before.selection;
    commit(composerModel.replace(segments, start, end, [{ type: 'text', text: words }]),
      { start: start + words.length, end: start + words.length }, before);
  }
  function deleteInput(forward, word = false) {
    const before = state(); let { start, end } = before.selection;
    if (start === end) {
      const units = segments.map(item => item.type === 'text' ? item.text : '\ufffc').join('');
      if (word) {
        if (forward) end += (/^(?:\s+|[^\s\ufffc]+|\ufffc)/u.exec(units.slice(end))?.[0].length || 0);
        else start -= (/(?:\s+|[^\s\ufffc]+|\ufffc)$/u.exec(units.slice(0, start))?.[0].length || 0);
      } else {
        const boundaries = typeof Intl.Segmenter === 'function'
          ? [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(units)].map(item => item.index)
          : [...units].reduce((list, item) => [...list, list.at(-1) + item.length], [0]);
        if (forward) end = boundaries.find(value => value > end) ?? units.length;
        else start = boundaries.filter(value => value < start).at(-1) ?? 0;
      }
    }
    const removedReference = composerModel.slice(segments, start, end).some(item => item.type === 'reference');
    commit(composerModel.replace(segments, start, end), { start, end: start }, before, removedReference ? 'Reference removed.' : '');
  }
  function init() {
    if (initialized || !root()) return;
    initialized = true;
    document.addEventListener('selectionchange', () => { if (!composing) readSelection(); });
    root().addEventListener('compositionstart', () => { compositionBefore = state(); composing = true; notice(); });
    root().addEventListener('compositionend', () => {
      const next = readDOM(); const selected = readSelection(); composing = false;
      commit(next, selected, compositionBefore); compositionBefore = null;
    });
    root().addEventListener('beforeinput', event => {
      if (event.isComposing || composing || event.inputType.includes('Composition')) return;
      pendingSelection = state();
      const type = event.inputType;
      if (type === 'insertText' && event.data !== null) { event.preventDefault(); insertText(event.data); }
      else if (type === 'insertParagraph' || type === 'insertLineBreak') { event.preventDefault(); insertText('\n'); }
      else if (['deleteContentBackward', 'deleteContentForward', 'deleteWordBackward', 'deleteWordForward'].includes(type)) {
        event.preventDefault(); deleteInput(type.endsWith('Forward'), type.includes('Word'));
      } else if (type === 'historyUndo' || type === 'historyRedo') { event.preventDefault(); undo(type === 'historyRedo'); }
      if (event.defaultPrevented) pendingSelection = null;
    });
    root().addEventListener('input', () => {
      if (composing) return;
      const selected = readSelection(); const next = readDOM();
      commit(next, selected, pendingSelection || state()); pendingSelection = null;
    });
    root().addEventListener('paste', event => {
      event.preventDefault(); if (!composing) insertText(event.clipboardData?.getData('text/plain') || '');
    });
    for (const type of ['copy', 'cut']) root().addEventListener(type, event => {
      if (composing) return;
      const { start, end } = readSelection(); if (start === end) return;
      event.preventDefault(); event.clipboardData?.setData('text/plain', composerModel.text(composerModel.slice(segments, start, end)));
      if (type === 'cut') deleteInput(false);
    });
    root().addEventListener('keydown', event => {
      if (event.isComposing || composing || event.keyCode === 229) return;
      if (event.target !== root()) return; // Token buttons own activation, never submission.
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); undo(event.shiftKey); }
      else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') { event.preventDefault(); undo(true); }
      else if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendChatMessage(); }
      else if (['ArrowLeft', 'ArrowRight'].includes(event.key) && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
        const { start, end } = readSelection(); const forward = event.key === 'ArrowRight';
        if (start === end && composerModel.slice(segments, forward ? start : start - 1, forward ? start + 1 : start).some(item => item.type === 'reference')) {
          event.preventDefault(); setSelection(start + (forward ? 1 : -1));
        }
      }
    });
  }
  function restore(value) {
    init(); composing = false; segments = composerModel.restore(value); history = []; redo = [];
    selection = { start: composerModel.length(segments), end: composerModel.length(segments) };
    render(); notice(); syncQuestionReferences();
  }
  function insertReference(ref) {
    init(); if (composing) return false;
    const refs = composerModel.references(segments), existing = refs.find(item => item.kind === ref.kind && item.id === ref.id);
    if (!existing && refs.length >= 24) { showGlobalStatus('A question can include up to 24 context items. Remove one before adding another.', 'info'); return false; }
    if (existing && !questionContextIsCurrent(existing)) {
      const next = segments.map(item => item.type === 'reference' && item.ref.kind === ref.kind && item.ref.id === ref.id
        ? { type: 'reference', ref: { ...ref, description: item.ref.description } } : item);
      commit(next, readSelection(), state(), 'Question context refreshed. Your question text is unchanged.'); return true;
    }
    const before = state(), at = before.selection.start;
    const prefix = composerModel.text(composerModel.slice(segments, 0, at));
    const suffix = composerModel.text(composerModel.slice(segments, at));
    const inserted = [{ type: 'text', text: `${prefix && !prefix.endsWith('\n\n') ? '\n\n' : ''}Can you explain ` },
      { type: 'reference', ref }, { type: 'text', text: `?${suffix && !suffix.startsWith('\n\n') ? '\n\n' : ''}` }];
    const nextAt = at + composerModel.length(inserted);
    commit(composerModel.replace(segments, at, at, inserted), { start: nextAt, end: nextAt }, before, 'Reference added.');
    return true;
  }
  function refreshPresentation() {
    if (composing || !root()) return;
    const focused = document.activeElement, active = root().contains(focused), selected = readSelection();
    const token = active ? focused.closest('.chat-reference-token') : null;
    const tokenAt = token ? positionOf(token) : null;
    const control = ['chat-reference-label', 'chat-reference-refresh', 'chat-reference-remove']
      .find(name => focused?.classList.contains(name));
    render();
    if (active) {
      root().focus(); setSelection(selected.start, selected.end);
      if (tokenAt !== null && control) {
        // Preserve this occurrence, even when another token has the same identity.
        const replacement = [...root().childNodes].find(node => tokenValues.has(node) && positionOf(node) === tokenAt);
        replacement?.querySelector(`.${control}`)?.focus();
      }
    }
  }
  function compactSignatures(text, hash) {
    const compact = items => items.map(item => item.type === 'reference' && item.ref.scenario_signature === text
      ? { ...item, ref: { ...item.ref, scenario_signature: hash } } : item);
    segments = compact(segments);
    for (const entry of [...history, ...redo]) entry.segments = compact(entry.segments);
    syncQuestionReferences();
  }
  return { init, snapshot, restore, insertReference, refreshPresentation, compactSignatures,
    insertText(text) { init(); if (!composing) insertText(String(text)); },
    get isComposing() { return composing; },
    clearIfUnchanged(value) { if (JSON.stringify(snapshot()) === JSON.stringify(value)) { restore({ text: '' }); return true; } return false; },
    restoreIfEmpty(value) { if (!composerModel.length(segments)) { restore(value); changed(); return true; } return false; },
    focus() { init(); root().focus(); setSelection(selection.start, selection.end); },
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = composerModel;
