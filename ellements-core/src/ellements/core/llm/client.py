"""Primary LLM client implementation.

The :class:`LLMClient` is the single entry point to every supported
provider (via LiteLLM). It is async-only — there is no synchronous
companion API.

Key contracts:

- ``model`` is required at construction. There is no implicit default.
- Every method (``complete``, ``complete_structured``, ``complete_with_tools``,
  ``stream``, ``loglikelihood``, ``generate_image``) emits uniform
  :class:`LLMRequestEvent` / :class:`LLMResponseEvent` / :class:`LLMErrorEvent`
  events to all registered :class:`LLMObserver` instances.
- Transient failures are retried with exponential backoff plus full
  jitter, classified by litellm exception type. Strategies must not
  add their own retry layer.
- :meth:`complete_with_tools` raises :class:`MaxToolIterationsError`
  carrying the partial conversation and unresolved tool calls when
  the loop exceeds its iteration cap.
- :meth:`complete_structured` uses litellm's native
  ``response_format=PydanticModel`` and raises
  :class:`StructuredOutputUnsupportedError` for models that don't
  support JSON-mode.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import random
import time
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

import litellm
from pydantic import BaseModel

from ..exceptions import (
    ConversationError,
    LLMError,
    LogprobsUnsupportedError,
    MaxToolIterationsError,
    StructuredOutputUnsupportedError,
)
from ..observability import (
    JsonlPromptLogger,
    LLMErrorEvent,
    LLMObserver,
    LLMRequestEvent,
    LLMResponseEvent,
)
from ..tools import (
    ToolCallRecord,
    ToolCallResponse,
    ToolDialect,
    ToolExecutor,
    ToolRegistry,
    default_dialect_for_model,
)
from .images import (
    ImageGenerationResponse,
    build_image_edit_request,
    build_image_generation_request,
    parse_image_generation_response,
)
from .messages import Conversation, MessageInput, normalize_message_input
from .requests import (
    configure_litellm_globals,
    extract_response_text,
    prepare_completion_request,
)
from .structured import (
    ensure_structured_support,
    parse_structured_content,
)

T = TypeVar("T", bound=BaseModel)

_logger = logging.getLogger(__name__)


def _is_raw_tool_definition(item: Any) -> bool:
    """Return whether *item* already matches an OpenAI Chat function-tool dict."""
    if not isinstance(item, Mapping):
        return False
    function = item.get("function")
    return (
        item.get("type") == "function"
        and isinstance(function, Mapping)
        and isinstance(function.get("name"), str)
    )


def _coerce_to_registry_and_extras(
    tools: ToolRegistry | Iterable[Any] | Mapping[str, Any],
) -> tuple[ToolRegistry, list[dict[str, Any]]]:
    """Split *tools* into a managed registry and pass-through raw definitions."""
    if isinstance(tools, ToolRegistry):
        return tools, []
    registry = ToolRegistry()
    raw_extras: list[dict[str, Any]] = []
    items: Iterable[tuple[str | None, Any]]
    if isinstance(tools, Mapping):
        items = list(tools.items())
    else:
        items = [(None, item) for item in tools]
    for name_hint, item in items:
        if _is_raw_tool_definition(item):
            raw_extras.append(copy.deepcopy(dict(item)))
            continue
        registry.register(item, name=name_hint)
    return registry, raw_extras


def _classify_retryable(exc: BaseException) -> bool:
    """Return whether *exc* is a transient litellm error worth retrying.

    Classification is type-based using litellm's exception hierarchy.
    No string matching, no opaque heuristics.
    """
    transient_types: tuple[type[BaseException], ...] = (
        litellm.RateLimitError,
        litellm.ServiceUnavailableError,
        litellm.APIConnectionError,
        litellm.Timeout,
        litellm.InternalServerError,
    )
    return isinstance(exc, transient_types)


def _full_jitter_backoff(
    attempt: int, *, base: float = 0.5, cap: float = 30.0
) -> float:
    """Return an AWS-style full-jitter backoff delay for *attempt* (0-indexed)."""
    return random.uniform(0.0, min(cap, base * (2**attempt)))


@dataclass
class _ToolLoopState:
    """Mutable per-iteration state for :meth:`LLMClient.complete_with_tools`.

    Bundling the loop's three "growing" pieces — the running message
    list, the per-call audit log, and the most recent assistant
    message — keeps the loop body small and makes it obvious which
    pieces escape into the final response or error.
    """

    llm_messages: list[dict[str, Any]]
    tool_log: list[ToolCallRecord] = field(default_factory=list)
    assistant_msg: Any = None

    async def run_tool_calls(
        self,
        tool_calls: Iterable[Any],
        executor: ToolExecutor,
    ) -> None:
        """Invoke every requested tool, recording results in-place.

        Appends one ``role=tool`` message per call so the next LLM
        turn sees the resolved outputs in order.
        """
        for tool_call in tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            _logger.debug("Tool call: %s(%s)", fn_name, fn_args)
            result_str = await executor(fn_name, fn_args)
            self.tool_log.append(
                ToolCallRecord(
                    name=fn_name,
                    arguments=fn_args,
                    result=result_str,
                )
            )
            self.llm_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str,
                }
            )


class LLMClient:
    """Generic LLM client supporting multiple providers via LiteLLM.

    Args:
        model: Required default model identifier (litellm format, e.g.
            ``"openai/gpt-4o"`` or ``"anthropic/claude-3-5-sonnet-20241022"``).
        use_responses_api: Use OpenAI's Responses API (only relevant for
            ``openai/gpt-5*``).
        observers: Sequence of :class:`LLMObserver` implementations to
            notify on every request, response, and error.
        log_dir: Convenience shorthand — when provided, a
            :class:`JsonlPromptLogger` is created at this path and added
            to the observer chain.
        max_retries: Maximum number of retries on transient errors. The
            initial attempt is *not* counted. Default 3.
        retry_base_delay: Base delay (seconds) for exponential backoff
            with full jitter. Default 0.5.
        retry_max_delay: Cap on individual retry delays. Default 30.0.
        **kwargs: Provider configuration forwarded to LiteLLM
            (e.g. ``api_key``, ``base_url``).
    """

    def __init__(
        self,
        *,
        model: str,
        use_responses_api: bool = False,
        observers: Iterable[LLMObserver] | None = None,
        log_dir: str | Path | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 30.0,
        **kwargs: Any,
    ) -> None:
        if not model:
            raise ValueError("LLMClient(model=...) is required and must be non-empty.")

        self.model = model
        self.use_responses_api = use_responses_api
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.config = kwargs

        observers_list: list[LLMObserver] = list(observers or [])
        if log_dir is not None:
            observers_list.append(JsonlPromptLogger(log_dir))
        self._observers: list[LLMObserver] = observers_list

        configure_litellm_globals(self.config)

    # ── Observers ────────────────────────────────────────────────────

    @property
    def observers(self) -> list[LLMObserver]:
        """Mutable list of registered observers."""
        return self._observers

    def add_observer(self, observer: LLMObserver) -> None:
        """Register a new observer to receive future LLM events."""
        self._observers.append(observer)

    async def _emit_request(self, event: LLMRequestEvent) -> None:
        for observer in self._observers:
            try:
                await observer.on_request(event)
            except Exception as exc:
                _logger.warning("Observer on_request failed: %s", exc)

    async def _emit_response(self, event: LLMResponseEvent) -> None:
        for observer in self._observers:
            try:
                await observer.on_response(event)
            except Exception as exc:
                _logger.warning("Observer on_response failed: %s", exc)

    async def _emit_error(self, event: LLMErrorEvent) -> None:
        for observer in self._observers:
            try:
                await observer.on_error(event)
            except Exception as exc:
                _logger.warning("Observer on_error failed: %s", exc)

    # ── Retry wrapper ────────────────────────────────────────────────

    async def _call_with_retry(
        self, fn: Callable[[], Awaitable[Any]], *, what: str
    ) -> Any:
        """Run *fn* with retry+backoff on transient litellm errors."""
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await fn()
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries or not _classify_retryable(exc):
                    raise
                delay = _full_jitter_backoff(
                    attempt,
                    base=self.retry_base_delay,
                    cap=self.retry_max_delay,
                )
                _logger.warning(
                    "%s failed (attempt %d/%d, %s); retrying in %.2fs",
                    what,
                    attempt + 1,
                    self.max_retries + 1,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    # ── Shared call wrapper ──────────────────────────────────────────

    async def _invoke_litellm(
        self,
        *,
        call_id: str,
        method: str,
        model: str,
        messages: list[dict[str, Any]],
        request_params: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
        start: float,
        fail_label: str,
        extra_passthrough: tuple[type[BaseException], ...] = (),
    ) -> Any:
        """Call ``litellm.acompletion`` with uniform retry + error handling.

        On success, returns the raw litellm response. On error, emits
        :class:`LLMErrorEvent` and either re-raises (for
        :class:`LLMError` or any type in ``extra_passthrough``) or
        wraps the exception in :class:`LLMError` with a ``fail_label``
        prefix. Used by ``complete``, ``complete_structured``,
        ``stream``, ``complete_with_tools``, and ``loglikelihood`` so
        every method emits identical telemetry on failure.
        """
        try:
            if tools is None:
                return await self._call_with_retry(
                    lambda: litellm.acompletion(
                        model=model, messages=messages, **request_params
                    ),
                    what=method,
                )
            return await self._call_with_retry(
                lambda: litellm.acompletion(
                    model=model, messages=messages, tools=tools, **request_params
                ),
                what=method,
            )
        except Exception as exc:
            await self._emit_error(
                LLMErrorEvent(
                    call_id=call_id,
                    method=method,
                    model=model,
                    error=exc,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            if isinstance(exc, (LLMError, *extra_passthrough)):
                raise
            raise LLMError(f"{fail_label} failed: {exc}") from exc

    # ── Conversation helpers ─────────────────────────────────────────

    def create_conversation(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> Conversation:
        """Create a new :class:`Conversation` bound to this client's model."""
        return Conversation(model=model or self.model, system_prompt=system_prompt)

    # ── complete ─────────────────────────────────────────────────────

    async def complete(
        self,
        messages: MessageInput,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a single completion for *messages*."""
        call_id = str(uuid4())
        start = time.monotonic()
        llm_messages = normalize_message_input(messages)
        request = prepare_completion_request(
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_responses_api=self.use_responses_api,
            extra_params=kwargs,
        )
        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="complete",
                model=request.model,
                messages=llm_messages,
                temperature=temperature,
                max_tokens=request.logged_max_tokens,
                extra_params=dict(kwargs),
            )
        )

        response = await self._invoke_litellm(
            call_id=call_id,
            method="complete",
            model=request.model,
            messages=llm_messages,
            request_params=request.params,
            start=start,
            fail_label="Completion",
        )
        content = extract_response_text(response)
        await self._emit_response(
            LLMResponseEvent(
                call_id=call_id,
                method="complete",
                model=request.model,
                response=content,
                duration_ms=int((time.monotonic() - start) * 1000),
                usage=_usage_dict(response),
            )
        )
        return content

    # ── complete_structured ─────────────────────────────────────────

    async def complete_structured(
        self,
        messages: MessageInput,
        response_model: type[T],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> T:
        """Generate a structured Pydantic completion via litellm's native JSON mode.

        Raises:
            StructuredOutputUnsupportedError: If the model does not
                support native structured outputs.
            LLMError: If the model returns content that cannot be parsed
                into *response_model*.
        """
        call_id = str(uuid4())
        start = time.monotonic()
        target_model = model or self.model
        ensure_structured_support(target_model)

        llm_messages = normalize_message_input(messages)
        request = prepare_completion_request(
            model=target_model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_responses_api=self.use_responses_api,
            extra_params=kwargs,
        )
        request_params = dict(request.params)
        request_params["response_format"] = response_model

        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="complete_structured",
                model=request.model,
                messages=llm_messages,
                temperature=temperature,
                max_tokens=request.logged_max_tokens,
                extra_params={**kwargs, "response_format": response_model.__name__},
            )
        )

        response = await self._invoke_litellm(
            call_id=call_id,
            method="complete_structured",
            model=request.model,
            messages=llm_messages,
            request_params=request_params,
            start=start,
            fail_label="Structured completion",
            extra_passthrough=(StructuredOutputUnsupportedError,),
        )
        content = extract_response_text(response)
        parsed = parse_structured_content(
            content,
            response_model,
            error_context="Failed to parse structured response",
        )
        await self._emit_response(
            LLMResponseEvent(
                call_id=call_id,
                method="complete_structured",
                model=request.model,
                response=content,
                duration_ms=int((time.monotonic() - start) * 1000),
                usage=_usage_dict(response),
            )
        )
        return parsed

    # ── stream ───────────────────────────────────────────────────────

    async def stream(
        self,
        messages: MessageInput,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream completion tokens as they are produced."""
        call_id = str(uuid4())
        start = time.monotonic()
        llm_messages = normalize_message_input(messages)
        request = prepare_completion_request(
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_responses_api=self.use_responses_api,
            extra_params={"stream": True, **kwargs},
        )
        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="stream",
                model=request.model,
                messages=llm_messages,
                temperature=temperature,
                max_tokens=request.logged_max_tokens,
                extra_params=dict(kwargs),
            )
        )

        collected: list[str] = []
        try:
            response = await self._call_with_retry(
                lambda: litellm.acompletion(
                    model=request.model,
                    messages=llm_messages,
                    **request.params,
                ),
                what="stream",
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    collected.append(content)
                    yield content
        except Exception as exc:
            await self._emit_error(
                LLMErrorEvent(
                    call_id=call_id,
                    method="stream",
                    model=request.model,
                    error=exc,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            if isinstance(exc, LLMError):
                raise
            raise LLMError(f"Streaming failed: {exc}") from exc
        else:
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._emit_response(
                LLMResponseEvent(
                    call_id=call_id,
                    method="stream",
                    model=request.model,
                    response="".join(collected),
                    duration_ms=duration_ms,
                )
            )

    # ── continue_conversation ────────────────────────────────────────

    async def continue_conversation(
        self,
        conversation: Conversation,
        user_message: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Append *user_message* and an assistant response to *conversation*."""
        if not isinstance(conversation, Conversation):
            raise ConversationError("Expected Conversation object")

        conversation.user(user_message)
        response = await self.complete(
            conversation,
            model=conversation.model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        conversation.assistant(response)
        return response

    # ── complete_with_tools ──────────────────────────────────────────

    async def complete_with_tools(
        self,
        messages: MessageInput,
        tools: ToolRegistry | Mapping[str, Any] | Iterable[Any],
        *,
        tool_executor: ToolExecutor | None = None,
        dialect: ToolDialect | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        max_iterations: int = 10,
        **kwargs: Any,
    ) -> ToolCallResponse:
        """Run a multi-turn completion loop with tool/function calling.

        Args:
            messages: Conversation input (string, list of messages, or
                :class:`Conversation`).
            tools: A :class:`ToolRegistry`, an iterable of tools, or a
                ``{name: tool}`` mapping. Items may be :class:`Tool` /
                :class:`ToolSpec` / :class:`SimpleTool` / plain
                callables, or raw provider-format dicts (in which case
                *tool_executor* is required).
            tool_executor: Optional override executor. Required if any
                raw provider-format dicts are present in *tools*.
            dialect: Optional :class:`ToolDialect` override. Defaults to
                :func:`default_dialect_for_model` keyed off the model.
            model: Optional model override.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate per turn.
            max_iterations: Cap on tool-calling turns.

        Raises:
            MaxToolIterationsError: If the loop exceeds *max_iterations*
                without the model returning a final (tool-call-free)
                response. The error carries the partial conversation
                and unresolved tool calls.
        """
        call_id = str(uuid4())
        start = time.monotonic()
        llm_messages = normalize_message_input(messages)
        input_messages = [dict(message) for message in llm_messages]

        effective_executor, tool_definitions = self._prepare_tool_loop(
            tools=tools,
            tool_executor=tool_executor,
            dialect=dialect,
            model_override=model,
        )

        request = prepare_completion_request(
            model=model or self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_responses_api=self.use_responses_api,
            extra_params=kwargs,
        )

        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="complete_with_tools",
                model=request.model,
                messages=input_messages,
                temperature=temperature,
                max_tokens=request.logged_max_tokens,
                tools=tool_definitions,
                extra_params=dict(kwargs),
            )
        )

        state = _ToolLoopState(llm_messages=llm_messages)
        aggregate_usage: dict[str, Any] = {}
        for _ in range(max_iterations):
            response = await self._invoke_litellm(
                call_id=call_id,
                method="complete_with_tools",
                model=request.model,
                messages=state.llm_messages,
                request_params=request.params,
                tools=tool_definitions,
                start=start,
                fail_label="Tool-calling completion",
            )
            aggregate_usage = _merge_usage(
                aggregate_usage,
                _usage_dict(response),
            )
            state.assistant_msg = response.choices[0].message
            tool_calls = getattr(state.assistant_msg, "tool_calls", None)

            if not tool_calls:
                result = ToolCallResponse(
                    content=state.assistant_msg.content or "",
                    tool_calls=list(state.tool_log),
                )
                await self._emit_response(
                    LLMResponseEvent(
                        call_id=call_id,
                        method="complete_with_tools",
                        model=request.model,
                        response=result.content,
                        duration_ms=int((time.monotonic() - start) * 1000),
                        tool_calls=[r.model_dump() for r in state.tool_log],
                        usage=aggregate_usage or None,
                    )
                )
                return result

            state.llm_messages.append(
                _assistant_tool_call_message(state.assistant_msg, tool_calls)
            )
            await state.run_tool_calls(tool_calls, effective_executor)

        # Loop ended without a tool-call-free response.
        unresolved = _serialize_tool_calls(
            getattr(state.assistant_msg, "tool_calls", None)
            if state.assistant_msg
            else None
        )
        error = MaxToolIterationsError(
            f"complete_with_tools hit max_iterations={max_iterations} "
            "without converging on a final response.",
            max_iterations=max_iterations,
            messages=list(state.llm_messages),
            tool_calls_made=list(state.tool_log),
            unresolved_tool_calls=unresolved,
        )
        await self._emit_error(
            LLMErrorEvent(
                call_id=call_id,
                method="complete_with_tools",
                model=request.model,
                error=error,
                duration_ms=int((time.monotonic() - start) * 1000),
                metadata={"unresolved_tool_calls": len(unresolved)},
            )
        )
        raise error

    def _prepare_tool_loop(
        self,
        *,
        tools: ToolRegistry | Mapping[str, Any] | Iterable[Any],
        tool_executor: ToolExecutor | None,
        dialect: ToolDialect | None,
        model_override: str | None,
    ) -> tuple[ToolExecutor, list[dict[str, Any]]]:
        """Resolve the executor + dialect + serialized tool definitions.

        Extracted from :meth:`complete_with_tools` so the loop body
        reads as a state machine instead of mixing setup with control
        flow.
        """
        registry, raw_extras = _coerce_to_registry_and_extras(tools)
        effective_executor = tool_executor
        if effective_executor is None:
            if len(registry) == 0:
                raise ValueError(
                    "tool_executor is required when tools do not include "
                    "executable Tool/callable entries."
                )
            effective_executor = registry.executor()

        effective_dialect = dialect or default_dialect_for_model(
            model_override or self.model,
            use_responses_api=self.use_responses_api,
        )
        return effective_executor, registry.to_dialect(effective_dialect) + raw_extras

    # ── loglikelihood ────────────────────────────────────────────────

    async def loglikelihood(
        self,
        context: str,
        continuation: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> tuple[float, bool]:
        """Compute the log-likelihood of *continuation* given *context*.

        Raises:
            LogprobsUnsupportedError: If the provider does not expose
                token log-probabilities or returns malformed data.
        """
        call_id = str(uuid4())
        start = time.monotonic()
        target_max_tokens = max_tokens
        if target_max_tokens is None:
            target_max_tokens = max(1, len(continuation.split()) * 3)

        llm_messages = [{"role": "user", "content": context}]
        request = prepare_completion_request(
            model=model or self.model,
            temperature=0.0,
            max_tokens=target_max_tokens,
            use_responses_api=self.use_responses_api,
            extra_params={"logprobs": True, **kwargs},
        )
        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="loglikelihood",
                model=request.model,
                messages=llm_messages,
                temperature=0.0,
                max_tokens=request.logged_max_tokens,
                extra_params={"logprobs": True, **kwargs},
            )
        )

        try:
            response = await self._call_with_retry(
                lambda: litellm.acompletion(
                    model=request.model,
                    messages=llm_messages,
                    **request.params,
                ),
                what="loglikelihood",
            )
            choice = response.choices[0]
            generated = extract_response_text(response)
            raw_logprobs = getattr(choice, "logprobs", None)

            token_logprobs: Any
            if isinstance(raw_logprobs, dict):
                token_logprobs = raw_logprobs.get("token_logprobs")
            else:
                token_logprobs = getattr(raw_logprobs, "token_logprobs", None)

            if not isinstance(token_logprobs, list):
                raise LogprobsUnsupportedError(
                    f"Model {request.model!r} did not return token log-probabilities."
                )

            total_ll = float(
                sum(
                    value for value in token_logprobs if isinstance(value, (int, float))
                )
            )
            is_greedy = generated.strip().startswith(continuation.strip())
            await self._emit_response(
                LLMResponseEvent(
                    call_id=call_id,
                    method="loglikelihood",
                    model=request.model,
                    response=generated,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    metadata={"total_logprob": total_ll, "is_greedy": is_greedy},
                )
            )
            return total_ll, is_greedy
        except Exception as exc:
            await self._emit_error(
                LLMErrorEvent(
                    call_id=call_id,
                    method="loglikelihood",
                    model=request.model,
                    error=exc,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            if isinstance(exc, (LLMError, LogprobsUnsupportedError)):
                raise
            raise LLMError(f"Loglikelihood failed: {exc}") from exc

    # ── generate_image ───────────────────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str | None = None,
        n: int = 1,
        size: str | None = None,
        quality: str | None = None,
        style: str | None = None,
        response_format: str = "url",
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        """Generate images from a text prompt via LiteLLM image APIs."""
        call_id = str(uuid4())
        start = time.monotonic()
        target_model, params = build_image_generation_request(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            quality=quality,
            style=style,
            response_format=response_format,  # type: ignore[arg-type]
            extra_params=dict(kwargs),
        )
        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="generate_image",
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=None,
                max_tokens=None,
                extra_params={k: v for k, v in params.items() if k != "prompt"},
            )
        )

        try:
            response = await self._call_with_retry(
                lambda: litellm.aimage_generation(**params),
                what="generate_image",
            )
            parsed = parse_image_generation_response(
                response, target_model=target_model
            )
            await self._emit_response(
                LLMResponseEvent(
                    call_id=call_id,
                    method="generate_image",
                    model=target_model,
                    response=json.dumps(parsed.model_dump(), default=str),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            return parsed
        except Exception as exc:
            await self._emit_error(
                LLMErrorEvent(
                    call_id=call_id,
                    method="generate_image",
                    model=target_model,
                    error=exc,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            if isinstance(exc, LLMError):
                raise
            raise LLMError(f"Image generation failed: {exc}") from exc

    # ── edit_image ────────────────────────────────────────────────────

    async def edit_image(
        self,
        prompt: str,
        images: Sequence[tuple[str, bytes] | bytes],
        *,
        model: str | None = None,
        n: int = 1,
        size: str | None = None,
        quality: str | None = None,
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        """Edit/compose images from reference *images* and a text *prompt*.

        Each entry in *images* is either raw ``bytes`` or a ``(filename, bytes)``
        tuple. The references are uploaded to the provider's image-edit endpoint
        (e.g. ``gpt-image-1``) so the generated image is conditioned on them.
        """
        import io

        call_id = str(uuid4())
        start = time.monotonic()
        target_model, params = build_image_edit_request(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            quality=quality,
            extra_params=dict(kwargs),
        )

        references: list[tuple[str, bytes]] = []
        for index, item in enumerate(images):
            if isinstance(item, tuple):
                name, payload = item
            else:
                name, payload = f"reference_{index}.png", item
            references.append((name, payload))

        await self._emit_request(
            LLMRequestEvent(
                call_id=call_id,
                method="edit_image",
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=None,
                max_tokens=None,
                extra_params={
                    **{k: v for k, v in params.items() if k != "prompt"},
                    "reference_images": len(references),
                },
            )
        )

        async def _edit_attempt() -> Any:
            files: list[io.BytesIO] = []
            for name, payload in references:
                handle = io.BytesIO(payload)
                handle.name = name
                files.append(handle)
            try:
                return await litellm.aimage_edit(image=files, **params)
            finally:
                for handle in files:
                    handle.close()

        try:
            response = await self._call_with_retry(
                _edit_attempt,
                what="edit_image",
            )
            parsed = parse_image_generation_response(
                response, target_model=target_model
            )
            await self._emit_response(
                LLMResponseEvent(
                    call_id=call_id,
                    method="edit_image",
                    model=target_model,
                    response=json.dumps(parsed.model_dump(), default=str),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            return parsed
        except Exception as exc:
            await self._emit_error(
                LLMErrorEvent(
                    call_id=call_id,
                    method="edit_image",
                    model=target_model,
                    error=exc,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            if isinstance(exc, LLMError):
                raise
            raise LLMError(f"Image edit failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _usage_dict(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        data: dict[str, Any] = {}
    elif hasattr(usage, "model_dump"):
        data = usage.model_dump()
    elif hasattr(usage, "dict"):
        data = usage.dict()
    elif isinstance(usage, dict):
        data = dict(usage)
    else:
        data = {}

    hidden = getattr(response, "_hidden_params", None)
    if isinstance(hidden, Mapping):
        response_cost = hidden.get("response_cost")
        if isinstance(response_cost, int | float):
            data["response_cost"] = float(response_cost)
    return data or None


def _merge_usage(
    aggregate: Mapping[str, Any],
    current: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Add provider usage from one turn into a multi-turn total."""

    merged = dict(aggregate)
    if current is None:
        return merged
    for key, value in current.items():
        previous = merged.get(key)
        if isinstance(previous, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_usage(previous, value)
        elif (
            isinstance(previous, int | float)
            and not isinstance(previous, bool)
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ):
            merged[key] = previous + value
        else:
            merged[key] = value
    return merged


def _serialize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    if not tool_calls:
        return []
    serialized: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        serialized.append(
            {
                "id": getattr(tool_call, "id", None),
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
        )
    return serialized


def _assistant_tool_call_message(assistant_msg: Any, tool_calls: Any) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": assistant_msg.content or "",
        "tool_calls": _serialize_tool_calls(tool_calls),
    }


__all__ = [
    "LLMClient",
]
