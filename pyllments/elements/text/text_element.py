from typing import Optional

import panel as pn
import param

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.payloads.message import MessagePayload
from .text_model import TextModel


class TextElement(Element):
    """Element providing a multi-line text input *and* a static markdown view.

    It is useful for single-turn prompts or notes where the user wants to keep
    the entered text visible while still emitting a `MessagePayload` into a
    flow.

    Ports
    -----
    input:
        - message_input       : MessagePayload   (display only)
        - message_emit_input  : MessagePayload   (display + re-emit)
    output:
        - message_output      : MessagePayload
    """

    text_input_view   = param.ClassSelector(class_=pn.layout.Row, is_instance=True)
    # View that displays the current text in a read-only form.  We render a
    # ``MessagePayload`` but the container is generic enough to show other
    # payload types in the future.
    display_view     = param.ClassSelector(class_=pn.layout.Column,        is_instance=True)
    send_button_view  = param.ClassSelector(class_=pn.widgets.Button,        is_instance=True)

    sent = param.Boolean(default=False, doc="Whether the text input is marked as sent.")

    # Whether the text input should be cleared after the Send button is pressed.
    clear_after_send = param.Boolean(default=False, doc="Clear textarea after emit if True.")

    # Track watcher tied to the text input so we can detach it when payload changes
    _input_content_watcher = None

    def __init__(self, **params):
        super().__init__(**params)
        self.model = TextModel(**params)

        # Set up ports individually for clarity
        self._message_output_setup()
        self._message_input_setup()
        self._message_emit_input_setup()

        # Flag used to distinguish programmatic text updates from user input
        self._internal_update: bool = False

    # ------------------------------------------------------------------
    # Port definitions (one helper per port for readability)
    # ------------------------------------------------------------------

    def _message_output_setup(self):
        """Output port that emits the user's text as a MessagePayload."""

        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload

        self.ports.add_output("message_output", pack_payload_callback=pack)

    def _message_input_setup(self):
        """Input port that only displays an incoming MessagePayload."""

        async def unpack_display(payload: MessagePayload):
            # Store and load the incoming payload (no re-emit)
            await self.model.handle_payload(payload)

        self.ports.add_input("message_input", unpack_payload_callback=unpack_display)

    def _message_emit_input_setup(self):
        """Input port that displays and then re-emits the MessagePayload."""

        async def unpack_emit(payload: MessagePayload):
            # Display the incoming payload, then forward it downstream.
            await self.model.handle_payload(payload)
            await self.ports.output["message_output"].stage_emit(payload=payload)

        self.ports.add_input("message_emit_input", unpack_payload_callback=unpack_emit)

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    @Component.view
    def create_text_input_view(
        self,
        placeholder: str = "Type here…",
        text_area_input_css: list[str] = [],
        status_mark_css: list[str] = [],
    ) -> pn.layout.Row:
        # Create the editable chat textarea which supports the Enter-to-send behaviour
        text_area_input = pn.chat.ChatAreaInput(
            placeholder=placeholder,
            auto_grow=True,
            sizing_mode="stretch_both",
            stylesheets=text_area_input_css,
        )

        # Create the status mark (✓ shown once content is sent)
        status_mark = pn.pane.Markdown("", stylesheets=status_mark_css)

        # sync back to model and reset sent marker
        def _on_input(event):
            """Synchronise model text and sent flag based on live user input.

            ChatAreaInput emits a second ``value_input`` event with an empty
            string right after a submission (because the frontend clears the
            textarea).  When that happens *and* the message has already been
            marked as sent, we want to IGNORE the empty-string event **and**
            restore the content so it remains visible, while keeping the sent
            flag and ✓ intact.
            """

            if self._internal_update:
                return  # ignore programmatic updates

            new_text = event.new or ""

            if self.sent and new_text.strip() == "":
                # Browser auto-cleared after submission; restore text
                self._internal_update = True          # <- guard OUR watchers only
                event.obj.value        = self.model.text
                event.obj.value_input  = self.model.text
                self._internal_update = False
                return

            # Regular user typing before sending
            self.model.text = new_text
            if self.sent:
                # Any *non-empty* user edit marks message as not sent
                self.sent = False
        text_area_input.param.watch(_on_input, "value_input")

        # Watch for Enter submissions (ChatAreaInput fires 'value' when the user presses Enter)
        text_area_input.param.watch(self._on_send, 'value')

        # Watch `sent` to toggle ✓ and CSS locally to this view
        def _update_sent(event):
            sent_state = event.new
            text_area_input.css_classes = ["sent"] if sent_state else []
            status_mark.object = "✓" if sent_state else ""
            status_mark.css_classes = ["sent"] if sent_state else []

        self.param.watch(_update_sent, "sent")

        # --------------------------------------------------------------
        # Watch for payload changes to preload & stream into textarea
        # --------------------------------------------------------------

        def _on_payload_change(event):
            payload = event.new
            if not isinstance(payload, MessagePayload):
                return

            # Load initial content
            self._internal_update = True
            try:
                text_area_input.value = payload.model.content
                text_area_input.value_input = payload.model.content
                self.model.text = payload.model.content
            finally:
                self._internal_update = False

            # Detach previous watcher on content
            if self._input_content_watcher is not None:
                try:
                    event.old.model.param.unwatch(self._input_content_watcher)
                except Exception:
                    pass

            # Sync as content streams
            def _on_content(event2):
                new_txt = event2.new or ""
                self._internal_update = True
                try:
                    text_area_input.value = new_txt
                    text_area_input.value_input = new_txt
                    self.model.text = new_txt
                finally:
                    self._internal_update = False

            self._input_content_watcher = payload.model.param.watch(_on_content, 'content')

        # Attach payload watcher once
        self.model.param.watch(_on_payload_change, 'payload')

        # Return a Row containing the textarea and the status mark
        self.text_input_view = pn.Row(
            text_area_input,
            status_mark
        )
        return self.text_input_view

    @Component.view
    def create_display_view(
        self,
        title: Optional[str] = None,
        title_css: list[str] = [],
        payload: Optional[MessagePayload] = None,
        **kwargs,
    ) -> pn.Column:
        """Return a Column that shows the text as a **MessagePayload**.

        Parameters
        ----------
        title : str, optional
            Optional title rendered above the message (e.g. "Output").
        title_css : list[str]
            Extra CSS stylesheets for the title pane.
        payload : MessagePayload, optional
            The payload to render. If None, the current model text is used.
        **kwargs
            Forwarded to :py:meth:`MessagePayload.create_static_view`.
        """

        # Ensure *payload* is a MessagePayload instance
        if not isinstance(payload, MessagePayload):
            if not isinstance(self.model.payload, MessagePayload):
                self.model.payload = MessagePayload(
                    role="assistant",  # role hidden by default; irrelevant here
                    content=self.model.text,
                    mode="atomic",
                )
            payload = self.model.payload

        payload_row = payload.create_static_view(show_role=False, **kwargs)

        if self.display_view is None:
            # Build column with optional title and the payload row as last item
            children = []
            if title:
                children.append(pn.pane.Str(title, stylesheets=title_css))
            children.append(payload_row)
            self.display_view = pn.Column(*children)

            # Reactive watcher defined *inside* the view scope
            def _on_payload_change(event):
                new_pl = event.new
                if not isinstance(new_pl, MessagePayload):
                    return
                new_row = new_pl.create_static_view(show_role=False)
                # Replace the last child (current payload row)
                self.display_view[-1] = new_row

            self.model.param.watch(_on_payload_change, 'payload')
        else:
            # Replace last child (payload row)
            self.display_view[-1] = payload_row

        return self.display_view

    @Component.view
    def create_send_button_view(self, icon: str = "arrow-up", label: str = "Send"):
        self.send_button_view = pn.widgets.Button(name=label, icon=icon, icon_size="1.2em")
        btn = self.send_button_view
        text_widget = self.text_input_view[0]
        btn.on_click(lambda *_: text_widget.param.trigger('value'))
        return self.send_button_view

    @Component.view
    def create_input_view(self, title: Optional[str] = None, title_css: list[str] = []):
        input_col = pn.Column(self.create_text_input_view(),
            pn.Spacer(height=5),
            self.create_send_button_view(height=30))
        if title:
            title_str = pn.pane.Str(
                title,
                stylesheets=title_css
            )
            input_col.insert(0, title_str)
        return input_col

    @Component.view
    def create_interface_view(
        self,
        input_title: Optional[str] = None,
        display_title: Optional[str] = None,
        **kwargs,
    ):
        """Column with input row on top and markdown view below."""
        # Backwards-compat: accept old keyword ``message_title``
        display_ttl = kwargs.pop("message_title", display_title)

        return pn.Column(
            self.create_input_view(title=input_title),
            pn.Spacer(height=6),
            self.create_display_view(title=display_ttl)
        )

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------
    async def _on_send(self, event):
        """Handle both send-button clicks and Enter-key submissions."""

        # Guard against programmatic updates that restore the textarea content
        if self._internal_update:
            return

        # Safety-check: ensure we have the input widget
        input_widget = self.text_input_view[0]
        if input_widget is None:
            return

        # Only process genuine submissions once per cycle
        if self.sent:
            return  # already processed this submission

        # Ensure we are handling the ChatAreaInput submission
        if event.obj is not input_widget:
            return

        # Distinguish between the two trigger sources (button vs. Enter key)
        if event.obj is self.send_button_view:
            input_text = input_widget.value_input
        elif event.obj is input_widget:  # Enter
            input_text = input_widget.value_input
        else:
            return

        if not input_text or str(input_text).strip() == "":
            return

        content = str(input_text).strip()

        # Emit once
        payload = MessagePayload(role='user', content=content, mode='atomic')
        await self.ports.output['message_output'].stage_emit(payload=payload)
        self.model.payload = payload

        # --- restore text so it stays visible ---
        if not self.clear_after_send:
            event.obj.value        = content
            event.obj.value_input  = content

        self._update_text(content, mark_sent=True)

        if self.clear_after_send:
            event.obj.value_input = ''
            self.model.text = ''

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_text(self, content: str, mark_sent: bool):
        """Push `content` into model, textarea, markdown and optionally mark as sent."""
        self.model.text = content
        is_chat_input = (
            self.text_input_view is not None and
            isinstance(self.text_input_view[0], pn.chat.ChatAreaInput)
        )

        if self.text_input_view is not None:
            if is_chat_input:
                if not self.clear_after_send:
                    # For ChatAreaInput the frontend clears .value on submit.
                    # Restore it so the text remains visible.
                    self._internal_update = True
                    try:
                        self.text_input_view[0].value = content
                    finally:
                        self._internal_update = False
            else:
                self.text_input_view[0].value = content
        # Update placeholder payload content if it exists and has atomic mode
        if isinstance(self.model.payload, MessagePayload):
            self.model.payload.model.content = content
        # Let the watcher take care of updating CSS & check-mark
        self.sent = mark_sent