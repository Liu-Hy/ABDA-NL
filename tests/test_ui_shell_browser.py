"""Explorer navigation and visual acceptance, using real assets and engine states."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re

import pytest

from app.scenario.diff_ops import apply as apply_diff
from app.scenario.loader import load_scenario, scenario_from_dict
from app.scenario.state import compute_state_bundle
from tests.test_exploration_browser import explorer_browser as _explorer_browser


pytestmark = pytest.mark.skipif(os.getenv("ABDA_BROWSER_TESTS") != "1", reason="browser acceptance is opt-in")
explorer_browser = _explorer_browser


def _set_bundle(page, bundle):
    page.evaluate("""bundle => {
      state.diff_ops = []; state.baseline = bundle.scenario;
      setBundle(bundle); indexBundle(); renderAll();
    }""", bundle)


def test_scenario_menu_keyboard_focus_does_not_load_until_activation(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    page.evaluate("""() => {
      state.scenarios.push({id: 'other', title: 'Other example'}); renderScenarioChoices();
      window.scenarioSelections = [];
      requestScenarioLoad = id => window.scenarioSelections.push(id);
    }""")
    page.locator('#scenario-menu-btn').click()
    expect(page.locator('[data-scenario-key="example:test"]')).to_be_focused()
    page.keyboard.press('ArrowDown')
    expect(page.locator('[data-scenario-key="example:other"]')).to_be_focused()
    assert page.evaluate('window.scenarioSelections') == []
    page.keyboard.press('Enter')
    assert page.evaluate('window.scenarioSelections') == ['other']
    expect(page.locator('#scenario-popover')).to_be_hidden()
    page.locator('#scenario-menu-btn').click()
    page.keyboard.press('o')
    expect(page.locator('[data-scenario-key="example:other"]')).to_be_focused()
    page.keyboard.press('Escape')
    expect(page.locator('#scenario-menu-btn')).to_be_focused()
    assert runtime['chat_requests'] == []


@pytest.mark.parametrize('width', [1440, 390])
def test_about_starts_closed_and_resets_on_scenario_and_project_switch(explorer_browser, width):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    page.set_viewport_size({'width': width, 'height': 900})
    about = page.locator('#scenario-about')
    button = page.locator('#scenario-about-btn')
    expect(about).to_be_hidden()
    expect(button).to_have_attribute('aria-expanded', 'false')

    # An old persisted preference cannot reopen the background on a fresh load.
    page.evaluate("localStorage.setItem('abda.about-collapsed', '0')")
    page.reload()
    expect(page.locator('#scenario-name')).to_have_text(runtime['bundle']['scenario']['title'])
    expect(about).to_be_hidden()
    button.focus()
    page.keyboard.press('Space')
    expect(about).to_be_visible()
    expect(button).to_be_focused()
    expect(button).to_have_attribute('aria-expanded', 'true')
    page.evaluate('() => renderAll()')
    expect(about).to_be_visible()
    page.keyboard.press('Enter')
    expect(about).to_be_hidden()
    expect(button).to_be_focused()
    button.click()

    runtime['bundle'] = deepcopy(runtime['bundle'])
    runtime['bundle']['scenario']['title'] = 'Another example'
    runtime['bundle']['scenario']['description'] = 'Background for another example.'
    page.evaluate("""() => {
      state.scenarios.push({id: 'other', title: 'Another example'});
      renderScenarioChoices();
    }""")
    page.locator('#scenario-menu-btn').click()
    page.locator('[data-scenario-key="example:other"]').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#scenario-name')).to_have_text('Another example')
    expect(about).to_be_hidden()
    expect(button).to_have_attribute('aria-expanded', 'false')
    expect(page.locator('#scenario-menu-btn')).to_be_focused()
    button.click()

    project = {'id': 'about-project', 'name': 'Private background', 'version': 1,
               'source_scenario_id': 'other', **deepcopy(runtime['bundle'])}
    page.route('**/api/projects/about-project', lambda route: route.fulfill(
        content_type='application/json', body=json.dumps(project)))
    page.evaluate("() => loadProject('about-project')")
    expect(page.locator('#context-indicator')).to_have_text('Private project')
    expect(about).to_be_hidden()
    button.click()
    page.evaluate("() => {state.activeProject.version += 1; renderShellControls();}")
    expect(about).to_be_visible()
    about.focus()
    page.evaluate("() => loadScenario('test')")
    expect(page.locator('#context-indicator')).to_have_text('Example')
    expect(about).to_be_hidden()
    expect(button).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    assert runtime['chat_requests'] == []


def test_reset_keeps_conversation_and_draft_with_a_version_bound_undo(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    baseline = scenario_from_dict(runtime['bundle']['scenario'])

    def respond(route):
        data = route.request.post_data_json
        result = compute_state_bundle(apply_diff(baseline, data['diff_ops']))
        route.fulfill(content_type='application/json', body=json.dumps(result))

    page.route('**/state', respond)
    page.locator('#chat-input').fill('Keep this conversation')
    page.locator('#chat-send-btn').click()
    expect(page.locator('.chat-msg-assistant:not(.chat-msg-loading)')).to_have_count(1)
    page.locator('#chat-input').fill('An unfinished next question')
    conversation = page.evaluate('conversationStore.activeId')
    page.evaluate("() => applyOp({op: 'toggle-assumption', id: 'a'})")
    expect(page.locator('#reset-btn')).to_be_visible()
    page.locator('#reset-btn').click()
    expect(page.locator('#reset-undo-btn')).to_be_visible()
    expect(page.locator('#reset-btn')).to_be_hidden()
    expect(page.locator('#chat-input')).to_contain_text('An unfinished next question')
    assert page.evaluate('conversationStore.activeId') == conversation
    assert page.evaluate('state.chatMessages.length') == 2
    page.locator('#reset-undo-btn').click()
    expect(page.locator('#reset-btn')).to_be_visible()
    assert page.evaluate('state.bundle.scenario.assumptions.a.active') is False
    page.locator('#reset-btn').click()
    expect(page.locator('#reset-undo-btn')).to_be_visible()
    page.evaluate("() => {state.activeProject={id: 'another-project', version: 2}; renderShellControls();}")
    expect(page.locator('#reset-undo-btn')).to_be_hidden()
    count = len(runtime['chat_requests'])
    page.evaluate('() => resetToBaseline()')
    assert len(runtime['chat_requests']) == count


def test_graph_drills_into_exact_literal_and_restores_view_and_focus(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    page.locator('#view-af-btn').click()
    page.locator('[data-af-scope="all"]').focus()
    page.keyboard.press('Enter')
    expect(page.locator('[data-af-scope="all"]')).to_be_focused()
    expect(page.locator('#af-show-isolated')).to_be_visible()
    expect(page.locator('.af-node[data-af-lit="p1"]')).to_have_count(0)
    page.locator('#af-show-isolated').check()
    expect(page.locator('.af-node[data-af-lit="p1"]')).to_have_count(1)
    page.locator('[data-af-zoom="reset"]').click()
    node = page.locator('.af-node[data-af-lit="c"]')
    node.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#modal-af')).to_be_hidden()
    expect(page.locator('#modal-derivation')).to_be_visible()
    expect(page.locator('#derivation-argument-select option')).to_have_count(2)
    assert page.evaluate('inspectorState.scope.id') == 'c'
    assert page.locator('.modal-backdrop.visible').count() == 1
    page.locator('#modal-derivation [data-argument-view="game"]').click()
    expect(page.locator('#modal-game')).to_be_visible()
    assert page.evaluate('gameNodes[gameRootId].argId') in [a['id'] for a in runtime['bundle']['af']['arguments'] if a['conclusion'] == 'c']
    page.locator('#modal-game [data-argument-view="derivation"]').click()
    expect(page.locator('#modal-game')).to_be_hidden()
    page.locator('#modal-derivation [data-argument-view="graph"]').click()
    expect(node).to_be_focused()
    expect(page.locator('#af-show-isolated')).to_be_checked()
    expect(page.locator('#af-zoom-readout')).to_have_text('100%')
    assert runtime['chat_requests'] == []


def test_game_keyboard_focus_survives_argument_moves_and_collapse(explorer_browser, tmp_path):
    from playwright.sync_api import expect
    page, _ = explorer_browser
    page.locator('[data-explain-id="c"]').click()
    picker = page.locator('.game-picker-card').first
    picker.focus()
    page.keyboard.press('Enter')
    expect(page.locator('.game-node-active')).to_be_focused()
    move = page.locator('#game-moves [data-move]').first
    expect(move).to_be_visible()
    move.focus()
    page.keyboard.press('Enter')
    expect(page.locator('.game-node-active')).to_be_focused()
    collapse = page.locator('[data-toggle-collapse-id]').first
    collapse.focus()
    collapse.hover()
    from axe_playwright_python.sync_playwright import Axe
    report = Axe().run(page, options={'runOnly': {'type': 'tag', 'values': ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}})
    assert report.violations_count == 0, report.generate_report()
    directory = Path(os.getenv('ABDA_BROWSER_ARTIFACT_DIR', str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(directory / f"{os.getenv('ABDA_BROWSER_ENGINE', 'chromium')}-expanded-game.png"), full_page=True)
    page.keyboard.press('Enter')
    expect(collapse).to_be_focused()
    expect(collapse).to_have_attribute('aria-expanded', 'false')
    page.locator('#game-back-btn').focus()
    page.keyboard.press('Enter')
    expect(page.locator('.game-picker-card').first).to_be_focused()


def test_saved_derivation_game_uses_saved_bundle_and_clears_on_account_change(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    saved = deepcopy(runtime['bundle'])
    candidate = next(a for a in saved['af']['arguments'] if a['conclusion'] == 'c')
    page.evaluate("""payload => {
      state.bundle = structuredClone(state.bundle);
      state.bundle.scenario.rules = {};
      state.bundle.af.arguments = [];
      openDerivationInspector(payload.arg, payload.bundle, true);
    }""", {'arg': candidate['id'], 'bundle': saved})
    page.locator('[data-argument-view="game"]').click()
    expect(page.locator('#game-modal-body')).to_contain_text('The claim holds')
    expect(page.locator('#game-modal-body')).to_contain_text('Saved scenario')
    assert page.evaluate('gameBundle.af.arguments.length') == len(saved['af']['arguments'])
    page.evaluate("() => {state.authSession.user = {id: 'different-person'}; renderAll();}")
    expect(page.locator('#modal-game')).to_be_hidden()
    assert page.evaluate('gameBundle') is None
    assert page.locator('#game-modal-body').inner_text() == ''


def test_one_root_starts_directly_and_absent_conclusion_stays_inspectable(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    scenario = deepcopy(runtime['bundle']['scenario'])
    scenario['rules'].pop('r2')
    scenario['rules'].pop('objection')
    scenario['conclusions']['missing'] = {'description': 'An unsupported conclusion'}
    _set_bundle(page, compute_state_bundle(scenario_from_dict(scenario)))
    page.locator('[data-explain-id="c"]').click()
    expect(page.locator('.game-picker-card')).to_have_count(0)
    assert page.evaluate('gameNodes[gameRootId].resolution') == 'conceded'
    expect(page.locator('[data-resolve]')).to_have_count(0)
    page.keyboard.press('Escape')
    page.locator('[data-inspect-conclusion="missing"]').click()
    expect(page.locator('#derivation-body')).to_contain_text('No matching derivation')
    expect(page.locator('#modal-derivation [data-argument-view="game"]')).to_be_disabled()


def test_strict_rule_immunity_is_not_described_as_a_preference(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    scenario = {
        'title': 'Strict derivation with a contrary argument',
        'facts': {'p': {'description': 'Premise P'}, 'q': {'description': 'Premise Q'}},
        'conclusions': {'c': {'description': 'Claim C', 'negated_description': 'Not C'}},
        'rules': {
            'strict_c': {'type': 'strict', 'premises': ['p'], 'conclusion': 'c'},
            'defeasible_not_c': {'type': 'defeasible', 'premises': ['q'], 'conclusion': '-c'},
        },
    }
    bundle = compute_state_bundle(scenario_from_dict(scenario))
    support = next(arg for arg in bundle['af']['arguments'] if arg['conclusion'] == 'c')
    contrary = next(arg for arg in bundle['af']['arguments'] if arg['conclusion'] == '-c')
    assert support['label'] == 'in' and contrary['label'] == 'out'
    assert {rule['block'] for rule in bundle['scenario']['rules'].values()} == {1}
    assert {(edge['from'], edge['to']) for edge in bundle['af']['attacks']} == {
        (support['id'], contrary['id']),
    }
    _set_bundle(page, bundle)
    page.locator('[data-explain-id="c"]').click()
    body = page.locator('#game-modal-body')
    expect(body).to_contain_text('No challenges remain.')
    # The contrary derivation is disclosed without inferring why its edge is absent.
    expect(body).to_contain_text('defeasible_not_c')
    expect(body).not_to_contain_text(re.compile('rule preference|preference rules out', re.I))
    assert runtime['chat_requests'] == []


def test_kind_and_state_filters_are_independent_and_inspection_reveals_hidden_item(explorer_browser):
    from playwright.sync_api import expect
    page, runtime = explorer_browser
    scenario = deepcopy(runtime['bundle']['scenario'])
    scenario['assumptions']['a']['active'] = False
    scenario['rules']['top']['active'] = False
    _set_bundle(page, compute_state_bundle(scenario_from_dict(scenario)))
    page.locator('[data-filter="assumptions"]').click()
    page.locator('#facts-suspended').check()
    expect(page.locator('#facts-list [data-element-id="a"]')).to_be_visible()
    page.locator('[data-filter="facts"]').click()
    expect(page.locator('#facts-list .fact-card')).to_have_count(0)
    expect(page.locator('#facts-suspended')).to_be_checked()
    page.locator('#rules-suspended').check()
    expect(page.locator('#kb-content .rule-card')).to_have_count(1)
    page.evaluate("() => openElementInspector('rule', 'r1')")
    page.locator('[data-locate-kind="rule"][data-locate-id="r1"]').first.click()
    expect(page.locator('#rules-suspended')).not_to_be_checked()
    expect(page.locator('#kb-content [data-element-id="r1"]')).to_be_focused()


@pytest.mark.parametrize('width,height', [(1440, 900), (1280, 800), (1152, 768), (1024, 768), (780, 900), (720, 450), (390, 844)])
def test_readable_layout_has_no_horizontal_overflow_and_records_screenshot(explorer_browser, width, height, tmp_path):
    from playwright.sync_api import expect
    page, _ = explorer_browser
    bundle = compute_state_bundle(load_scenario(Path('examples/popov_v_hayashi/scenario.yaml')))
    _set_bundle(page, bundle)
    page.set_viewport_size({'width': width, 'height': height})
    # WebKit may paint the old media-query layout during the first resize frame.
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    if width <= 780:
        expect(page.locator('#left-panel')).to_have_css('min-width', '0px')
    directory = Path(os.getenv('ABDA_BROWSER_ARTIFACT_DIR', str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(directory / f'explorer-{width}.png'), full_page=True)
    expect(page.locator('.conclusion-card').first).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), page.evaluate("""() =>
      [...document.querySelectorAll('body *')].filter(el => el.getClientRects().length && el.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 16).map(el => ({id: el.id, cls: el.className, width: el.getBoundingClientRect().width}))
    """)
    expected_font = '14px' if width <= 780 else '13px'
    assert page.locator('.conclusion-label').first.evaluate('el => getComputedStyle(el).fontSize') == expected_font
    assert page.locator('.conclusion-label').first.evaluate('el => el.scrollWidth <= el.clientWidth + 1')
    if width <= 780:
        card = page.locator('.conclusion-card').first
        assert card.locator('.conclusion-actions').bounding_box()['y'] >= card.locator('.conclusion-label').bounding_box()['y']
    for selector in ['#scenario-menu-btn', '#workspace-btn', '#save-btn', '.rule-info', '[data-inspect-conclusion]']:
        rect = page.locator(selector).first.bounding_box()
        assert rect and rect['height'] >= 24 and rect['width'] >= 24, selector
    if width >= 1280:
        assert page.locator('#conclusions-panel').bounding_box()['width'] >= 420
    if width in (1280, 720):
        from axe_playwright_python.sync_playwright import Axe
        if width == 720:
            page.locator('#scenario-about-btn').click()
            page.locator('#scenario-about').focus()
            expect(page.locator('#scenario-about')).to_be_focused()
        report = Axe().run(page, options={'runOnly': {'type': 'tag', 'values': ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}})
        assert report.violations_count == 0, report.generate_report()
        if width == 1280 and os.getenv('ABDA_BROWSER_ENGINE', 'chromium') == 'chromium':
            cdp = page.context.new_cdp_session(page)
            for deficiency in ('protanopia', 'deuteranopia', 'tritanopia'):
                cdp.send('Emulation.setEmulatedVisionDeficiency', {'type': deficiency})
                page.screenshot(path=str(directory / f'explorer-{deficiency}.png'), full_page=True)
            cdp.send('Emulation.setEmulatedVisionDeficiency', {'type': 'none'})
            cdp.detach()
        page.locator('#view-af-btn').click()
        report = Axe().run(page, options={'runOnly': {'type': 'tag', 'values': ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']}})
        assert report.violations_count == 0, report.generate_report()
        page.screenshot(path=str(directory / f'conclusion-graph-{width}.png'), full_page=True)


def test_global_error_is_dismissible_and_does_not_overlap_header(explorer_browser):
    from playwright.sync_api import expect
    page, _ = explorer_browser
    page.evaluate("() => showGlobalStatus('A recoverable test error', 'error')")
    expect(page.locator('#global-status')).to_contain_text('A recoverable test error')
    top = page.locator('.topbar').bounding_box()
    status = page.locator('#global-status').bounding_box()
    assert status['y'] >= top['y'] + top['height'] - 1
    page.locator('#global-status').get_by_role('button', name=re.compile('Dismiss')).click()
    expect(page.locator('#global-status')).to_be_hidden()
