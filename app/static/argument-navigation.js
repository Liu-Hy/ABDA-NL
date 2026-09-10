/* Explain, derivation and graph views share one captured scenario bundle. */
let argumentNavigation = null;
let graphContext = null;

function newArgumentNavigation(bundle, historical = false) {
  return { bundle, historical, owner: state.authSession.user?.id || null,
    scope: resetScope(), graph: null, game: null };
}

function argumentContextIsCurrent(context) {
  return context && context.owner === (state.authSession.user?.id || null)
    && (context.historical || (context.bundle === state.bundle && context.scope === resetScope()));
}

function clearArgumentViews() {
  for (const id of ['modal-game', 'modal-derivation', 'modal-af']) closeModal(id);
  argumentNavigation = null; graphContext = null; inspectorState = null;
  gameBundle = null; gameNodes = {}; gameRootId = null; gameFocusId = null;
  for (const id of ['game-modal-body', 'derivation-body', 'af-modal-body']) document.getElementById(id)?.replaceChildren();
}

function validateArgumentViews() {
  if ((argumentNavigation && !argumentContextIsCurrent(argumentNavigation))
      || (graphContext && !argumentContextIsCurrent(graphContext))) {
    const visible = ['modal-game', 'modal-derivation', 'modal-af'].some(id => document.getElementById(id)?.classList.contains('visible'));
    clearArgumentViews();
    if (visible) showGlobalStatus('The scenario changed. Open an explanation again for the updated state.', 'info');
  }
}

function inspectGraphConclusion(literal) {
  if (!argumentContextIsCurrent(graphContext)) { validateArgumentViews(); return; }
  const scroll = document.getElementById('af-svg-scroll');
  const navigation = newArgumentNavigation(graphContext.bundle);
  navigation.graph = { literal, zoom: afZoom, scope: afScope, isolated: afShowIsolated,
    left: scroll?.scrollLeft || 0, top: scroll?.scrollTop || 0 };
  closeModal('modal-af');
  openElementInspector('conclusion', literal, graphContext.bundle, false, navigation);
}

function returnToConclusionGraph() {
  const navigation = argumentNavigation;
  if (!navigation?.graph || !argumentContextIsCurrent(navigation)) { validateArgumentViews(); return; }
  closeModal('modal-game'); closeModal('modal-derivation');
  const saved = navigation.graph;
  afScope = saved.scope; afShowIsolated = saved.isolated;
  openModal('modal-af', '.modal-close');
  afZoom = saved.zoom; applyAFZoom();
  const scroll = document.getElementById('af-svg-scroll');
  const target = [...document.querySelectorAll('.af-node')].find(node => node.dataset.afLit === saved.literal);
  target?.focus({ preventScroll: true });
  if (scroll) { scroll.scrollLeft = saved.left; scroll.scrollTop = saved.top; }
}

function argumentNavigationMarkup(view, argId) {
  if (!argumentNavigation) return '';
  return `<nav class="argument-view-nav" aria-label="Argument views">
    ${argumentNavigation.graph ? '<button type="button" class="btn btn-small" data-argument-view="graph">Back to conclusion graph</button>' : ''}
    <button type="button" class="btn btn-small" data-argument-view="game" aria-current="${view === 'game' ? 'page' : 'false'}" ${view === 'game' || !argId ? 'disabled' : ''}>Explain</button>
    <button type="button" class="btn btn-small" data-argument-view="derivation" aria-current="${view === 'derivation' ? 'page' : 'false'}" ${view === 'derivation' || !argId ? 'disabled' : ''}>Derivation</button>
    ${argumentNavigation.historical ? '<span class="derivation-note">Saved scenario</span>' : ''}
  </nav>`;
}

function bindArgumentNavigation(body, view, argId) {
  body.querySelectorAll('[data-argument-view]').forEach(button => button.addEventListener('click', () => {
    const navigation = argumentNavigation;
    if (!argumentContextIsCurrent(navigation)) { validateArgumentViews(); return; }
    const next = button.dataset.argumentView;
    if (next === 'graph') { returnToConclusionGraph(); return; }
    const argument = navigation.bundle.af.arguments.find(item => item.id === argId);
    if (!argument) return;
    if (next === 'derivation') {
      navigation.game = { nodes: gameNodes, counter: gameNodeCounter, root: gameRootId, focus: gameFocusId,
        conclusion: gameConclusionId, explanationOnly: gameExplanationOnly, argId };
      closeModal('modal-game');
      openDerivationInspector(argId, navigation.bundle, navigation.historical, navigation);
    } else {
      closeModal('modal-derivation');
      if (navigation.game?.argId === argId) {
        const saved = navigation.game;
        gameBundle = navigation.bundle; gameNodes = saved.nodes; gameNodeCounter = saved.counter;
        gameRootId = saved.root; gameFocusId = saved.focus; gameConclusionId = saved.conclusion;
        gameExplanationOnly = saved.explanationOnly;
        renderGame(); openModal('modal-game', '.modal-close');
      } else openExplainModal(argument.conclusion, navigation.bundle, navigation.historical, argId, navigation);
    }
  }));
}

function derivationDescription(argument, bundle) {
  const byId = new Map(bundle.af.arguments.map(item => [item.id, item]));
  return (argument.premises || []).map(id => {
    const premise = byId.get(id);
    return premise ? `${premise.conclusion_nl} [${premise.top_rule}; ${id}]` : id;
  }).join('; ');
}
