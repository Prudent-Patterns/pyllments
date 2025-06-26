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
    markdown_view     = param.ClassSelector(class_=pn.pane.Markdown,         is_instance=True)
    send_button_view  = param.ClassSelector(class_=pn.widgets.Button,        is_instance=True)

    sent = param.Boolean(default=False, doc="Whether the text input is marked as sent.")

    # Whether the text input should be cleared after the Send button is pressed.
    clear_after_send = param.Boolean(default=False, doc="Clear textarea after emit if True.")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = TextModel(**params)

        # Set up ports individually for clarity
        self._message_output_setup()
        self._message_input_setup()
        self._message_emit_input_setup()

        # React to changes of the `sent` flag to keep CSS classes & check-mark in sync
        self.param.watch(self._on_sent_change, "sent")

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
            # Show the incoming text but do *not* mark it as sent nor re-emit.
            self._update_text(payload.model.content, mark_sent=False)

        self.ports.add_input("message_input", unpack_payload_callback=unpack_display)

    def _message_emit_input_setup(self):
        """Input port that displays and then re-emits the MessagePayload."""

        async def unpack_emit(payload: MessagePayload):
            # Display the incoming text, then forward it through the output port.
            self._update_text(payload.model.content, mark_sent=False)
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
                # Front-end auto-clear after sending; restore previous content
                self._internal_update = True
                try:
                    # Restore both .value and .value_input to keep UI & state in sync
                    event.obj.value = self.model.text
                    event.obj.value_input = self.model.text
                finally:
                    self._internal_update = False
                return

            # Regular user typing before sending
            self.model.text = new_text
            if self.sent:
                # Any *non-empty* user edit marks message as not sent
                self.sent = False
        text_area_input.param.watch(_on_input, "value_input")

        # Watch for Enter submissions (ChatAreaInput fires 'value' when the user presses Enter)
        text_area_input.param.watch(self._on_send, "value")

        # Return a Row containing the textarea and the status mark
        self.text_input_view = pn.Row(
            text_area_input,
            status_mark
        )
        return self.text_input_view

    @Component.view
    def create_markdown_view(self) -> pn.pane.Markdown:
        self.markdown_view = pn.pane.Markdown(self.model.text, sizing_mode="stretch_width")
        return self.markdown_view

    @Component.view
    def create_send_button_view(self, icon: str = "arrow-up", label: str = "Send"):
        self.send_button_view = pn.widgets.Button(name=label, icon=icon, icon_size="1.2em")
        self.send_button_view.on_click(self._on_send)
        return self.send_button_view

    @Component.view
    def create_input_view(self):
        return pn.Column(
            self.create_text_input_view(),
            pn.Spacer(height=5),
            self.create_send_button_view(height=30),
        )

    @Component.view
    def create_interface_view(self):
        """Column with input row on top and markdown view below."""
        return pn.Column(
            self.create_input_view(),
            pn.Spacer(height=6),
            self.create_markdown_view()
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
        input_widget = self.text_input_view[0] if self.text_input_view else None
        if input_widget is None:
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

        # Emit the payload downstream
        payload = MessagePayload(role="user", content=content, mode="atomic")
        await self.ports.output["message_output"].stage_emit(payload=payload)

        # Update markdown & mark as sent
        self._update_text(content, mark_sent=True)

        # Optionally clear the textarea afterwards to mimic chat behaviour
        if self.clear_after_send:
            input_widget.value_input = ''
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
        if self.markdown_view is not None:
            self.markdown_view.object = content
        # Let the watcher take care of updating CSS & check-mark
        self.sent = mark_sent

    # ------------------------------------------------------------------
    # Watchers
    # ------------------------------------------------------------------
    def _on_sent_change(self, event):
        """Synchronise CSS classes and ✓ symbol whenever `sent` changes."""
        sent_state = event.new

        # TextAreaInput widget is at index 0 in the Row
        if self.text_input_view is not None:
            text_widget = self.text_input_view[0]
            text_widget.css_classes = ["sent"] if sent_state else []

        # Check-mark markdown pane is at index 1 in the Row
        if self.text_input_view is not None and len(self.text_input_view) > 1:
            status_mark = self.text_input_view[1]
            status_mark.object = "✓" if sent_state else ""
            status_mark.css_classes = ["sent"] if sent_state else []
