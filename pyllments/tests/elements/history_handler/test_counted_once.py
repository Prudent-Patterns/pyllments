"""
A history entry is counted when it enters the ledger, not on every emit.

Building the context projects each entry by its tier. An entry its tier leaves
unchanged reuses the count it arrived with; only a changed projection is
counted again.
"""

from pyllments.elements.history_handler import history_handler_model
from pyllments.elements.history_handler.history_handler_model import HistoryHandlerModel
from pyllments.payloads import MessagePayload


def _counting(monkeypatch) -> list:
    calls = []
    real = history_handler_model.payload_token_count

    def count(payload, tokenizer_model):
        calls.append(payload)
        return real(payload, tokenizer_model)

    monkeypatch.setattr(history_handler_model, "payload_token_count", count)
    return calls


def _messages(n: int) -> list[MessagePayload]:
    return [
        MessagePayload(role="user" if i % 2 == 0 else "assistant", content=f"message number {i}")
        for i in range(n)
    ]


def test_unchanged_entries_are_not_counted_again(monkeypatch):
    model = HistoryHandlerModel(context_token_limit=8000, projection_tiers={0: {}}, trim_to_fraction=0.5)
    calls = _counting(monkeypatch)
    model.load_entries(_messages(20))
    assert len(calls) == 20  # once each, on arrival

    calls.clear()
    model.get_context_payloads()
    model.get_context_payloads()
    assert calls == []


def test_a_changed_projection_is_counted(monkeypatch):
    def shorten(payload, context):
        return MessagePayload(role=payload.model.role, content=payload.model.content[:7])

    model = HistoryHandlerModel(context_token_limit=8000, projection_tiers={0: {MessagePayload: shorten}})
    calls = _counting(monkeypatch)
    model.load_entries(_messages(3))
    calls.clear()

    contents = [payload.model.content for payload in model.get_context_payloads()]

    assert contents == ["message"] * 3
    assert [payload.model.content for payload in calls] == ["message"] * 3
