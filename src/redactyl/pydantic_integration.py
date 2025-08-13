"""Pydantic integration for automatic PII protection of structured data."""

import asyncio
import functools
import inspect
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, TypeVar, cast

from pydantic import BaseModel, Field

from redactyl.batch import BatchDetector
from redactyl.callbacks import CallbackContext
from redactyl.core import PIILoop
from redactyl.detectors.base import PIIDetector
from redactyl.entity_tracker import GlobalEntityTracker
from redactyl.types import (
    PIIEntity,
    PIIType,
    RedactionState,
    RedactionToken,
    UnredactionIssue,
)
from redactyl.utils import filter_overlapping_tokens


# Sentinel value to distinguish unset from None
class UnsetType:
    """Sentinel type for unset values."""

    pass


UNSET = UnsetType()  # Sentinel for unset values

# Type variables for generic function signatures
T = TypeVar("T")
P = TypeVar("P")
F = TypeVar("F", bound=Callable[..., Any])


class HallucinationAction(Enum):
    """Actions to take when hallucinated tokens are detected during unredaction."""

    PRESERVE = auto()  # Keep the token as-is
    REPLACE = auto()  # Replace with custom text
    THROW = auto()  # Raise an exception
    IGNORE = auto()  # Remove the token


class HallucinationError(Exception):
    """Exception raised when hallucinated tokens are detected and action is THROW."""

    def __init__(self, issues: list[UnredactionIssue]):
        self.issues = issues
        tokens = [issue.token for issue in issues]
        super().__init__(f"Hallucinated tokens detected: {', '.join(tokens)}")


@dataclass
class HallucinationResponse:
    """Response for a single hallucination issue."""

    action: HallucinationAction
    replacement_text: str | None = None  # Used when action is REPLACE

    @classmethod
    def preserve(cls) -> "HallucinationResponse":
        """Create a response to preserve the hallucinated token."""
        return cls(action=HallucinationAction.PRESERVE)

    @classmethod
    def replace(cls, text: str) -> "HallucinationResponse":
        """Create a response to replace the hallucinated token."""
        return cls(action=HallucinationAction.REPLACE, replacement_text=text)

    @classmethod
    def throw(cls) -> "HallucinationResponse":
        """Create a response to throw an exception."""
        return cls(action=HallucinationAction.THROW)

    @classmethod
    def ignore(cls) -> "HallucinationResponse":
        """Create a response to remove the hallucinated token."""
        return cls(action=HallucinationAction.IGNORE)


# Module-level cache for the default detector to avoid reloading spaCy
_default_detector_cache: PIIDetector | None = None


def _get_default_detector() -> PIIDetector:
    """Get or create the default detector with caching to avoid reloading spaCy."""
    global _default_detector_cache
    if _default_detector_cache is None:
        from redactyl.detectors.presidio import PresidioDetector

        detector = PresidioDetector(
            use_gliner_for_names=False,
            language="en",
            supported_entities=[
                "PERSON",
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "LOCATION",
                "CREDIT_CARD",
                "IP_ADDRESS",
                "FIRST_NAME",
                "MIDDLE_NAME",
                "LAST_NAME",
            ],
        )
        _default_detector_cache = detector
    return _default_detector_cache


def _clear_default_detector_cache() -> None:
    """Clear the cached default detector. Useful for tests that need isolation."""
    global _default_detector_cache
    _default_detector_cache = None


class PIIConfig:
    """Configuration for PII protection with clean decorator API."""

    def __init__(
        self,
        detector: PIIDetector | None = None,
        *,
        batch_detection: bool = True,
        use_name_parsing: bool = True,
        fuzzy_unredaction: bool = False,
        on_hallucination: Callable[[list[UnredactionIssue]], list[HallucinationResponse]] | None = None,
        on_gliner_unavailable: Callable[[], None] | None | UnsetType = UNSET,
        on_detection: Callable[[list[PIIEntity]], None] | None = None,
        on_batch_error: Callable[[Exception], None] | None | UnsetType = UNSET,
        on_unredaction_issue: Callable[[UnredactionIssue], None] | None | UnsetType = UNSET,
        on_gliner_model_error: Callable[[str, Exception], None] | None | UnsetType = UNSET,
        traverse_containers: bool = True,
        on_stream_complete: Callable[[RedactionState], None] | None = None,
    ):
        """
        Initialize PII configuration.

        Args:
            detector: PII detector to use. If None, creates a default PresidioDetector
                     with nameparser for name component detection
            batch_detection: Whether to use batch detection for efficiency
            use_name_parsing: Whether to parse name components
            fuzzy_unredaction: Whether to allow fuzzy matching during unredaction
            on_hallucination: Callback for handling hallucinated tokens.
                              Receives list of UnredactionIssue objects,
                              returns list of HallucinationResponse objects.
            on_gliner_unavailable: Callback when GLiNER is not available.
                                  Called when GLiNER is requested but unavailable.
                                  None (default): use warnings.warn
                                  Callable: custom callback
            on_detection: Callback when PII entities are detected.
                         Receives list of detected PIIEntity objects.
                         Default: None (no callback)
            on_batch_error: Callback when batch processing encounters an error.
                           Receives the exception object.
                           None (default): use warnings.warn
                           Callable: custom callback
            on_unredaction_issue: Callback for individual unredaction issues.
                                 Receives UnredactionIssue object.
                                 Default: None (handled by on_hallucination)
            on_gliner_model_error: Callback when GLiNER model fails to load.
                                  Receives model name and exception.
                                  None (default): use warnings.warn
                                  Callable: custom callback
            traverse_containers: Whether to traverse and protect containers of models
                               (list, dict, tuple, set, frozenset). Default: True
            on_stream_complete: Callback invoked when streaming completes, receiving
                              the accumulated RedactionState. Useful for retrieving
                              state after streaming for later unredaction.

        Example:
            ```python
            # Custom logging
            config = PIIConfig(
                detector=detector,
                on_gliner_unavailable=lambda: logger.warning("GLiNER not available"),
                on_detection=lambda entities: metrics.record("pii.detected", len(entities)),
                on_hallucination=lambda issues: [
                    HallucinationResponse.replace("[REDACTED]")
                    if "EMAIL" in issue.token
                    else HallucinationResponse.preserve()
                    for issue in issues
                ]
            )

            # Custom handler to silence warnings
            config = PIIConfig(
                detector=detector,
                on_gliner_unavailable=lambda: None  # Don't warn about missing GLiNER
            )

            @config.protect
            def process_user(user: User) -> User:
                # User is automatically protected/unprotected
                return user
            ```
        """
        if detector is None:
            # Use cached default detector to avoid reloading spaCy
            detector = _get_default_detector()

        self.detector = detector
        self.batch_detection = batch_detection
        self.use_name_parsing = use_name_parsing
        self.fuzzy_unredaction = fuzzy_unredaction
        self.on_hallucination = on_hallucination

        # Set default callbacks if not provided (UNSET means use defaults, None means silence)
        if on_gliner_unavailable is UNSET:
            # UNSET (default) means use warnings.warn
            self.on_gliner_unavailable = lambda: warnings.warn(
                "GLiNER is not installed or unavailable. Install with: pip install redactyl[gliner]. "
                "Falling back to nameparser for name component detection.",
                UserWarning,
                stacklevel=3,
            )
        elif on_gliner_unavailable is None:
            # Explicit None means silence
            self.on_gliner_unavailable = None
        else:
            # Custom callback
            self.on_gliner_unavailable = on_gliner_unavailable

        self.on_detection = on_detection

        if on_batch_error is UNSET:
            # UNSET (default) means use warnings.warn
            def _batch_error_handler(exc: Exception) -> None:
                warnings.warn(f"Batch processing error: {exc}", RuntimeWarning, stacklevel=3)

            self.on_batch_error = _batch_error_handler
        elif on_batch_error is None:
            # Explicit None means silence
            self.on_batch_error = None
        else:
            # Custom callback
            self.on_batch_error = on_batch_error

        if on_unredaction_issue is UNSET:
            # Default: do not emit per-issue warnings automatically.
            # Hallucination handling can be configured via on_hallucination.
            self.on_unredaction_issue = None
        elif on_unredaction_issue is None:
            # Explicit None means silence
            self.on_unredaction_issue = None
        else:
            # Custom callback
            self.on_unredaction_issue = on_unredaction_issue

        if on_gliner_model_error is UNSET:
            # UNSET (default) means use warnings.warn
            def _gliner_model_error_handler(model: str, exc: Exception) -> None:
                warnings.warn(
                    f"Failed to load GLiNER model '{model}': {exc}. "
                    "Falling back to nameparser for name component detection.",
                    RuntimeWarning,
                    stacklevel=3,
                )

            self.on_gliner_model_error = _gliner_model_error_handler
        elif on_gliner_model_error is None:
            # Explicit None means silence
            self.on_gliner_model_error = None
        else:
            # Custom callback
            self.on_gliner_model_error = on_gliner_model_error

        self.traverse_containers = traverse_containers
        self.on_stream_complete = on_stream_complete

    def protect(self, func: F) -> F:
        """
        Decorator to automatically protect/unprotect PII in function arguments and returns.

        Args:
            func: Function to decorate

        Returns:
            Decorated function that handles PII automatically
        """
        # Check if function is async generator
        if inspect.isasyncgenfunction(func):
            return cast(F, self.protect_stream(func))

        # Check if function is regular generator
        if inspect.isgeneratorfunction(func):
            return cast(F, self.protect_stream_sync(func))

        # Check if function is async
        is_async = asyncio.iscoroutinefunction(func)

        # Get function signature for introspection
        sig = inspect.signature(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await self._process_with_protection_async(func, args, kwargs, sig)

            return cast(F, async_wrapper)
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return self._process_with_protection_sync(func, args, kwargs, sig)

            return cast(F, sync_wrapper)

    def protect_stream(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator for async generator functions that yield Pydantic models.

        Maintains PII state across all yields and handles both partial and complete responses.

        Args:
            func: Async generator function to decorate

        Returns:
            Decorated async generator that handles PII automatically
        """
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def async_gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create callback context from config
            callbacks = CallbackContext(
                on_gliner_unavailable=self.on_gliner_unavailable
                if isinstance(self.on_gliner_unavailable, Callable)
                else None,
                on_detection=self.on_detection,
                on_batch_error=self.on_batch_error if isinstance(self.on_batch_error, Callable) else None,
                on_unredaction_issue=self.on_unredaction_issue
                if isinstance(self.on_unredaction_issue, Callable)
                else None,
                on_gliner_model_error=self.on_gliner_model_error
                if isinstance(self.on_gliner_model_error, Callable)
                else None,
            )

            # Initialize protector
            protector = PydanticPIIProtector(
                detector=self.detector,
                batch_detection=self.batch_detection,
                use_name_parsing=self.use_name_parsing,
                fuzzy_unredaction=self.fuzzy_unredaction,
                traverse_containers=self.traverse_containers,
                callbacks=callbacks,
            )

            # Process input arguments
            protected_args: list[Any] = []
            protected_kwargs: dict[str, Any] = {}
            accumulated_state = RedactionState()

            # Bind arguments to get parameter names
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Collect all BaseModel arguments for batch processing
            model_params: list[BaseModel] = []
            model_param_info: list[tuple[str, bool]] = []

            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, BaseModel):
                    model_params.append(param_value)
                    model_param_info.append((param_name, param_name in bound.kwargs))

            # Process all input models together if there are multiple
            if len(model_params) > 1:
                # Batch process for consistent tokenization
                protected_models, accumulated_state = protector.protect_models_batch(model_params)

                # Map protected models back to their parameter positions
                model_idx = 0
                for param_name, param_value in bound.arguments.items():
                    if isinstance(param_value, BaseModel):
                        protected_model = protected_models[model_idx]
                        param_name, is_kwarg = model_param_info[model_idx]

                        if is_kwarg:
                            protected_kwargs[param_name] = protected_model
                        else:
                            protected_args.append(protected_model)

                        model_idx += 1
                    else:
                        # Pass through non-model arguments
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)
            else:
                # Process arguments individually
                for param_name, param_value in bound.arguments.items():
                    if isinstance(param_value, BaseModel):
                        # Protect this model
                        protected_model, state = protector.protect_model(param_value)

                        # Store protected version
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = protected_model
                        else:
                            protected_args.append(protected_model)

                        # Accumulate state
                        accumulated_state = accumulated_state.merge(state)
                    else:
                        # Pass through non-model arguments
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)

            # Call the async generator with protected arguments
            try:
                async for item in func(*protected_args, **protected_kwargs):
                    if isinstance(item, BaseModel):
                        # Protect the yielded model to redact its PII
                        protected_item, item_state = protector.protect_model(item)

                        # Merge the state from this yield into accumulated state
                        accumulated_state = accumulated_state.merge(item_state)

                        # Yield the protected (redacted) model
                        yield protected_item
                    else:
                        # Pass through non-model items
                        yield item
            finally:
                # Notify completion with accumulated state
                if callable(self.on_stream_complete):
                    self.on_stream_complete(accumulated_state)

        return async_gen_wrapper

    def protect_stream_sync(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator for sync generator functions that yield Pydantic models.

        Maintains PII state across all yields and handles both partial and complete responses.

        Args:
            func: Generator function to decorate

        Returns:
            Decorated generator that handles PII automatically
        """
        sig = inspect.signature(func)

        @functools.wraps(func)
        def gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create callback context from config
            callbacks = CallbackContext(
                on_gliner_unavailable=self.on_gliner_unavailable
                if isinstance(self.on_gliner_unavailable, Callable)
                else None,
                on_detection=self.on_detection,
                on_batch_error=self.on_batch_error if isinstance(self.on_batch_error, Callable) else None,
                on_unredaction_issue=self.on_unredaction_issue
                if isinstance(self.on_unredaction_issue, Callable)
                else None,
                on_gliner_model_error=self.on_gliner_model_error
                if isinstance(self.on_gliner_model_error, Callable)
                else None,
            )

            # Initialize protector
            protector = PydanticPIIProtector(
                detector=self.detector,
                batch_detection=self.batch_detection,
                use_name_parsing=self.use_name_parsing,
                fuzzy_unredaction=self.fuzzy_unredaction,
                traverse_containers=self.traverse_containers,
                callbacks=callbacks,
            )

            # Process input arguments
            protected_args: list[Any] = []
            protected_kwargs: dict[str, Any] = {}
            accumulated_state = RedactionState()

            # Bind arguments to get parameter names
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Collect all BaseModel arguments for batch processing
            model_params: list[BaseModel] = []
            model_param_info: list[tuple[str, bool]] = []

            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, BaseModel):
                    model_params.append(param_value)
                    model_param_info.append((param_name, param_name in bound.kwargs))

            # Process all input models together if there are multiple
            if len(model_params) > 1:
                # Batch process for consistent tokenization
                protected_models, accumulated_state = protector.protect_models_batch(model_params)

                # Map protected models back to their parameter positions
                model_idx = 0
                for param_name, param_value in bound.arguments.items():
                    if isinstance(param_value, BaseModel):
                        protected_model = protected_models[model_idx]
                        param_name, is_kwarg = model_param_info[model_idx]

                        if is_kwarg:
                            protected_kwargs[param_name] = protected_model
                        else:
                            protected_args.append(protected_model)

                        model_idx += 1
                    else:
                        # Pass through non-model arguments
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)
            else:
                # Process arguments individually
                for param_name, param_value in bound.arguments.items():
                    if isinstance(param_value, BaseModel):
                        # Protect this model
                        protected_model, state = protector.protect_model(param_value)

                        # Store protected version
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = protected_model
                        else:
                            protected_args.append(protected_model)

                        # Accumulate state
                        accumulated_state = accumulated_state.merge(state)
                    else:
                        # Pass through non-model arguments
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)

            # Call the generator with protected arguments
            try:
                for item in func(*protected_args, **protected_kwargs):
                    if isinstance(item, BaseModel):
                        # Protect the yielded model to redact its PII
                        protected_item, item_state = protector.protect_model(item)

                        # Merge the state from this yield into accumulated state
                        accumulated_state = accumulated_state.merge(item_state)

                        # Yield the protected (redacted) model
                        yield protected_item
                    else:
                        # Pass through non-model items
                        yield item
            finally:
                # Notify completion with accumulated state
                if callable(self.on_stream_complete):
                    self.on_stream_complete(accumulated_state)

        return gen_wrapper

    async def _process_with_protection_async(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        sig: inspect.Signature,
    ) -> Any:
        """Process async function call with PII protection."""
        # Create callback context from config
        callbacks = CallbackContext(
            on_gliner_unavailable=self.on_gliner_unavailable
            if isinstance(self.on_gliner_unavailable, Callable)
            else None,
            on_detection=self.on_detection,
            on_batch_error=self.on_batch_error if isinstance(self.on_batch_error, Callable) else None,
            on_unredaction_issue=self.on_unredaction_issue if isinstance(self.on_unredaction_issue, Callable) else None,
            on_gliner_model_error=self.on_gliner_model_error
            if isinstance(self.on_gliner_model_error, Callable)
            else None,
        )

        # Initialize protector
        protector = PydanticPIIProtector(
            detector=self.detector,
            batch_detection=self.batch_detection,
            use_name_parsing=self.use_name_parsing,
            fuzzy_unredaction=self.fuzzy_unredaction,
            traverse_containers=self.traverse_containers,
            callbacks=callbacks,
        )

        # Process arguments
        protected_args: list[Any] = []
        protected_kwargs: dict[str, Any] = {}
        accumulated_state = RedactionState()

        # Bind arguments to get parameter names
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # Collect all BaseModel arguments for batch processing
        model_params: list[BaseModel] = []
        model_param_info: list[tuple[str, bool]] = []  # Track (param_name, is_kwarg) for each model

        for param_name, param_value in bound.arguments.items():
            if isinstance(param_value, BaseModel):
                model_params.append(param_value)
                model_param_info.append((param_name, param_name in bound.kwargs))

        # Process all models together if there are multiple
        if len(model_params) > 1:
            # Batch process for consistent tokenization
            protected_models, accumulated_state = protector.protect_models_batch(model_params)

            # Map protected models back to their parameter positions
            model_idx = 0
            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, BaseModel):
                    protected_model = protected_models[model_idx]
                    param_name, is_kwarg = model_param_info[model_idx]

                    if is_kwarg:
                        protected_kwargs[param_name] = protected_model
                    else:
                        protected_args.append(protected_model)

                    model_idx += 1
                else:
                    # Pass through or protect non-model arguments
                    if self.traverse_containers:
                        new_val, st = protector.protect_any(param_value)
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = new_val
                        else:
                            protected_args.append(new_val)
                        accumulated_state = accumulated_state.merge(st)
                    else:
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)
        else:
            # Process arguments individually
            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, BaseModel):
                    # Protect this model
                    protected_model, state = protector.protect_model(param_value)

                    # Store protected version
                    if param_name in bound.kwargs:
                        protected_kwargs[param_name] = protected_model
                    else:
                        protected_args.append(protected_model)

                    # Accumulate state
                    accumulated_state = accumulated_state.merge(state)
                else:
                    # Pass through or protect non-model arguments
                    if self.traverse_containers:
                        new_val, st = protector.protect_any(param_value)
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = new_val
                        else:
                            protected_args.append(new_val)
                        accumulated_state = accumulated_state.merge(st)
                    else:
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)

        # Call the async function with protected arguments
        result = await func(*protected_args, **protected_kwargs)

        # Process return value
        if isinstance(result, BaseModel):
            # Unprotect the result
            unprotected_result, issues = protector.unprotect_model(result, accumulated_state)

            # Handle hallucination issues if callback provided
            if issues and self.on_hallucination:
                responses = self.on_hallucination(issues)
                unprotected_result = self._apply_hallucination_responses(unprotected_result, issues, responses)
            elif issues:
                # Default behavior: warn unless explicitly silenced
                if self.on_unredaction_issue is not None and callable(self.on_unredaction_issue):
                    for issue in issues:
                        self.on_unredaction_issue(issue)
                else:
                    for issue in issues:
                        warnings.warn(
                            f"PII unredaction issue: {issue.token} - {issue.issue_type}"
                            + (f" ({issue.details})" if issue.details else ""),
                            UserWarning,
                            stacklevel=3,
                        )

            return unprotected_result
        else:
            # Non-BaseModel return
            if self.traverse_containers:
                return self._unprotect_and_handle_hallucinations(result, protector, accumulated_state)
            else:
                return result

    def _unprotect_and_handle_hallucinations(
        self,
        result: Any,
        protector: "PydanticPIIProtector",
        accumulated_state: RedactionState,
    ) -> Any:
        """Helper to unprotect container results and handle hallucinations."""
        unprotected, issues = protector.unprotect_any(result, accumulated_state)

        if not issues:
            return unprotected

        if self.on_hallucination:
            responses = self.on_hallucination(issues)
            if len(responses) != len(issues):
                raise ValueError(f"Mismatch between issues ({len(issues)}) and responses ({len(responses)})")

            # Build replacements map from responses
            replacements: dict[str, str | None] = {}
            for issue, response in zip(issues, responses, strict=False):
                if response.action == HallucinationAction.THROW:
                    raise HallucinationError([issue])
                if response.action == HallucinationAction.PRESERVE:
                    continue
                if response.action == HallucinationAction.REPLACE:
                    replacements[issue.token] = response.replacement_text or ""
                if response.action == HallucinationAction.IGNORE:
                    replacements[issue.token] = ""

            if replacements:
                unprotected = protector.apply_replacements_to_any(unprotected, replacements)
            return unprotected

        # Default: route to per-issue handler or warn
        if self.on_unredaction_issue is not None and callable(self.on_unredaction_issue):
            for issue in issues:
                self.on_unredaction_issue(issue)
        else:
            for issue in issues:
                warnings.warn(
                    f"PII unredaction issue: {issue.token} - {issue.issue_type}"
                    + (f" ({issue.details})" if issue.details else ""),
                    UserWarning,
                    stacklevel=3,
                )
        return unprotected

    def _process_with_protection_sync(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        sig: inspect.Signature,
    ) -> Any:
        """Process sync function call with PII protection."""
        # Create callback context from config
        callbacks = CallbackContext(
            on_gliner_unavailable=self.on_gliner_unavailable
            if isinstance(self.on_gliner_unavailable, Callable)
            else None,
            on_detection=self.on_detection,
            on_batch_error=self.on_batch_error if isinstance(self.on_batch_error, Callable) else None,
            on_unredaction_issue=self.on_unredaction_issue if isinstance(self.on_unredaction_issue, Callable) else None,
            on_gliner_model_error=self.on_gliner_model_error
            if isinstance(self.on_gliner_model_error, Callable)
            else None,
        )

        # Initialize protector
        protector = PydanticPIIProtector(
            detector=self.detector,
            batch_detection=self.batch_detection,
            use_name_parsing=self.use_name_parsing,
            fuzzy_unredaction=self.fuzzy_unredaction,
            traverse_containers=self.traverse_containers,
            callbacks=callbacks,
        )

        # Process arguments
        protected_args: list[Any] = []
        protected_kwargs: dict[str, Any] = {}
        accumulated_state = RedactionState()

        # Bind arguments to get parameter names
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # Collect all BaseModel arguments for batch processing
        model_params: list[BaseModel] = []
        model_param_info: list[tuple[str, bool]] = []  # Track (param_name, is_kwarg) for each model

        for param_name, param_value in bound.arguments.items():
            if isinstance(param_value, BaseModel):
                model_params.append(param_value)
                model_param_info.append((param_name, param_name in bound.kwargs))

        # Process all models together if there are multiple
        if len(model_params) > 1:
            # Batch process for consistent tokenization
            protected_models, accumulated_state = protector.protect_models_batch(model_params)

            # Map protected models back to their parameter positions
            model_idx = 0
            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, BaseModel):
                    protected_model = protected_models[model_idx]
                    param_name, is_kwarg = model_param_info[model_idx]

                    if is_kwarg:
                        protected_kwargs[param_name] = protected_model
                    else:
                        protected_args.append(protected_model)

                    model_idx += 1
                else:
                    # Pass through or protect non-model arguments
                    if self.traverse_containers:
                        new_val, st = protector.protect_any(param_value)
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = new_val
                        else:
                            protected_args.append(new_val)
                        accumulated_state = accumulated_state.merge(st)
                    else:
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)
        else:
            # Process arguments individually
            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, BaseModel):
                    # Protect this model
                    protected_model, state = protector.protect_model(param_value)

                    # Store protected version
                    if param_name in bound.kwargs:
                        protected_kwargs[param_name] = protected_model
                    else:
                        protected_args.append(protected_model)

                    # Accumulate state
                    accumulated_state = accumulated_state.merge(state)
                else:
                    # Pass through or protect non-model arguments
                    if self.traverse_containers:
                        new_val, st = protector.protect_any(param_value)
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = new_val
                        else:
                            protected_args.append(new_val)
                        accumulated_state = accumulated_state.merge(st)
                    else:
                        if param_name in bound.kwargs:
                            protected_kwargs[param_name] = param_value
                        else:
                            protected_args.append(param_value)

        # Call the sync function with protected arguments
        result = func(*protected_args, **protected_kwargs)

        # Process return value
        if isinstance(result, BaseModel):
            # Unprotect the result
            unprotected_result, issues = protector.unprotect_model(result, accumulated_state)

            # Handle hallucination issues if callback provided
            if issues and self.on_hallucination:
                responses = self.on_hallucination(issues)
                unprotected_result = self._apply_hallucination_responses(unprotected_result, issues, responses)
            elif issues:
                # Default behavior: warn unless explicitly silenced
                if self.on_unredaction_issue is not None and callable(self.on_unredaction_issue):
                    for issue in issues:
                        self.on_unredaction_issue(issue)
                else:
                    for issue in issues:
                        warnings.warn(
                            f"PII unredaction issue: {issue.token} - {issue.issue_type}"
                            + (f" ({issue.details})" if issue.details else ""),
                            UserWarning,
                            stacklevel=3,
                        )

            return unprotected_result
        else:
            # Non-BaseModel return
            if self.traverse_containers:
                return self._unprotect_and_handle_hallucinations(result, protector, accumulated_state)
            else:
                return result

    def _apply_hallucination_responses(
        self,
        model: BaseModel,
        issues: list[UnredactionIssue],
        responses: list[HallucinationResponse],
    ) -> BaseModel:
        """
        Apply hallucination responses to a model.

        Processes the responses and applies replacements to the model.
        """
        if len(issues) != len(responses):
            raise ValueError(f"Mismatch between issues ({len(issues)}) and responses ({len(responses)})")

        # Collect replacements to make
        replacements: dict[str, str | None] = {}

        for issue, response in zip(issues, responses, strict=False):
            if response.action == HallucinationAction.THROW:
                # Throw exception immediately
                raise HallucinationError([issue])
            elif response.action == HallucinationAction.PRESERVE:
                # Keep the token as-is (do nothing)
                continue
            elif response.action == HallucinationAction.REPLACE:
                # Replace with specified text
                replacements[issue.token] = response.replacement_text or ""
            elif response.action == HallucinationAction.IGNORE:
                # Remove the token (replace with empty string)
                replacements[issue.token] = ""

        if not replacements:
            # No changes needed
            return model

        # Apply replacements to all string fields in the model
        model_dict = model.model_dump()
        self._apply_replacements_to_dict(model_dict, replacements)

        # Create new model with replacements applied
        return model.__class__.model_validate(model_dict)

    def _apply_replacements_to_dict(self, data: Any, replacements: dict[str, str | None]) -> None:
        """
        Recursively apply string replacements to a dictionary.

        Modifies the dictionary in place.
        """
        if isinstance(data, dict):
            # Recurse into dictionary
            data_dict: dict[Any, Any] = data  # type: ignore[reportUnknownVariableType]
            for key, value in data_dict.items():
                if isinstance(value, str):
                    # Apply replacements
                    new_value = value
                    for token, replacement in replacements.items():
                        if replacement is not None and token in new_value:
                            new_value = new_value.replace(token, replacement)
                    data[key] = new_value
                else:
                    self._apply_replacements_to_dict(value, replacements)
        elif isinstance(data, list):
            # Recurse into list
            data_list: list[Any] = data  # type: ignore[reportUnknownVariableType]
            for i, item in enumerate(data_list):
                if isinstance(item, str):
                    # Apply replacements
                    new_value = item
                    for token, replacement in replacements.items():
                        if replacement is not None and token in new_value:
                            new_value = new_value.replace(token, replacement)
                    data[i] = new_value
                else:
                    self._apply_replacements_to_dict(item, replacements)


@dataclass
class PIIFieldConfig:
    """Configuration for a PII field."""

    pii_type: PIIType | None = None
    detect: bool = True
    parse_components: bool = False  # For name fields


def pii_field(
    pii_type: PIIType | None = None,
    *,
    detect: bool = True,
    parse_components: bool = False,
    **field_kwargs: Any,
) -> Any:
    """
    Mark a Pydantic field as containing PII.

    Args:
        pii_type: Optional explicit PII type (auto-detected if not provided)
        detect: Whether to detect PII in this field
        parse_components: For name fields, whether to parse into components
        **field_kwargs: Additional Pydantic Field arguments

    Returns:
        Annotated field with PII configuration

    Example:
        ```python
        class User(BaseModel):
            name: Annotated[str, pii_field(PIIType.PERSON, parse_components=True)]
            email: Annotated[str, pii_field(PIIType.EMAIL)]
            notes: str  # Will be auto-detected
        ```
    """
    config = PIIFieldConfig(pii_type=pii_type, detect=detect, parse_components=parse_components)

    # Create Pydantic Field with our config in metadata
    field_info = Field(**field_kwargs)
    if not hasattr(field_info, "metadata"):
        field_info.metadata = []  # type: ignore[attr-defined]
    field_info.metadata.append(config)  # type: ignore[attr-defined]

    return field_info


class PydanticPIIProtector:
    """Handles PII protection for Pydantic models."""

    def __init__(
        self,
        detector: PIIDetector,
        batch_detection: bool = True,
        use_name_parsing: bool = True,
        fuzzy_unredaction: bool = False,
        traverse_containers: bool = True,
        callbacks: "CallbackContext | None" = None,
    ):
        """
        Initialize Pydantic PII protector.

        Args:
            detector: PII detector to use
            batch_detection: Whether to use batch detection for efficiency
            use_name_parsing: Whether to parse name components
            fuzzy_unredaction: Whether to allow fuzzy matching during unredaction
            traverse_containers: Whether to traverse and protect containers of models
            callbacks: Callback context for event handling
        """
        self.detector = detector
        self.batch_detection = batch_detection
        self.use_name_parsing = use_name_parsing
        self.fuzzy_unredaction = fuzzy_unredaction
        self.traverse_containers = traverse_containers

        if callbacks is None:
            callbacks = CallbackContext.with_defaults()
        self.callbacks = callbacks

        # Initialize components with callbacks
        self.redactyl = PIILoop(detector, callbacks=callbacks)
        self.batch_detector = BatchDetector(
            detector,
            use_position_tracking=True,
            use_name_parsing=use_name_parsing,
            callbacks=callbacks,
        )
        self.entity_tracker = GlobalEntityTracker()

    def protect_model[M: BaseModel](self, model: M, path_prefix: str = "") -> tuple[M, RedactionState]:
        """
        Redact PII in a Pydantic model.

        Args:
            model: The Pydantic model to protect
            path_prefix: Optional path prefix for nested models

        Returns:
            Tuple of (protected model copy, redaction state)
        """
        # Extract all string fields with their paths
        fields_to_process = self._extract_string_fields(model, path_prefix)

        if not fields_to_process:
            # No string fields to process
            return model.model_copy(), RedactionState()

        if self.batch_detection and len(fields_to_process) > 1:
            # Use batch detection for multiple fields
            protected_data, state = self._batch_protect(fields_to_process)
        else:
            # Process fields individually
            protected_data, state = self._individual_protect(fields_to_process)

        # Create a new model with protected data
        protected_model = self._apply_protected_data(model, protected_data, path_prefix)

        return protected_model, state

    def protect_models_batch[M: BaseModel](self, models: list[M]) -> tuple[list[M], RedactionState]:
        """
        Protect multiple models in a single batch for consistent tokenization.

        Args:
            models: List of Pydantic models to protect

        Returns:
            Tuple of (list of protected models, combined redaction state)
        """
        if not models:
            return [], RedactionState()

        # Extract all fields from all models with unique paths
        all_fields: dict[str, str] = {}
        model_field_mapping: dict[int, dict[str, str]] = {}

        for idx, model in enumerate(models):
            model_prefix = f"model_{idx}"
            model_fields = self._extract_string_fields(model, model_prefix)
            model_field_mapping[idx] = model_fields
            all_fields.update(model_fields)

        if not all_fields:
            # No string fields to process
            return [m.model_copy() for m in models], RedactionState()

        # Detect PII in all fields together
        entities_by_field = self.batch_detector.detect_batch(all_fields)

        # Use entity tracker for consistent tokens across all models
        tokens_by_field = self.entity_tracker.assign_tokens(entities_by_field)

        # Build protected models and accumulate state
        protected_models: list[M] = []
        accumulated_state = RedactionState()

        for idx, model in enumerate(models):
            model_prefix = f"model_{idx}"
            model_fields = model_field_mapping[idx]

            # Get protected data for this model's fields
            protected_data: dict[str, Any] = {}
            for field_path, field_value in model_fields.items():
                if field_path in tokens_by_field:
                    # Apply redactions
                    redacted_text = field_value
                    field_tokens = tokens_by_field[field_path]

                    # Sort tokens by position (reverse order for replacement)
                    sorted_tokens = sorted(field_tokens, key=lambda t: t.entity.start, reverse=True)

                    for token in sorted_tokens:
                        # Replace in text
                        redacted_text = (
                            redacted_text[: token.entity.start] + token.token + redacted_text[token.entity.end :]
                        )

                        # Add to state
                        accumulated_state = accumulated_state.with_token(token.token, token)

                    # Store without the model prefix
                    clean_path = (
                        field_path.replace(f"{model_prefix}.", "", 1)
                        if field_path.startswith(f"{model_prefix}.")
                        else field_path
                    )
                    protected_data[clean_path] = redacted_text
                else:
                    # No PII detected
                    clean_path = (
                        field_path.replace(f"{model_prefix}.", "", 1)
                        if field_path.startswith(f"{model_prefix}.")
                        else field_path
                    )
                    protected_data[clean_path] = field_value

            # Create protected model
            protected_model = self._apply_protected_data(model, protected_data, "")
            protected_models.append(protected_model)

        return protected_models, accumulated_state

    def unprotect_model[M: BaseModel](
        self, model: M, state: RedactionState, path_prefix: str = ""
    ) -> tuple[M, list[UnredactionIssue]]:
        """
        Unredact PII in a Pydantic model.

        Args:
            model: The protected Pydantic model
            state: The redaction state from protection
            path_prefix: Optional path prefix for nested models

        Returns:
            Tuple of (unprotected model copy, list of issues)
        """
        # Extract all string fields with their paths
        fields_to_process = self._extract_string_fields(model, path_prefix)

        if not fields_to_process:
            # No string fields to process
            return model.model_copy(), []

        # Unredact all fields
        unprotected_data: dict[str, str] = {}
        all_issues: list[UnredactionIssue] = []

        for field_path, field_value in fields_to_process.items():
            unredacted, issues = self.redactyl.unredact(field_value, state, fuzzy=self.fuzzy_unredaction)
            unprotected_data[field_path] = unredacted
            all_issues.extend(issues)

        # Create a new model with unprotected data
        unprotected_model = self._apply_protected_data(model, unprotected_data, path_prefix)

        return unprotected_model, all_issues

    def _extract_string_fields(self, model: BaseModel, path_prefix: str = "") -> dict[str, str]:
        """
        Extract all string fields from a model recursively.

        Returns a flat dictionary with dot-notation paths as keys.
        """
        fields: dict[str, str] = {}

        for field_name, field_value in model.model_dump().items():
            field_path = f"{path_prefix}.{field_name}" if path_prefix else field_name

            # Get field info to check for PII configuration
            field_info = model.__class__.model_fields.get(field_name)
            skip_field = False
            if field_info and hasattr(field_info, "metadata"):
                # Check if field is marked to skip detection
                for meta in field_info.metadata:
                    if isinstance(meta, PIIFieldConfig) and not meta.detect:
                        skip_field = True
                        break

            if skip_field:
                # Skip this field entirely
                continue

            if isinstance(field_value, str):
                # String field - add to processing
                fields[field_path] = field_value
            elif isinstance(field_value, BaseModel):
                # Nested model - recurse
                nested_fields = self._extract_string_fields(field_value, field_path)
                fields.update(nested_fields)
            elif isinstance(field_value, dict):
                # Dictionary - recursively extract from nested structures
                self._extract_from_dict(field_value, field_path, fields)
            elif isinstance(field_value, list):
                # List - check for strings or models
                for idx, item in enumerate(field_value):  # type: ignore[arg-type]
                    item_path = f"{field_path}[{idx}]"
                    if isinstance(item, str):
                        fields[item_path] = item
                    elif isinstance(item, BaseModel):
                        nested_fields = self._extract_string_fields(item, item_path)
                        fields.update(nested_fields)

        return fields

    def _extract_from_dict(self, data: dict[str, Any], path_prefix: str, fields: dict[str, str]) -> None:
        """
        Recursively extract string fields from a dictionary.

        This handles nested dicts that come from model_dump().
        """
        for key, value in data.items():
            field_path = f"{path_prefix}.{key}"

            if isinstance(value, str):
                fields[field_path] = value
            elif isinstance(value, dict):
                # Recursively handle nested dicts
                self._extract_from_dict(value, field_path, fields)
            elif isinstance(value, list):
                # Handle lists of strings or dicts
                for idx, item in enumerate(value):
                    item_path = f"{field_path}[{idx}]"
                    if isinstance(item, str):
                        fields[item_path] = item
                    elif isinstance(item, dict):
                        self._extract_from_dict(item, item_path, fields)

    def _batch_protect(self, fields: dict[str, str]) -> tuple[dict[str, str], RedactionState]:
        """
        Protect multiple fields using batch detection.

        Returns protected field values and accumulated state.
        """
        # Detect PII in all fields with one call
        entities_by_field = self.batch_detector.detect_batch(fields)

        # Use entity tracker for consistent tokens
        tokens_by_field = self.entity_tracker.assign_tokens(entities_by_field)

        # Build redaction state and apply redactions
        protected_fields: dict[str, str] = {}
        accumulated_state = RedactionState()

        for field_path, field_value in fields.items():
            if field_path not in tokens_by_field:
                # No PII detected in this field
                protected_fields[field_path] = field_value
                continue

            # Apply redactions to this field
            redacted_text = field_value
            field_tokens = tokens_by_field[field_path]

            # Filter overlapping tokens before applying redactions
            # This prevents issues like EMAIL overlapping with URL parts
            filtered_tokens = self._filter_overlapping_tokens(field_tokens)

            # Sort tokens by position (reverse order for replacement)
            sorted_tokens = sorted(filtered_tokens, key=lambda t: t.entity.start, reverse=True)

            for token in sorted_tokens:
                # Replace in text
                redacted_text = redacted_text[: token.entity.start] + token.token + redacted_text[token.entity.end :]

                # Add to state
                accumulated_state = accumulated_state.with_token(token.token, token)

            protected_fields[field_path] = redacted_text

        return protected_fields, accumulated_state

    def _individual_protect(self, fields: dict[str, str]) -> tuple[dict[str, str], RedactionState]:
        """
        Protect fields individually (fallback when batch not available).

        Returns protected field values and accumulated state.
        """
        protected_fields: dict[str, str] = {}
        accumulated_state = RedactionState()

        for field_path, field_value in fields.items():
            # Redact this field
            redacted, field_state = self.redactyl.redact(field_value)
            protected_fields[field_path] = redacted

            # Merge state
            accumulated_state = accumulated_state.merge(field_state)

        return protected_fields, accumulated_state

    def _apply_protected_data[M: BaseModel](self, model: M, protected_data: dict[str, str], path_prefix: str = "") -> M:
        """
        Create a new model with protected data applied.

        This reconstructs the model with redacted values.
        """
        # Get current model data
        model_data = model.model_dump()

        # Apply protected values
        for field_path, protected_value in protected_data.items():
            # Remove prefix if present
            if path_prefix:
                field_path = field_path[len(path_prefix) + 1 :]

            # Parse the path and set the value
            self._set_nested_value(model_data, field_path, protected_value)

        # Create new model instance
        return model.__class__.model_validate(model_data)

    def _set_nested_value(self, data: dict[str, Any], path: str, value: str) -> None:
        """Set a value in nested dictionary using dot notation path."""
        # Handle array indices in path
        if "[" in path:
            # Split on array indices
            parts = path.split("[")
            base_path = parts[0]

            # Navigate to base
            if "." in base_path:
                keys = base_path.split(".")
                for key in keys[:-1]:
                    data = data[key]
                base_key = keys[-1]
            else:
                base_key = base_path

            # Handle array indices
            current = data[base_key]
            for part in parts[1:]:
                idx = int(part.split("]")[0])
                if part.endswith("]"):
                    # Final index
                    current[idx] = value
                else:
                    # More nesting after index
                    remaining = part.split("]")[1].lstrip(".")
                    if remaining:
                        self._set_nested_value(current[idx], remaining, value)
                    else:
                        current = current[idx]
        else:
            # Simple dot notation
            keys = path.split(".")
            for key in keys[:-1]:
                data = data[key]
            data[keys[-1]] = value

    def _filter_overlapping_tokens(self, tokens: list[RedactionToken]) -> list[RedactionToken]:
        """Filter overlapping tokens, preferring longer and more confident entities.

        This prevents issues like EMAIL overlapping with URL parts when processing
        entities like 'john.smith@example.com' which may be detected as both
        EMAIL and multiple URL fragments.
        """
        return filter_overlapping_tokens(tokens)

    # Container-aware helpers
    def protect_any(self, value: Any) -> tuple[Any, RedactionState]:
        """Protect any value, traversing containers if enabled."""
        if isinstance(value, BaseModel):
            return self.protect_model(value)
        if isinstance(value, str):
            # Redact raw strings directly
            redacted, state = self.redactyl.redact(value)
            return redacted, state
        if value is None:
            return value, RedactionState()
        if isinstance(value, Mapping):
            out: dict[Any, Any] = {}
            state = RedactionState()
            for k, v in value.items():
                new_v, st = self.protect_any(v)
                out[k] = new_v
                state = state.merge(st)
            # Return a plain dict to avoid constructing unknown Mapping types
            return out, state
        if isinstance(value, tuple):
            items: list[Any] = []
            state = RedactionState()
            for v in value:
                new_v, st = self.protect_any(v)
                items.append(new_v)
                state = state.merge(st)
            return tuple(items), state
        if isinstance(value, list):
            items: list[Any] = []
            state = RedactionState()
            for v in value:
                new_v, st = self.protect_any(v)
                items.append(new_v)
                state = state.merge(st)
            return items, state
        if isinstance(value, set):
            # Batch-protect pure string sets to avoid dedup from identical tokens
            if value and all(isinstance(v, str) for v in value):
                # Use a stable order for batch protection
                seq = sorted(value)
                fields = {f"item_{i}": s for i, s in enumerate(seq)}
                # Force batch-based protection to ensure distinct tokens
                protected_map, st = self._batch_protect(fields)
                protected_seq = [protected_map[f"item_{i}"] for i in range(len(seq))]
                return set(protected_seq), st
            # General recursive case for mixed types
            items_set: set[Any] = set()
            state = RedactionState()
            for v in value:
                new_v, st = self.protect_any(v)
                items_set.add(new_v)
                state = state.merge(st)
            return items_set, state
        if isinstance(value, frozenset):
            # Batch-protect pure string frozensets as well
            if value and all(isinstance(v, str) for v in value):
                seq = sorted(value)
                fields = {f"item_{i}": s for i, s in enumerate(seq)}
                protected_map, st = self._batch_protect(fields)
                protected_seq = [protected_map[f"item_{i}"] for i in range(len(seq))]
                return frozenset(protected_seq), st
            tmp: set[Any] = set()
            state = RedactionState()
            for v in value:
                new_v, st = self.protect_any(v)
                tmp.add(new_v)
                state = state.merge(st)
            return frozenset(tmp), state
        return value, RedactionState()

    def unprotect_any(self, value: Any, state: RedactionState) -> tuple[Any, list[UnredactionIssue]]:
        """Unprotect any value, traversing containers if enabled."""
        if isinstance(value, BaseModel):
            return self.unprotect_model(value, state)
        if isinstance(value, str):
            # Unredact raw strings using loop
            unred, issues = self.redactyl.unredact(value, state, fuzzy=self.fuzzy_unredaction)
            return unred, issues
        if value is None:
            return value, []
        issues: list[UnredactionIssue] = []
        if isinstance(value, Mapping):
            out: dict[Any, Any] = {}
            for k, v in value.items():
                new_v, isss = self.unprotect_any(v, state)
                out[k] = new_v
                issues.extend(isss)
            # Return a plain dict to avoid constructing unknown Mapping types
            return out, issues
        if isinstance(value, tuple):
            items: list[Any] = []
            for v in value:
                new_v, isss = self.unprotect_any(v, state)
                items.append(new_v)
                issues.extend(isss)
            return tuple(items), issues
        if isinstance(value, list):
            items: list[Any] = []
            for v in value:
                new_v, isss = self.unprotect_any(v, state)
                items.append(new_v)
                issues.extend(isss)
            return items, issues
        if isinstance(value, set):
            tmp: set[Any] = set()
            for v in value:
                new_v, isss = self.unprotect_any(v, state)
                tmp.add(new_v)
                issues.extend(isss)
            return tmp, issues
        if isinstance(value, frozenset):
            tmp: set[Any] = set()
            for v in value:
                new_v, isss = self.unprotect_any(v, state)
                tmp.add(new_v)
                issues.extend(isss)
            return frozenset(tmp), issues
        return value, issues

    def apply_replacements_to_any(self, data: Any, replacements: dict[str, str | None]) -> Any:
        """Apply token replacements to any data structure."""
        if isinstance(data, str):
            new_value = data
            for token, replacement in replacements.items():
                if replacement is not None and token in new_value:
                    new_value = new_value.replace(token, replacement)
            return new_value
        if isinstance(data, dict):
            return {k: self.apply_replacements_to_any(v, replacements) for k, v in data.items()}
        if isinstance(data, list):
            return [self.apply_replacements_to_any(v, replacements) for v in data]
        if isinstance(data, tuple):
            return tuple(self.apply_replacements_to_any(v, replacements) for v in data)
        if isinstance(data, set):
            return {self.apply_replacements_to_any(v, replacements) for v in data}
        if isinstance(data, frozenset):
            return frozenset(self.apply_replacements_to_any(v, replacements) for v in data)
        return data


# Export public API
__all__ = ["PIIConfig", "HallucinationAction", "HallucinationResponse", "HallucinationError", "UNSET", "UnsetType"]
