"""
What lives for one turn, and a window whose start moves only between turns.

A user message starts a turn. A message with ``lifetime="turn"`` (the gateway's
notice) sits where it arrived until then and is never stored; a reply's
``reasoning`` is shown during its turn and left out of earlier turns, by copy.
With ``trim_to_fraction`` the window's first message moves only when a turn
starts, so within a turn every request only appends.
"""

import tempfile
from pathlib import Path

import pytest

from pyllments.elements import HistoryHandlerElement, PipeElement
from pyllments.elements.history_handler.history_handler_model import HistoryHandlerModel
from pyllments.elements.history_handler.history_store import SQLiteHistoryStore
from pyllments.payloads import MessagePayload


def _model(**params) -> HistoryHandlerModel:
    defaults = {"context_token_limit": 8000, "summary_token_threshold": 0,
                "projection_tiers": {0: {}}, "tokenizer_model": "gpt-4o"}
    return HistoryHandlerModel(**{**defaults, **params})


def _contents(model: HistoryHandlerModel) -> list[str]:
    return [payload.model.content for payload in model.get_context_payloads()]


def _say(role: str, content: str, **params) -> MessagePayload:
    return MessagePayload(role=role, content=content, **params)


def _notice(content: str) -> MessagePayload:
    return _say("system", content, lifetime="turn")


def test_a_turn_message_stays_in_place_until_the_next_user_message():
    model = _model()
    model.load_entries([_say("user", "q1"), _notice("notice 1")])
    model.load_entries([_say("assistant", "calling"), _notice("notice 2")])

    assert _contents(model) == ["q1", "notice 1", "calling", "notice 2"]

    model.load_entries([_say("user", "q2")])
    assert _contents(model) == ["q1", "calling", "q2"]
    assert model.history_token_count == sum(entry.raw_token_count for entry in model.history)


@pytest.mark.asyncio
async def test_a_turn_message_is_never_stored():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteHistoryStore(db_path=str(Path(tmp) / "turn.db"))
        model = _model(persist=True, history_store=store)
        await model.await_store_ready()
        model.load_entries([_say("user", "q1"), _notice("notice")])
        model.load_entries([_say("assistant", "a1"), _say("user", "q2")])
        await model.flush_store()

        stored = [record.payload_data["content"] for record in await store.load_records()]
        assert stored == ["q1", "a1", "q2"]


@pytest.mark.asyncio
async def test_a_notice_through_the_ingest_door_emits_nothing():
    history = HistoryHandlerElement(
        context_token_limit=8000, summary_token_threshold=0,
        projection_tiers={0: {}}, tokenizer_model="gpt-4o",
    )
    notices = PipeElement(name="notices")
    seen = PipeElement(name="seen")
    notices.ports.pipe_output > history.ports.payload_input
    history.ports.context_output > seen.ports.pipe_input

    await notices.async_send_payload(_notice("Round 1."))

    assert seen.received_payloads == []
    assert _contents(history.model) == ["Round 1."]


def test_reasoning_is_shown_in_its_turn_and_left_out_of_earlier_ones():
    reasoning = {"provider": "anthropic", "content": [{"type": "thinking", "signature": "s"}]}
    reply = _say("assistant", "a1", reasoning=reasoning)
    model = _model()
    model.load_entries([_say("user", "q1"), reply])

    assert model.get_context_payloads()[1] is reply

    model.load_entries([_say("user", "q2")])
    shown = model.get_context_payloads()[1]
    assert shown is not reply
    assert (shown.model.content, shown.model.reasoning, shown.finished) == ("a1", None, True)
    # The ledger's own record is finished and never changes.
    assert reply.model.reasoning == reasoning


def _turns(model: HistoryHandlerModel, count: int, start: int = 0) -> None:
    for index in range(start, start + count):
        model.load_entries([_say("user", f"question {index} " + "word " * 40)])
        model.load_entries([_say("assistant", f"answer {index} " + "word " * 40)])


def _first(model: HistoryHandlerModel) -> str:
    return model.get_context_payloads()[0].model.content.split(" word")[0]


def test_the_window_start_holds_and_moves_at_a_turn_start():
    probe = _model()
    _turns(probe, 1)
    per_turn = probe.history_token_count
    # Six turns fit with a little room (two-digit turns are a token longer); seven do not.
    model = _model(context_token_limit=per_turn * 6 + 20, trim_to_fraction=0.55)

    firsts = []
    for index in range(11):
        _turns(model, 1, start=index)
        firsts.append(_first(model))

    # The start holds while the turns fit; an overflowing turn cuts back to three, at a question.
    assert firsts[:6] == ["question 0"] * 6
    assert firsts[6:10] == ["question 4"] * 4
    assert firsts[10] == "question 8"


def test_a_turn_that_outgrows_the_window_keeps_growing_until_it_ends():
    model = _model(context_token_limit=200, trim_to_fraction=0.5)
    model.load_entries([_say("user", "q0 " + "word " * 60)])
    model.load_entries([_say("assistant", "a0 " + "word " * 60)])
    model.load_entries([_say("user", "q1 " + "word " * 20)])
    model.load_entries([_say("assistant", "a1 " + "word " * 120)])

    # Mid-turn: over the limit, nothing trimmed, so the turn's requests only append.
    assert _first(model) == "q0"

    model.load_entries([_say("user", "q2 " + "word " * 10)])
    assert _first(model) in ("q1", "q2")
    assert model.get_context_payloads()[0].model.role == "user"


def test_without_trim_to_fraction_the_window_slides_every_turn():
    probe = _model()
    _turns(probe, 1)
    per_turn = probe.history_token_count
    model = _model(context_token_limit=per_turn * 6 + 20)

    firsts = []
    for index in range(9):
        _turns(model, 1, start=index)
        firsts.append(_first(model))

    assert firsts[6:] == ["question 1", "question 2", "question 3"]


def test_a_trimmed_window_opens_on_a_user_message():
    model = _model(context_token_limit=300, trim_to_fraction=0.5)
    model.load_entries([_say("user", "q0 " + "word " * 60)])
    model.load_entries([_say("assistant", "a0 " + "word " * 60)])
    model.load_entries([_say("assistant", "a0 again " + "word " * 30)])
    model.load_entries([_say("assistant", "a0 more " + "word " * 120)])
    model.load_entries([_say("user", "q1 " + "word " * 20)])

    context = model.get_context_payloads()
    assert context[0].model.role == "user"
