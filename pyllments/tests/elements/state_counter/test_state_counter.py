import asyncio

import pytest

from pyllments.elements import StateCounterElement
from pyllments.elements.pipe import PipeElement
from pyllments.payloads import MessagePayload, StructuredPayload
from pyllments.runtime.lifecycle_manager import LifecycleManager, manager as lifecycle_manager
from pyllments.runtime.loop_registry import LoopRegistry


@pytest.fixture
def loop():
    return LoopRegistry.get_loop()


@pytest.fixture(autouse=True)
def cleanup_output_ports(loop):
    yield
    loop.run_until_complete(lifecycle_manager.shutdown())
    LifecycleManager.reset_for_tests()


def _send_and_drain(sender: PipeElement, counter: StateCounterElement, payload, loop):
    sender.send_payload(payload)
    loop.run_until_complete(sender.ports.output["pipe_output"].drain())
    loop.run_until_complete(counter.drain())


class TestStateCounterLogic:
    def test_reset_and_count(self):
        counter = StateCounterElement(
            initial_count=0,
            limit=3,
            reset_predicate=lambda _p, _s: True,
            count_predicate=lambda _p, _s: True,
        )
        counter.handle_reset(MessagePayload(content="reset", role="user"))
        state = counter.handle_count(MessagePayload(content="count", role="assistant"))
        assert state is not None
        assert state["count"] == 1
        assert state["remaining"] == 2
        assert state["exhausted"] is False

    def test_limit_exhausted(self):
        counter = StateCounterElement(
            initial_count=0,
            limit=2,
            reset_predicate=lambda _p, _s: True,
            count_predicate=lambda _p, _s: True,
        )
        counter.handle_reset(MessagePayload(content="reset", role="user"))
        counter.handle_count(MessagePayload(content="count", role="assistant"))
        state = counter.handle_count(MessagePayload(content="count", role="assistant"))
        assert state is not None
        assert state["count"] == 2
        assert state["remaining"] == 0
        assert state["exhausted"] is True

    def test_ignored_when_predicate_false(self):
        counter = StateCounterElement(initial_count=5)
        payload = MessagePayload(content="ignored", role="user")
        assert counter.handle_reset(payload) is None
        assert counter.handle_count(payload) is None
        assert counter.build_state()["count"] == 5


class TestStateCounterElement:
    def test_ports_exposed(self):
        counter = StateCounterElement()
        assert "reset_emit_input" in counter.ports.input
        assert "count_emit_input" in counter.ports.input
        assert "state_output" in counter.ports.output

    def test_message_predicates_emit_state(self, loop):
        received = []

        def capture(payload):
            received.append(payload.model.data)

        output_pipe = PipeElement(receive_callback=capture)

        counter = StateCounterElement(
            limit=3,
            reset_predicate=lambda p, _s: getattr(getattr(p, "model", None), "role", None) == "user",
            count_predicate=lambda p, _s: getattr(getattr(p, "model", None), "role", None) == "assistant",
        )

        reset_pipe = PipeElement(name="reset_pipe")
        count_pipe = PipeElement(name="count_pipe")

        reset_pipe.ports.pipe_output > counter.ports.input["reset_emit_input"]
        count_pipe.ports.pipe_output > counter.ports.input["count_emit_input"]
        counter.ports.output["state_output"] > output_pipe.ports.input["pipe_input"]

        _send_and_drain(
            reset_pipe,
            counter,
            MessagePayload(content="hi", role="user"),
            loop,
        )
        assert len(received) == 1
        assert received[-1]["count"] == 0
        assert received[-1]["last_event"] == "reset"

        _send_and_drain(
            count_pipe,
            counter,
            MessagePayload(content="tool call", role="assistant"),
            loop,
        )
        assert received[-1]["count"] == 1
        assert received[-1]["remaining"] == 2

    def test_ignored_payload_does_not_emit(self, loop):
        received = []
        output_pipe = PipeElement(receive_callback=lambda p: received.append(p))

        counter = StateCounterElement(
            count_predicate=lambda _p, _s: False,
            reset_predicate=lambda _p, _s: False,
        )
        sender = PipeElement()
        sender.ports.pipe_output > counter.ports.input["count_emit_input"]
        counter.ports.output["state_output"] > output_pipe.ports.input["pipe_input"]

        _send_and_drain(
            sender,
            counter,
            MessagePayload(content="ignored", role="user"),
            loop,
        )
        assert received == []

    def test_on_exhausted_fires_once_until_reset(self, loop):
        exhausted_calls = []

        counter = StateCounterElement(
            limit=2,
            reset_predicate=lambda p, _s: p.model.data.get("reset", False),
            count_predicate=lambda _p, _s: True,
            on_exhausted=lambda state: exhausted_calls.append(dict(state)),
        )

        reset_pipe = PipeElement()
        count_pipe = PipeElement()
        reset_pipe.ports.pipe_output > counter.ports.input["reset_emit_input"]
        count_pipe.ports.pipe_output > counter.ports.input["count_emit_input"]

        _send_and_drain(reset_pipe, counter, StructuredPayload(data={"reset": True}), loop)

        _send_and_drain(count_pipe, counter, MessagePayload(content="a"), loop)
        _send_and_drain(count_pipe, counter, MessagePayload(content="b"), loop)
        _send_and_drain(count_pipe, counter, MessagePayload(content="c"), loop)

        assert len(exhausted_calls) == 1
        assert exhausted_calls[0]["exhausted"] is True
        assert exhausted_calls[0]["remaining"] == 0

        _send_and_drain(reset_pipe, counter, StructuredPayload(data={"reset": True}), loop)
        _send_and_drain(count_pipe, counter, MessagePayload(content="d"), loop)
        _send_and_drain(count_pipe, counter, MessagePayload(content="e"), loop)

        assert len(exhausted_calls) == 2

    def test_on_exhausted_async(self, loop):
        exhausted_calls = []

        async def on_exhausted(state):
            await asyncio.sleep(0)
            exhausted_calls.append(state["exhausted"])

        counter = StateCounterElement(
            limit=1,
            reset_predicate=lambda _p, _s: True,
            count_predicate=lambda _p, _s: True,
            on_exhausted=on_exhausted,
        )

        reset_pipe = PipeElement()
        count_pipe = PipeElement()
        reset_pipe.ports.pipe_output > counter.ports.input["reset_emit_input"]
        count_pipe.ports.pipe_output > counter.ports.input["count_emit_input"]

        _send_and_drain(reset_pipe, counter, StructuredPayload(data={"reset": True}), loop)
        _send_and_drain(count_pipe, counter, MessagePayload(content="x"), loop)
        assert exhausted_calls == [True]

    def test_lazy_import(self):
        from pyllments.elements import StateCounterElement as ImportedCounter

        assert ImportedCounter is StateCounterElement
