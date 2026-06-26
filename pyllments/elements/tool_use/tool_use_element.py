from __future__ import annotations

import asyncio
import json
from typing import Any, Literal, Union

import param
from pydantic import BaseModel, Field, RootModel, create_model

from pyllments.base.element_base import Element
from pyllments.common.pydantic_models import CleanModel
from pyllments.payloads import MessagePayload, SchemaPayload, StructuredPayload, ToolUsePayload
from pyllments.runtime.scheduler import schedule_task

from .tool_use_model import ToolUseModel, build_adapters


class ToolUseElement(Element):
    """
    Framework element for model tool use with adapter-backed execution.

    Owns tool schema aggregation, tool-call normalization, permission-aware routing,
    and execution of approved ToolUsePayload instances.
    """

    _tools_schema = param.ClassSelector(default=None, class_=BaseModel, is_instance=False)

    def __init__(
        self,
        *,
        adapters=None,
        mcps=None,
        functions=None,
        tools_requiring_permission=None,
        flow_id: str | None = None,
        flow_version: str | None = None,
        **params,
    ):
        super().__init__(**params)
        self.flow_id = flow_id
        self.flow_version = flow_version
        adapter_list = build_adapters(
            adapters=adapters,
            mcps=mcps,
            functions=functions,
            tools_requiring_permission=tools_requiring_permission,
        )
        self.model = ToolUseModel(adapters=adapter_list)
        self._setup_ports()
        schedule_task(self._emit_latched_schema_outputs())

    async def _emit_latched_schema_outputs(self):
        """Emit tool schemas when adapter resources are ready."""
        await self.model.await_ready()
        await self.ports.output["tools_schema_output"].stage_emit(tools_schema=self.tools_schema)
        await self.ports.output["tools_output"].stage_emit(
            tools_list=self._provider_tool_definitions()
        )
        await self.ports.output["structured_tools_output"].stage_emit(
            tools_list=self._structured_tools_list()
        )

    def _setup_ports(self):
        self._tools_schema_output_setup()
        self._tools_output_setup()
        self._tool_request_structured_input_setup()
        self._tool_request_message_input_setup()
        self._approved_tool_use_input_setup()
        self._denied_tool_use_input_setup()
        self._tool_use_output_setup()
        self._tool_result_output_setup()

    async def await_ready(self):
        return await self.model.await_ready()

    def _provider_tool_definitions(self) -> list[dict[str, Any]]:
        tools_list = []
        for spec in self.model.tool_specs.values():
            parameters = dict(spec.parameters_schema)
            parameters.pop("title", None)
            tools_list.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.model_tool_name,
                        "description": spec.description,
                        "parameters": parameters,
                    },
                }
            )
        return tools_list

    def _structured_tools_list(self) -> list[dict[str, Any]]:
        tools_list = []
        for spec in self.model.tool_specs.values():
            parameters = dict(spec.parameters_schema)
            parameters.pop("title", None)
            tools_list.append(
                {
                    "name": spec.model_tool_name,
                    "description": spec.description,
                    "parameters": parameters,
                }
            )
        return tools_list

    def _build_tool_use_payload(
        self,
        requests: list[dict[str, Any]],
        *,
        turn_id: str | None = None,
    ) -> ToolUsePayload:
        payload = ToolUsePayload(
            turn_id=turn_id,
            correlation_id=turn_id,
            flow_id=self.flow_id,
            flow_version=self.flow_version,
            executor_element_name=self.name,
        )
        for request in requests:
            model_tool_name = request["name"]
            spec = self.model.spec_for_model_tool(model_tool_name)
            payload.model.add_tool_use(
                adapter_name=spec.adapter_name,
                provider_name=spec.provider_name,
                tool_name=spec.tool_name,
                model_tool_name=spec.model_tool_name,
                description=spec.description,
                parameters=request.get("parameters") or {},
                permission_required=spec.permission_required,
            )
        return payload

    @staticmethod
    def _parse_tool_call_parameters(arguments: str | dict | None) -> dict:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if not arguments.strip():
            return {}
        return json.loads(arguments)

    def _normalize_message_tool_calls(
        self,
        message: MessagePayload,
    ) -> list[dict[str, Any]]:
        requests = []
        for tool_call in message.model.tool_calls or []:
            function = tool_call.get("function") or {}
            requests.append(
                {
                    "name": function.get("name", ""),
                    "parameters": self._parse_tool_call_parameters(function.get("arguments")),
                    "tool_use_id": tool_call.get("id"),
                }
            )
        return requests

    async def _emit_tool_use(self, payload: ToolUsePayload):
        await self.ports.output["tool_use_output"].stage_emit(payload=payload)
        if not payload.model.needs_permission():
            payload.model.approve()
            executed = await self._execute_payload(payload)
            await self.ports.output["tool_result_output"].stage_emit(payload=executed)

    def _normalize_structured_requests(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "name": item["name"],
                "parameters": item.get("parameters") or {},
            }
            for item in data
        ]

    async def _execute_payload(self, payload: ToolUsePayload) -> ToolUsePayload:
        payload.model.recover_stale_running()
        tasks = []
        tool_use_ids = []
        for tool_use_id, record in payload.model.tool_uses.items():
            if not payload.model.can_execute(tool_use_id):
                continue
            payload.model.mark_running(tool_use_id)
            tool_use_ids.append(tool_use_id)
            tasks.append(self.model.execute_tool_use(record))

        if not tasks:
            return payload

        results = await asyncio.gather(*tasks)
        for tool_use_id, outcome in zip(tool_use_ids, results):
            if "error" in outcome:
                payload.model.attach_error(tool_use_id, outcome["error"])
            else:
                payload.model.attach_result(tool_use_id, outcome["result"])
        return payload

    def _tools_schema_output_setup(self):
        async def pack(tools_schema: type[BaseModel]) -> SchemaPayload:
            return SchemaPayload(schema=tools_schema)

        self.ports.add_output(
            name="tools_schema_output",
            pack_payload_callback=pack,
            readiness_check=self.model.await_ready,
            latched=True,
        )

    def _tools_output_setup(self):
        async def pack(tools_list: list[dict[str, Any]]) -> StructuredPayload:
            return StructuredPayload(data=tools_list)

        self.ports.add_output(
            name="tools_output",
            pack_payload_callback=pack,
            readiness_check=self.model.await_ready,
            latched=True,
        )

        async def pack_structured(tools_list: list[dict[str, Any]]) -> StructuredPayload:
            return StructuredPayload(data=tools_list)

        self.ports.add_output(
            name="structured_tools_output",
            pack_payload_callback=pack_structured,
            readiness_check=self.model.await_ready,
            latched=True,
        )

    def _tool_request_structured_input_setup(self):
        async def unpack(payload: StructuredPayload):
            await self.model.await_ready()
            requests = self._normalize_structured_requests(payload.model.data)
            tool_use = self._build_tool_use_payload(requests)
            await self._emit_tool_use(tool_use)

        self.ports.add_input(
            name="tool_request_structured_input",
            unpack_payload_callback=unpack,
            readiness_check=self.model.await_ready,
        )

    def _tool_request_message_input_setup(self):
        async def unpack(payload: MessagePayload):
            await self.model.await_ready()
            if payload.model.mode == "atomic" and not payload.model.ready:
                await payload.model.aget_message()
            elif payload.model.mode == "stream" and not payload.model.streamed:
                await payload.model.await_ready()
            turn_id = getattr(payload.model, "correlation_id", None)
            requests = self._normalize_message_tool_calls(payload)
            if not requests:
                return
            tool_use = self._build_tool_use_payload(requests, turn_id=turn_id)
            await self._emit_tool_use(tool_use)

        self.ports.add_input(
            name="tool_request_message_input",
            unpack_payload_callback=unpack,
            readiness_check=self.model.await_ready,
        )

    def _approved_tool_use_input_setup(self):
        async def unpack(payload: ToolUsePayload):
            payload.model.approve()
            executed = await self._execute_payload(payload)
            await self.ports.output["tool_result_output"].stage_emit(payload=executed)

        self.ports.add_input(
            name="approved_tool_use_input",
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload,
        )

    def _denied_tool_use_input_setup(self):
        async def unpack(payload: ToolUsePayload):
            reason = payload.model.metadata.get("denial_reason")
            payload.model.deny(reason=reason)
            await self.ports.output["tool_result_output"].stage_emit(payload=payload)

        self.ports.add_input(
            name="denied_tool_use_input",
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload,
        )

    def _tool_use_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(name="tool_use_output", pack_payload_callback=pack)

    def _tool_result_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(name="tool_result_output", pack_payload_callback=pack)

    @property
    def tools_schema(self) -> BaseModel:
        if not self._tools_schema:
            self._tools_schema = self.create_tools_schema(self.model.tool_specs)
        return self._tools_schema

    def create_tools_schema(self, tool_specs: dict):
        tool_schema_list = []
        for model_tool_name, spec in tool_specs.items():
            tool_schema_list.append(
                self.create_tool_model(
                    model_tool_name,
                    {
                        "description": spec.description,
                        "parameters": spec.parameters_schema,
                    },
                )
            )
        if not tool_schema_list:
            return create_model("tool_array", __base__=(RootModel[list], CleanModel))
        return create_model(
            "tool_array",
            __base__=(RootModel[list[Union[*tool_schema_list]]], CleanModel),
        )

    def create_tool_model(self, tool_name, tool_data):
        model_args = {}
        model_args["name"] = (Literal[tool_name], ...)
        if properties := tool_data["parameters"].get("properties"):
            model_args["parameters"] = (object, Field(json_schema_extra=properties))
        model_args["__doc__"] = tool_data["description"]
        model_args["__base__"] = CleanModel
        return create_model(tool_name, **model_args)
