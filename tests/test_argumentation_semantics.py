"""Focused semantic checks for the deterministic argumentation engine."""
from __future__ import annotations

import pytest

from app.abda_bridge import (
    Argument,
    ArgumentationGraph,
    Attack,
    StrictRule,
    init_engine,
)
from GroundedDiscussionGame.Game import Game
from GroundedDiscussionGame.Moves.CB import CB
from GroundedDiscussionGame.Moves.CONCEDE import CONCEDE
from GroundedDiscussionGame.Moves.HTB import HTB
from GroundedDiscussionGame.Moves.RETRACT import RETRACT


@pytest.fixture(scope="module", autouse=True)
def _engine_configuration() -> None:
    init_engine()


def _argument(conclusion: str) -> Argument:
    return Argument(StrictRule([], conclusion))


def test_grounded_labelling_reaches_fixed_point_and_leaves_cycle_undecided():
    source = _argument("source")
    challenged = _argument("challenged")
    restored = _argument("restored")
    isolated = _argument("isolated")
    loop_left = _argument("loop_left")
    loop_right = _argument("loop_right")

    attacks = {
        Attack(source, challenged),
        Attack(challenged, restored),
        Attack(loop_left, loop_right),
        Attack(loop_right, loop_left),
    }
    graph = ArgumentationGraph(
        {source, challenged, restored, isolated, loop_left, loop_right},
        attacks,
    )

    labels = graph.get_grounded_labelling()

    assert labels[source] == "in"
    assert labels[challenged] == "out"
    assert labels[restored] == "in"
    assert labels[isolated] == "in"
    assert labels[loop_left] == "undec"
    assert labels[loop_right] == "undec"


def test_min_max_numbering_uses_max_for_in_and_min_for_out_arguments():
    source = _argument("source")
    first_out = _argument("first_out")
    middle_in = _argument("middle_in")
    later_out = _argument("later_out")
    joined_in = _argument("joined_in")
    short_out = _argument("short_out")
    loop_left = _argument("loop_left")
    loop_right = _argument("loop_right")

    attacks = {
        Attack(source, first_out),
        Attack(first_out, middle_in),
        Attack(middle_in, later_out),
        Attack(first_out, joined_in),
        Attack(later_out, joined_in),
        Attack(source, short_out),
        Attack(middle_in, short_out),
        Attack(loop_left, loop_right),
        Attack(loop_right, loop_left),
    }
    graph = ArgumentationGraph(
        {
            source,
            first_out,
            middle_in,
            later_out,
            joined_in,
            short_out,
            loop_left,
            loop_right,
        },
        attacks,
    )
    labels = graph.get_grounded_labelling()
    numbering = graph.get_min_max(labels)

    assert numbering[source] == 1
    assert numbering[first_out] == 2
    assert numbering[middle_in] == 3
    assert numbering[later_out] == 4
    assert numbering[joined_in] == 5
    assert numbering[short_out] == 2
    assert loop_left not in numbering
    assert loop_right not in numbering


def test_discussion_game_accepts_a_claim_after_its_challenge_is_retracted():
    claim = _argument("claim")
    challenge = _argument("challenge")
    defense = _argument("defense")
    attacks = {
        Attack(challenge, claim),
        Attack(defense, challenge),
    }
    graph = ArgumentationGraph({claim, challenge, defense}, attacks)
    labels = graph.get_grounded_labelling()
    numbering = graph.get_min_max(labels)
    game = Game(graph, claim, labels, numbering)

    assert game.do_move(HTB(game, claim))
    assert game.do_move(CB(game, challenge))
    assert game.do_move(HTB(game, defense))
    assert game.do_move(CONCEDE(game, defense))
    assert game.do_move(RETRACT(game, challenge))
    assert game.do_move(CONCEDE(game, claim))

    assert not game.EnabledMoves
    assert game.get_outcome() == f"Proponent has won: {claim} has been conceded."
