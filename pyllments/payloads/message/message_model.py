import asyncio
import inspect
import time
from typing import AsyncIterator

from loguru import logger
import param

from pyllments.base.model_base import Model
from pyllments.runtime.loop_registry import LoopRegistry
from pyllments.payloads.message.stream_events import MessageStreamEvent
from pyllments.payloads.message.usage import normalize_usage
# from pyllments.common.tokenizers import get_token_len


class MessageModel(Model):
    """
    Model representing a message. Handles both atomic and streaming scenarios.
    In streaming mode, use :meth:`aiter_events` to consume provider chunks as events.
    In atomic mode, a stored coroutine is awaited to populate message content.
    """
    role = param.Selector(
        default='user',
        objects=['system', 'assistant', 'user', 'function', 'tool', 'developer'],
        instantiate=True,
        doc="Message role - matches OpenAI/LiteLLM format"
    )

    content = param.String(default='', doc="Message content")

    mode = param.Selector(
        objects=['atomic', 'stream'],
        default='atomic',
        instantiate=True,
        doc="Determines whether the message is captured atomically or via streaming"
    )

    message_coroutine = param.Parameter(
        default=None,
        doc="Used with stream mode for assistant messages or atomic mode when a coroutine needs to be awaited"
    )

    streamed = param.Boolean(default=False, doc="Indicates whether the message has been fully streamed")

    ready = param.Boolean(default=False, doc="Indicates if the message is fully processed and ready for use")

    cancelled = param.Boolean(default=False, doc="Indicates the stream was cancelled before completion")

    aggregate_stream = param.Boolean(
        default=True,
        doc="When True, aiter_events updates content and tool_calls on the model during streaming"
    )

    embedding = param.Parameter(doc="Message embedding if generated")

    timestamp = param.Number(default=None, doc="Unix timestamp when the message was created")

    loop = param.Parameter(default=None, doc="Asyncio event loop associated with this message model")

    tool_calls = param.List(default=[], item_type=dict, doc="List of tool calls from the model")

    tool_call_id = param.String(
        default=None,
        allow_None=True,
        doc="For role 'tool': the id of the assistant tool call this message answers",
    )

    tool_name = param.String(
        default=None,
        allow_None=True,
        doc="For role 'tool': the name of the tool that produced the content",
    )

    usage = param.Dict(
        default=None,
        allow_None=True,
        doc=(
            "Token usage of this reply, set by the backend as it finishes: input_tokens "
            "(the whole prompt), cached_input_tokens, cache_write_tokens, output_tokens. "
            "None when the provider reported none."
        ),
    )

    reasoning = param.Dict(
        default=None,
        allow_None=True,
        doc=(
            "The model's reasoning for this reply, in its provider's own opaque form, "
            "set by the backend as the reply finishes: {'provider': 'anthropic', "
            "'content': [...]} (the reply's thinking, text and tool_use blocks in order, "
            "since Anthropic's signatures depend on position) or {'provider': 'openai', "
            "'items': [...]} (its output items, reasoning encrypted). Only that provider's "
            "backend sends it back. It lives for the turn: the history shows earlier "
            "turns without it. content and tool_calls stay the form everything else reads."
        ),
    )

    lifetime = param.Selector(
        objects=["durable", "turn"],
        default="durable",
        doc=(
            "How long the model should see this message. 'durable' is history. 'turn' "
            "lasts until the next user message starts a new turn, such as the gateway's "
            "notice: it stays in place while the turn runs, so each request only appends, "
            "and is never stored."
        ),
    )

    request_check = param.Dict(
        default=None,
        allow_None=True,
        doc=(
            "Set by LLMChatElement on the reply it requested: whether that request only "
            "appended to the previous one, which every provider's prompt cache needs. "
            "{'first_request', 'appended', 'changed_at' (first message index that differs, "
            "or None), 'same_turn', 'settings_changed' (model, tools or request options)}."
        ),
    )

    strict_params = True

    def __init__(self, **params):
        super().__init__(**params)
        if params.get('loop', None) is None:
            params['loop'] = LoopRegistry.get_loop()
        self.loop = params.get('loop', LoopRegistry.get_loop())
        self.timestamp = time.time() if not self.timestamp else self.timestamp

        self._stream_task = None
        self._active_stream_source = None
        self._stream_lock = None

    async def _resolve_stream_source(self):
        """Normalize message_coroutine to an async iterator."""
        if self.message_coroutine is None:
            raise ValueError("Cannot stream: Message coroutine is not set")

        stream_source = self.message_coroutine
        if inspect.isawaitable(stream_source) and not hasattr(stream_source, '__aiter__'):
            stream_source = await stream_source
            self.message_coroutine = stream_source
        if not hasattr(stream_source, '__aiter__'):
            raise TypeError(
                "Stream messages require an async iterator or an awaitable that "
                f"resolves to one, got {type(stream_source).__name__}"
            )
        self._active_stream_source = stream_source
        return stream_source

    async def _close_stream_source(self):
        """Close the active provider stream to stop token generation."""
        stream_source = self._active_stream_source
        self._active_stream_source = None
        if stream_source is None:
            return
        aclose = getattr(stream_source, 'aclose', None)
        if aclose is None:
            return
        try:
            await aclose()
        except Exception as exc:
            logger.debug(f"Stream close raised {type(exc).__name__}: {exc}")

    def _apply_tool_call_delta(self, tc_delta) -> dict:
        """Accumulate a tool-call delta and return a snapshot for event emission."""
        index = getattr(tc_delta, 'index', None)
        delta_id = getattr(tc_delta, 'id', None)
        if index is None:
            # A provider that sends whole calls per chunk carries no index:
            # continue the call with the same id, otherwise start a new one.
            index = next(
                (i for i, tc in enumerate(self.tool_calls) if delta_id and tc['id'] == delta_id),
                len(self.tool_calls),
            )
        while index >= len(self.tool_calls):
            self.tool_calls.append({
                'id': '',
                'type': 'function',
                'function': {'name': '', 'arguments': ''},
            })
        current_id = self.tool_calls[index]['id']
        if delta_id and delta_id != current_id:
            # OpenAI sends the id once; some providers repeat it on every delta.
            self.tool_calls[index]['id'] = delta_id if not current_id else current_id + delta_id
        if tc_delta.type:
            self.tool_calls[index]['type'] = tc_delta.type
        if tc_delta.function:
            if tc_delta.function.name:
                self.tool_calls[index]['function']['name'] += tc_delta.function.name
            if tc_delta.function.arguments:
                self.tool_calls[index]['function']['arguments'] += tc_delta.function.arguments
        return {
            'index': index,
            'id': tc_delta.id,
            'type': tc_delta.type,
            'function': {
                'name': getattr(tc_delta.function, 'name', None) if tc_delta.function else None,
                'arguments': getattr(tc_delta.function, 'arguments', None) if tc_delta.function else None,
            },
        }

    @property
    def cache_share(self) -> float | None:
        """Share of the prompt read from the provider's cache, or None without usage."""
        usage = self.usage or {}
        total = usage.get('input_tokens') or 0
        return (usage.get('cached_input_tokens') or 0) / total if total else None

    def _take_reply_extras(self, source) -> None:
        """Keep the usage and provider record a backend attached to a chunk or response."""
        usage = normalize_usage(getattr(source, 'usage', None))
        if usage is not None:
            self.usage = usage
        reasoning = getattr(source, 'reasoning', None)
        dump = getattr(reasoning, 'model_dump', None)
        reasoning = dump() if callable(dump) else reasoning
        # Only a backend's provider record; a provider's own 'reasoning' text is not one.
        if isinstance(reasoning, dict) and reasoning.get('provider'):
            self.reasoning = reasoning

    def _flush_content_buffer(self, buffer: str) -> str:
        """Apply buffered token text to model content when aggregating."""
        if buffer and self.aggregate_stream:
            self.content += buffer
        return ''

    async def aiter_events(self) -> AsyncIterator[MessageStreamEvent]:
        """
        Yield provider-neutral stream events for tokens, tool deltas, and completion.

        When ``aggregate_stream`` is True, ``content`` and ``tool_calls`` are updated
        on this model as chunks arrive (same behavior as :meth:`stream`).
        """
        if self.mode != 'stream':
            raise ValueError("Cannot iterate events: Mode is not set to 'stream'")

        if self.cancelled:
            yield MessageStreamEvent(type='cancelled')
            return

        if self.streamed:
            yield MessageStreamEvent(
                type='done',
                tool_calls=list(self.tool_calls) if self.tool_calls else None,
            )
            return

        if self._stream_lock is None:
            self._stream_lock = asyncio.Lock()

        async with self._stream_lock:
            if self.streamed or self.cancelled:
                if self.cancelled:
                    yield MessageStreamEvent(type='cancelled')
                else:
                    yield MessageStreamEvent(
                        type='done',
                        tool_calls=list(self.tool_calls) if self.tool_calls else None,
                    )
                return

            if self.aggregate_stream:
                self.content = ''
                self.tool_calls = []

            buffer = ''
            try:
                stream_source = await self._resolve_stream_source()
                async for chunk in stream_source:
                    if self.cancelled:
                        yield MessageStreamEvent(type='cancelled')
                        break

                    self._take_reply_extras(chunk)
                    choices = getattr(chunk, 'choices', None)
                    if not choices:
                        # A closing chunk may carry only usage or the provider record.
                        continue
                    delta = choices[0].delta
                    if delta.content:
                        buffer += delta.content
                        yield MessageStreamEvent(
                            type='token',
                            content_delta=delta.content,
                            raw=chunk,
                        )
                        if self.aggregate_stream and (len(buffer) >= 10 or '\n' in buffer):
                            buffer = self._flush_content_buffer(buffer)

                    for tc_delta in delta.tool_calls or []:
                        tool_delta = self._apply_tool_call_delta(tc_delta)
                        yield MessageStreamEvent(
                            type='tool_call_delta',
                            tool_call_delta=tool_delta,
                            raw=chunk,
                        )

                if not self.cancelled:
                    buffer = self._flush_content_buffer(buffer)
                    if self.tool_calls:
                        yield MessageStreamEvent(
                            type='tool_calls_complete',
                            tool_calls=[dict(tc) for tc in self.tool_calls],
                        )
                    logger.debug("Completed message stream")
                    self.streamed = True
                    self.ready = True
                    yield MessageStreamEvent(
                        type='done',
                        tool_calls=list(self.tool_calls) if self.tool_calls else None,
                    )
                else:
                    buffer = self._flush_content_buffer(buffer)
                    self.ready = True
            except asyncio.CancelledError:
                self.cancelled = True
                self.ready = True
                yield MessageStreamEvent(type='cancelled')
                raise
            except Exception as exc:
                self.ready = True
                yield MessageStreamEvent(type='error', error=str(exc), raw=exc)
                raise
            finally:
                await self._close_stream_source()
                if (streamed_watchers := self.param.watchers.get('streamed')) is not None:
                    for watcher in streamed_watchers['value']:
                        self.param.unwatch(watcher)

    async def aiter_tokens(self) -> AsyncIterator[str]:
        """Yield content token deltas from the message stream."""
        async for event in self.aiter_events():
            if event.type == 'token' and event.content_delta:
                yield event.content_delta

    async def stream(self):
        """
        Consume the full stream and aggregate content on this model.

        Delegates to :meth:`aiter_events` with aggregation enabled.
        """
        original_aggregate = self.aggregate_stream
        self.aggregate_stream = True
        try:
            async for _event in self.aiter_events():
                pass
        finally:
            self.aggregate_stream = original_aggregate

    def cancel(self):
        """
        Cancel in-flight streaming and close the provider iterator when possible.

        Stops further token consumption so upstream providers can tear down.
        """
        if self.cancelled:
            return
        self.cancelled = True
        self.ready = True

        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()

        stream_source = self._active_stream_source
        if stream_source is not None:
            loop = self.loop or LoopRegistry.get_loop()
            aclose = getattr(stream_source, 'aclose', None)
            if aclose is not None:
                try:
                    running_loop = asyncio.get_running_loop()
                except RuntimeError:
                    running_loop = None
                if running_loop is loop:
                    loop.create_task(self._close_stream_source())
                else:
                    asyncio.run_coroutine_threadsafe(self._close_stream_source(), loop)

    async def aget_message(self) -> str:
        """
        Asynchronously retrieves the complete message content.
        If streaming is required and not yet complete or if this is an atomic response with a coroutine,
        the corresponding process is initiated and awaited.

        Returns
        -------
        str
            The complete message content.
        """
        if self.mode == 'atomic':
            if self.message_coroutine is not None:
                response = await self.message_coroutine
                self._take_reply_extras(response)
                message = response.choices[0].message
                self.content = message.content or ''
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    self.tool_calls = [
                        tc.model_dump() if hasattr(tc, 'model_dump') else dict(tc)
                        for tc in message.tool_calls
                    ]
                self.message_coroutine = None
                self.ready = True
            return self.content
        elif self.mode == 'stream':
            if not self.streamed and not self.cancelled:
                if self._stream_task is None:
                    self._stream_task = asyncio.create_task(self.stream())
                await self._stream_task
                self.ready = True
            return self.content
        else:
            raise ValueError(f"Unsupported mode: {self.mode}")

    async def await_ready(self):
        """
        Passively await until the message is fully processed without starting consumption.
        Returns the model instance for chaining.
        """
        if self.ready or self.cancelled:
            return self

        if self.mode == 'atomic' and self.message_coroutine is not None:
            future = self.loop.create_future()

            def on_resolved(event):
                if event.new is None:
                    future.set_result(self)
                    self.param.unwatch(watcher)

            watcher = self.param.watch(on_resolved, 'message_coroutine')
            await future
        elif self.mode == 'stream' and not self.streamed:
            future = self.loop.create_future()
            watchers = []

            def on_terminal(_event):
                if self.ready or self.cancelled:
                    if not future.done():
                        future.set_result(self)
                    for w in watchers:
                        self.param.unwatch(w)

            watchers.append(self.param.watch(on_terminal, 'ready'))
            watchers.append(self.param.watch(on_terminal, 'cancelled'))
            await future
        return self
