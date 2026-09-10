/* Saved source text is data. A confirmed location is not proof of a claim. */
const sourceReaderData = (() => {
  function locate(source, evidence) {
    if (!source || typeof source.text !== 'string' || !evidence || source.filename !== evidence.source
        || typeof evidence.quote !== 'string' || !evidence.quote) return null;
    const points = Array.from(source.text);
    const { start, end } = evidence;
    if (Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end >= start && end <= points.length
        && points.slice(start, end).join('') === evidence.quote) {
      return { start: points.slice(0, start).join('').length, end: points.slice(0, end).join('').length, method: 'offset' };
    }
    const found = source.text.indexOf(evidence.quote);
    if (found >= 0 && source.text.indexOf(evidence.quote, found + 1) < 0) {
      return { start: found, end: found + evidence.quote.length, method: 'unique-match' };
    }
    return null;
  }
  function paragraph(source, location) {
    if (!location) return null;
    const text = source.text;
    const previous = text.lastIndexOf('\n\n', location.start);
    const start = Math.min(location.start, Math.max(previous < 0 ? 0 : previous + 2, location.start - 500, 0));
    const boundary = text.indexOf('\n\n', location.end);
    const end = Math.min(boundary < 0 ? text.length : boundary, location.end + 500);
    return { text: text.slice(start, end), start: location.start - start, end: location.end - start,
      clippedStart: start > 0, clippedEnd: end < text.length };
  }
  const sources = snapshot => {
    const values = snapshot?.scenario?.scenario?.sources;
    return Array.isArray(values) ? values.filter(item => item && typeof item.filename === 'string' && typeof item.text === 'string') : [];
  };
  return { locate, paragraph, sources };
})();

const sourceReader = (() => {
  let generation = 0, value = null, activeSource = '', query = '', matchIndex = 0;
  const noDocuments = 'No reference documents attached. You can ask about this scenario\'s statements, rules, and computed labels.';
  const node = id => document.getElementById(id);
  function markedText(container, text, range, className = '') {
    container.replaceChildren();
    if (!range) { container.textContent = text; return; }
    container.append(document.createTextNode(text.slice(0, range.start)));
    const mark = document.createElement('mark'); mark.className = className; mark.textContent = text.slice(range.start, range.end);
    container.append(mark, document.createTextNode(text.slice(range.end)));
  }
  function clear() {
    generation++; value = null; activeSource = ''; query = ''; matchIndex = 0;
    if (node('modal-sources-reader')?.classList.contains('visible')) closeModal('modal-sources-reader');
    for (const id of ['source-reader-documents', 'source-reader-text', 'source-reader-glossary', 'source-reader-excerpt']) node(id)?.replaceChildren();
    for (const id of ['source-reader-state', 'source-reader-position', 'source-reader-metadata']) if (node(id)) node(id).textContent = '';
    if (node('sources-reader-title')) node('sources-reader-title').textContent = 'Sources and glossary';
    if (node('source-reader-edit')) { node('source-reader-edit').onclick = null; node('source-reader-edit').hidden = true; }
    if (node('source-reader-edit-scenario')) { node('source-reader-edit-scenario').onclick = null; node('source-reader-edit-scenario').hidden = true; }
    if (node('source-reader-search')) node('source-reader-search').value = '';
  }
  async function open(options = {}) {
    const request = ++generation, owner = conversationStore.owner;
    let snapshot = options.snapshot || null;
    const supplied = Array.isArray(options.sources);
    if (!snapshot && !supplied && options.historical !== true) {
      const context = captureModelViewContext();
      if (!context.bundle) return;
      try { snapshot = await captureConversationSnapshot(context); }
      catch (error) { if (request === generation && owner === conversationStore.owner) showGlobalStatus(`Sources could not be opened: ${error.message}`, 'error'); return; }
      if (!modelViewContextIsCurrent(context)) return;
    }
    if (request !== generation || owner !== conversationStore.owner) return;
    const scenario = snapshot?.scenario?.scenario || {};
    value = { sources: structuredClone(supplied ? options.sources : sourceReaderData.sources(snapshot)),
      scenario: structuredClone(scenario), evidence: options.evidence || null,
      historical: options.historical === true || Boolean(options.snapshot),
      title: options.title || scenario.title || 'Reference documents', onEditSource: options.onEditSource || null };
    activeSource = options.selectedSource || value.evidence?.source || value.sources[0]?.filename || '';
    query = ''; matchIndex = 0; node('source-reader-search').value = '';
    node('sources-reader-title').textContent = `Sources and glossary: ${value.title}`;
    node('source-reader-state').textContent = value.historical ? 'Saved scenario at the time of this answer.' : 'Reference documents describe context; they do not add facts or rules to the argumentation engine.';
    const projectId = !value.historical && !supplied && state.viewKind === 'project' ? state.activeProject?.id : null;
    const editScenario = node('source-reader-edit-scenario');
    editScenario.hidden = !projectId || state.readOnly || typeof openPrivateScenarioEditor !== 'function';
    editScenario.onclick = () => {
      if (request !== generation || owner !== conversationStore.owner || state.activeProject?.id !== projectId || state.readOnly) return;
      closeModal('modal-sources-reader'); openPrivateScenarioEditor();
    };
    renderDocuments(); renderGlossary(); renderText(); showTab('sources');
    openModal('modal-sources-reader', value.sources.length ? '#source-reader-search' : '#source-reader-glossary-tab');
  }
  function renderDocuments() {
    const list = node('source-reader-documents'); list.replaceChildren();
    if (!value.sources.length) { const empty = document.createElement('p'); empty.textContent = noDocuments; list.append(empty); }
    for (const source of value.sources) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'source-reader-document';
      button.setAttribute('aria-pressed', String(source.filename === activeSource));
      const name = document.createElement('span'); name.textContent = source.filename;
      const size = document.createElement('small'); size.textContent = `${new TextEncoder().encode(source.text || '').length.toLocaleString()} bytes of text`;
      button.append(name, size); button.addEventListener('click', () => {
        activeSource = source.filename; matchIndex = 0; renderDocuments(); renderText();
        list.querySelector('[aria-pressed="true"]')?.focus();
      }); list.append(button);
    }
  }
  function renderText() {
    if (!value) return;
    const source = value.sources.find(item => item.filename === activeSource);
    const evidence = value.evidence?.source === activeSource ? value.evidence : null;
    const location = sourceReaderData.locate(source, evidence);
    const text = source?.text || '';
    const matches = [];
    if (query) {
      const pattern = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'giu');
      for (const match of text.matchAll(pattern)) {
        matches.push({ start: match.index, end: match.index + match[0].length });
        if (matches.length >= 10000) break;
      }
    }
    matchIndex = matches.length ? ((matchIndex % matches.length) + matches.length) % matches.length : 0;
    const searchRange = matches[matchIndex] || null;
    node('source-reader-position').textContent = query ? (matches.length ? `Search match ${matchIndex + 1} of ${matches.length}` : 'No search matches')
      : evidence ? (location ? 'Confirmed location of the supplied excerpt.' : 'Location in the saved document could not be confirmed.') : '';
    node('source-reader-previous').disabled = !matches.length; node('source-reader-next').disabled = !matches.length;
    node('source-reader-search').disabled = !source;
    markedText(node('source-reader-text'), text, query ? searchRange : location, query ? 'source-search-match' : 'source-citation-match');
    const excerpt = node('source-reader-excerpt'); excerpt.replaceChildren(); excerpt.hidden = !evidence || Boolean(location);
    if (evidence && !location) { const title = document.createElement('p'); title.textContent = 'Supplied excerpt'; const quote = document.createElement('blockquote'); quote.textContent = evidence.quote; excerpt.append(title, quote); }
    const metadata = node('source-reader-metadata'); metadata.textContent = source?.url ? `Source URL (provided metadata): ${source.url}` : '';
    const edit = node('source-reader-edit'); edit.hidden = !value.onEditSource || !source;
    edit.onclick = () => { if (!source || !value?.onEditSource) return; const callback = value.onEditSource; closeModal('modal-sources-reader'); callback(structuredClone(source)); };
    requestAnimationFrame(() => node('source-reader-text')?.querySelector('mark')?.scrollIntoView({ block: 'center' }));
  }
  function renderGlossary() {
    const container = node('source-reader-glossary'); container.replaceChildren();
    const table = document.createElement('table'); table.className = 'source-reader-glossary';
    const caption = document.createElement('caption'); caption.textContent = 'Meanings in this scenario'; table.append(caption);
    const head = document.createElement('thead'), header = document.createElement('tr');
    for (const text of ['Symbol', 'Meaning', 'Negated meaning']) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = text; header.append(th); }
    head.append(header); table.append(head); const body = document.createElement('tbody'), seen = new Set();
    for (const section of ['facts', 'assumptions', 'propositions', 'conclusions', 'rules']) for (const [id, entry] of Object.entries(value.scenario[section] || {})) {
      if (seen.has(id)) continue; seen.add(id);
      const row = document.createElement('tr');
      for (const text of [id, entry.description || literalInScenario(id, value.scenario), entry.negated_description || literalInScenario(`-${id}`, value.scenario)]) {
        const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
      }
      body.append(row);
    }
    table.append(body); container.append(table);
    if (!seen.size) { const empty = document.createElement('p'); empty.textContent = 'No glossary entries in this view.'; container.append(empty); }
  }
  function showTab(tab) {
    node('source-reader-sources').hidden = tab !== 'sources'; node('source-reader-glossary').hidden = tab !== 'glossary';
    for (const name of ['sources', 'glossary']) node(`source-reader-${name}-tab`).setAttribute('aria-pressed', String(name === tab));
  }
  function init() {
    if (!node('modal-sources-reader')) return;
    for (const name of ['sources', 'glossary']) node(`source-reader-${name}-tab`).addEventListener('click', () => showTab(name));
    node('source-reader-search').addEventListener('input', event => { query = event.target.value; matchIndex = 0; renderText(); });
    node('source-reader-next').addEventListener('click', () => { matchIndex++; renderText(); });
    node('source-reader-previous').addEventListener('click', () => { matchIndex--; renderText(); });
  }
  return { open, clear, init, markedText, noDocuments };
})();

async function openSourcesReader(options = {}) { return sourceReader.open(options); }
if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', sourceReader.init);
if (typeof module !== 'undefined' && module.exports) module.exports = sourceReaderData;
