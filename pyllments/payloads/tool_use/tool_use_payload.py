from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from jinja2 import Template

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload

from .tool_use_executor import ToolUseExecutor, ToolUseExecutorNotBoundError
from .tool_use_model import ToolUseModel

if TYPE_CHECKING:
    import panel as pn

__all__ = ["ToolUsePayload", "ToolUseExecutorNotBoundError"]

_EXECUTOR_REGISTRY: weakref.WeakValueDictionary[str, ToolUseExecutor] = (
    weakref.WeakValueDictionary()
)


class ToolUsePayload(Payload):
    """
    Durable payload representing one or more tool calls across their lifecycle.

    Execution is delegated to a bound runtime executor (typically ToolUseElement).
    Each payload stores ``executor_element_name``; live ``ToolUseElement`` instances
    register by name so hydrated payloads can rebind automatically.
    """

    parameters_template = Template("""```
{
{%- for key, value in parameters.items() %}
{{ key }}: {{ value }}{% if not loop.last %},{% endif %}
{%- endfor %}
}
```""")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolUseModel(**params)
        self._executor: ToolUseExecutor | None = None

    @classmethod
    def register_executor(cls, executor: ToolUseExecutor, name: str | None = None) -> None:
        """Register a live ToolUseElement executor by element name."""
        executor_name = name or getattr(executor, "name", None)
        if not executor_name:
            raise ValueError("Tool executor name is required for registration")
        _EXECUTOR_REGISTRY[executor_name] = executor

    @classmethod
    def unregister_executor(cls, executor: ToolUseExecutor | str) -> None:
        """Remove a registered executor when its element is torn down."""
        if isinstance(executor, str):
            _EXECUTOR_REGISTRY.pop(executor, None)
            return
        executor_name = getattr(executor, "name", None)
        if executor_name and _EXECUTOR_REGISTRY.get(executor_name) is executor:
            _EXECUTOR_REGISTRY.pop(executor_name, None)

    @classmethod
    def resolve_executor(cls, name: str | None) -> ToolUseExecutor | None:
        """Look up a registered executor by ToolUseElement name."""
        if not name:
            return None
        return _EXECUTOR_REGISTRY.get(name)

    @classmethod
    async def cancel_execution_for_owner(
        cls,
        execution_owner: str,
        *,
        interrupt_policy: str = "cancel",
    ) -> None:
        """Request cancellation of active invocations across registered executors."""
        for executor in list(_EXECUTOR_REGISTRY.values()):
            cancel = getattr(executor, "cancel_execution_for_owner", None)
            if cancel is None:
                continue
            await cancel(execution_owner, interrupt_policy=interrupt_policy)

    @classmethod
    def clear_executor_registry(cls) -> None:
        """Clear all registered executors. Intended for test isolation."""
        _EXECUTOR_REGISTRY.clear()

    def bind_executor(self, executor: ToolUseExecutor) -> ToolUsePayload:
        """Attach a live executor for in-memory execution delegation."""
        self._executor = executor
        return self

    def bind_registered_executor(self) -> bool:
        """
        Rebind this payload to a registered executor by ``executor_element_name``.

        Returns
        -------
        bool
            True when a live executor was found and bound.
        """
        executor = self.resolve_executor(self.model.executor_element_name)
        if executor is None:
            return False
        self.bind_executor(executor)
        return True

    @property
    def is_bound(self) -> bool:
        """Return whether this payload can execute approved tool records."""
        return self._executor is not None

    async def execute_approved(
        self,
        tool_call_indices: list[int] | None = None,
    ) -> ToolUsePayload:
        """
        Execute approved tool records through the bound executor.

        Parameters
        ----------
        tool_call_indices : list[int] or None
            Optional subset of tool-call list indices to execute.

        Raises
        ------
        ToolUseExecutorNotBoundError
            If execution is attempted before rebinding.
        """
        if not self.is_bound:
            self.bind_registered_executor()
        if not self.is_bound:
            raise ToolUseExecutorNotBoundError(
                "ToolUsePayload is not bound to an executor. "
                f"No live ToolUseElement named {self.model.executor_element_name!r} is registered."
            )
        return await self._executor.execute_tool_use_payload(
            self,
            tool_call_indices=tool_call_indices,
        )

    @Component.view
    def create_tool_use_view(
        self,
        card_css: list | None = None,
        str_css: list | None = None,
        parameters_css: list | None = None,
        response_md_css: list | None = None,
    ) -> pn.Column:
        """Render tool-use records by lifecycle status; execution stays in ToolUseElement."""
        import panel as pn

        card_css = card_css or []
        str_css = str_css or []
        parameters_css = parameters_css or []
        response_md_css = response_md_css or []

        # Header verb reflects where the record is in its lifecycle.
        status_verbs = {
            'awaiting_permission': ' is requesting to run ',
            'approved': ' is approved to run ',
            'running': ' is running ',
            'denied': ' was denied running ',
            'failed': ' failed running ',
        }

        cards = []
        for record in self.model.tool_calls:
            provider = record.get('provider_name') or record.get('adapter_name', '')
            tool_label = record.get('tool_name') or record.get('model_tool_name', '')
            status = record.get('status', 'pending')

            header = pn.Row(
                pn.pane.Str(provider, stylesheets=str_css),
                pn.pane.Str(status_verbs.get(status, ' has run '), styles={'font-size': '14px'}),
                pn.pane.Str(tool_label, stylesheets=str_css),
            )

            objects = []
            params = record.get('parameters') or {}
            if params:
                md = self.parameters_template.render(parameters=params)
                objects.append(pn.pane.Markdown(md, stylesheets=parameters_css))
            else:
                objects.append(pn.pane.Markdown('No parameters provided.', stylesheets=parameters_css))

            result = record.get('result')
            error = record.get('error')
            if result and result.get('content'):
                text = '\n'.join(
                    item.get('text', '')
                    for item in result['content']
                    if item.get('type') == 'text'
                )
                objects.append(
                    pn.Column(
                        pn.pane.Str('Response:', stylesheets=[":host {margin-bottom: 0px}"]),
                        pn.pane.Str(text, stylesheets=response_md_css),
                    )
                )
            elif error:
                objects.append(
                    pn.pane.Str(error.get('message', 'Tool failed'), stylesheets=response_md_css)
                )
            elif status == 'denied':
                reason = (record.get('permission') or {}).get('reason')
                objects.append(
                    pn.pane.Str(
                        f"Denied{': ' + reason if reason else ''}",
                        stylesheets=response_md_css,
                    )
                )
            else:
                objects.append(pn.pane.Str('Processing...', stylesheets=response_md_css))

            cards.append(
                pn.layout.Card(header=header, objects=objects, collapsed=False, stylesheets=card_css)
            )

        return pn.Column(*cards, styles={'flex': '0 0 auto', 'height': 'fit-content'})

    @Component.view
    def create_collapsible_view(
        self,
        card_css: list | None = None,
        str_css: list | None = None,
        parameters_css: list | None = None,
        response_md_css: list | None = None,
    ) -> pn.Column:
        """Collapsible view for history; delegates to the main tool-use view."""
        return self.create_tool_use_view(
            card_css=card_css,
            str_css=str_css,
            parameters_css=parameters_css,
            response_md_css=response_md_css,
        )
