"""Offline contracts for reference editing and exact saved-source locations."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


@pytest.fixture(scope="module")
def node():
    executable = shutil.which("node")
    if not executable:
        try:
            import playwright
        except ImportError:
            pytest.skip("Node or the Playwright Node runtime is required")
        executable = str(Path(playwright.__file__).parent / "driver" / "node")
    return executable


def javascript(node, body):
    script = (
        "const assert = require('node:assert/strict');\n"
        f"const composer = require({json.dumps(str(STATIC / 'composer.js'))});\n"
        f"const reader = require({json.dumps(str(STATIC / 'source-reader.js'))});\n"
        "const ref = (id, description='Same description') => ({type:'reference',ref:{kind:'rule',id,description,scenario_signature:'old',view_key:'example:test'}});\n"
        + body
    )
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_rewording_prose_keeps_distinct_reference_identities(node):
    javascript(node, r"""
      const original = [{type:'text',text:'Can you explain '},ref('r1'),{type:'text',text:' and '},ref('r2'),{type:'text',text:'?'}];
      const edited = composer.replace(original,0,16,[{type:'text',text:'Compare '}]);
      assert.deepEqual(composer.references(edited).map(item=>item.id),['r1','r2']);
      assert.equal(composer.text(edited),'Compare "Same description" and "Same description"?');
      const removed = composer.replace(edited,8,9);
      assert.equal(composer.text(removed),'Compare  and "Same description"?');
      assert.deepEqual(composer.references(removed).map(item=>item.id),['r2']);
    """)


def test_token_conversion_and_cross_token_replacement_do_not_rewrite_surrounding_text(node):
    javascript(node, r"""
      const original=[{type:'text',text:'Before '},ref('r1','A quoted claim'),{type:'text',text:' after'}];
      const converted=composer.replace(original,7,8,[{type:'text',text:'"A quoted claim"'}]);
      assert.equal(composer.text(converted),'Before "A quoted claim" after');
      assert.equal(composer.references(converted).length,0);
      const replaced=composer.replace(original,4,10,[{type:'text',text:'X'}]);
      assert.equal(composer.text(replaced),'BefoXfter');
      assert.equal(composer.references(replaced).length,0);
    """)


def test_legacy_migration_preserves_prose_without_matching_duplicate_descriptions(node):
    javascript(node, r"""
      const prose='Compare "Same description" with my revised wording.';
      const migrated=composer.restore({text:prose,refs:[ref('r1').ref,ref('r2').ref]});
      assert.equal(migrated[0].text,prose+'\n');
      assert.equal(composer.text(migrated),prose+'\n"Same description"\n"Same description"');
      assert.deepEqual(composer.references(migrated).map(item=>item.id),['r1','r2']);
      const again=composer.restore({text:composer.text(migrated),segments:migrated,refs:composer.references(migrated)});
      assert.deepEqual(again,migrated);
    """)


def test_old_tab_plaintext_edit_wins_over_obsolete_segments(node):
    javascript(node, r"""
      const restored=composer.restore({text:'New wording',segments:[{type:'text',text:'Obsolete wording'},ref('r1')],refs:[ref('r1').ref]});
      assert.equal(composer.text(restored),'New wording\n"Same description"');
      assert.equal(composer.references(restored)[0].id,'r1');
    """)


def test_reference_order_is_document_order_and_repeated_mentions_deduplicate(node):
    javascript(node, r"""
      const segments=[ref('r2'),{type:'text',text:' '},ref('r1'),{type:'text',text:' '},ref('r2')];
      assert.deepEqual(composer.references(segments).map(item=>item.id),['r2','r1']);
      assert.equal(composer.text(segments),'"Same description" "Same description" "Same description"');
      assert.deepEqual(composer.references(composer.slice(segments,2)),[ref('r1').ref,ref('r2').ref]);
    """)


def test_reference_metadata_does_not_store_arbitrary_browser_secrets(node):
    javascript(node, r"""
      const unsafe=ref('r1'); unsafe.ref.apiKey='must-not-save'; unsafe.ref.session={secret:'must-not-save'};
      assert.equal(JSON.stringify(composer.normalize([unsafe])).includes('must-not-save'),false);
    """)


@pytest.mark.parametrize("case", [
    "assert.deepEqual(reader.locate({filename:'x.txt',text:'😀A target Z'}, {source:'x.txt',quote:'target',start:3,end:9}),{start:4,end:10,method:'offset'});",
    "assert.deepEqual(reader.locate({filename:'x.txt',text:'target then target'}, {source:'x.txt',quote:'target',start:12,end:18}),{start:12,end:18,method:'offset'});",
    "assert.equal(reader.locate({filename:'x.txt',text:'target then target'}, {source:'x.txt',quote:'target',start:0,end:1}),null);",
    "assert.deepEqual(reader.locate({filename:'x.txt',text:'Saved layout: target.'}, {source:'x.txt',quote:'target',start:100,end:106}),{start:14,end:20,method:'unique-match'});",
    "assert.equal(reader.locate({filename:'x.txt',text:'target'}, {source:'other.txt',quote:'target',start:0,end:6}),null);",
    "assert.equal(reader.locate({filename:'x.txt',text:'Saved layout differs'}, {source:'x.txt',quote:'Saved  layout',start:0,end:13}),null);",
    "assert.equal(reader.locate({filename:'x.txt',text:'anything'}, {source:'x.txt',quote:'',start:0,end:0}),null);",
])
def test_source_locations_require_exact_saved_text_and_unambiguous_fallback(node, case):
    javascript(node, case)


def test_paragraph_keeps_source_start_and_verified_span(node):
    javascript(node, r"""
      const source={filename:'x.txt',text:'Exact quote. A qualification.\n\nLater text.'};
      const location=reader.locate(source,{source:'x.txt',quote:'Exact quote.',start:0,end:12});
      const context=reader.paragraph(source,location);
      assert.equal(context.text,'Exact quote. A qualification.');
      assert.equal(context.text.slice(context.start,context.end),'Exact quote.');
      assert.equal(reader.paragraph(source,null),null);
    """)


def test_missing_historical_snapshot_never_substitutes_current_sources(node):
    javascript(node, r"""
      global.state={bundle:{scenario:{sources:[{filename:'private.txt',text:'Current private material'}]}}};
      assert.deepEqual(reader.sources(undefined),[]);
      assert.deepEqual(reader.sources({scenario:{scenario:{sources:[{filename:'old.txt',text:'Historical material'}]}}}),[{filename:'old.txt',text:'Historical material'}]);
    """)
