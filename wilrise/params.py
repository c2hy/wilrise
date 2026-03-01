"""Parameter metadata, validation, and dependency injection for JSON-RPC methods."""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin

# Provider may take 0 args or (Request,); return value is injected into the method parameter.
# Callable[..., ...] allows both () -> T and (Request) -> T for frameworks that pass request.
RequestProvider = Callable[..., Any | Awaitable[Any]]

T = TypeVar("T")

_BaseModel: type[Any] | None = None
_PydanticValidationError: type[Exception] | None = None

try:
    from pydantic import BaseModel as _BaseModel  # noqa: F811
    from pydantic import ValidationError as _PydanticValidationError  # noqa: F811
except ImportError:
    _BaseModel = None  # type: ignore[misc, assignment]
    _PydanticValidationError = None  # type: ignore[misc, assignment]

BaseModel = _BaseModel
PydanticValidationError = _PydanticValidationError


class ParamsValidationError(ValueError):
    """Raised when Pydantic parameter validation fails.

    Carries serializable validation errors for JSON-RPC error response.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__("Parameter validation failed")


# Sentinel to identify Use-injected parameters
USE_MARKER = object()


@dataclass
class Param:
    """FastAPI-style parameter metadata for JSON-RPC method arguments.

    Can be used as default value or inside Annotated:
      - a: int = Param(1, description="first number")
      - a: Annotated[int, Param(description="first number")]
    """

    default: Any = ...
    description: str = ""
    alias: str | None = None

    def __repr__(self) -> str:
        if self.default is ...:
            return f"Param(description={self.description!r}, alias={self.alias!r})"
        return f"Param(default={self.default!r}, description={self.description!r}, alias={self.alias!r})"


def get_param_meta(
    param: inspect.Parameter,
) -> tuple[Any, Param | None]:
    """Extract Param metadata from parameter annotation and default.

    Returns (effective_default, param_meta). Used by core and testing.
    """
    default = param.default if param.default is not inspect.Parameter.empty else ...
    meta: Param | None = None

    # Default value is a Param instance
    if isinstance(default, Param):
        meta = default
        default = meta.default if meta.default is not ... else ...
    # Annotation is Annotated[T, Param(...) | Use(...), ...]
    annotation = param.annotation
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        for a in args[1:]:
            if isinstance(a, Param):
                if meta is None:
                    meta = a
                else:
                    # Merge: Annotated Param supplies description/alias;
                    # default may come from default=
                    meta = Param(
                        default=meta.default if meta.default is not ... else a.default,
                        description=meta.description or a.description,
                        alias=meta.alias or a.alias,
                    )
                if meta.default is not ... and default is ...:
                    default = meta.default
            elif isinstance(a, _Use):
                # Use in Annotated: DI without default value (type-checker friendly)
                if default is ...:
                    default = a

    return default, meta


def _effective_annotation(annotation: Any) -> Any:
    """Unwrap Annotated to the first type for validation."""
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        return args[0] if args else annotation
    return annotation


# Used by core.py; pyright reports unused within this file.
# pyright: reportUnusedFunction=false
def _validate_param(
    annotation: Any,
    value: Any,
    param_name: str,
) -> Any:
    """Validate value with Pydantic when annotation is a BaseModel.

    When pydantic is not installed or annotation is not a model,
    returns value unchanged.
    Raises ParamsValidationError on validation failure.
    """
    if BaseModel is None or PydanticValidationError is None:
        return value
    effective = _effective_annotation(annotation)
    if not (isinstance(effective, type) and issubclass(effective, BaseModel)):
        return value
    try:
        return effective.model_validate(value)  # type: ignore[union-attr]
    except PydanticValidationError as e:
        raise ParamsValidationError(cast(list[dict[str, Any]], e.errors())) from e


def _provider_arity(provider: RequestProvider) -> int:
    """Number of parameters the provider accepts (0 or 1 for Request)."""
    try:
        return len(inspect.signature(provider).parameters)
    except (ValueError, TypeError):
        return 1  # e.g. C extension; assume (request,)


@dataclass
class _Use:
    """Internal: dependency injection marker. Use the Use() function instead."""

    provider: RequestProvider

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if _provider_arity(self.provider) == 0:
            return self.provider()
        return self.provider(*args, **kwargs)


def Use(provider: Callable[..., T | Awaitable[T]]) -> Any:
    """Dependency injection. Provider may take 0 args or (Request,); do not use for RPC params.

    Supports sync and async providers. Use Annotated[YourType, Use(provider)] so
    the parameter is typed as YourType (provider may return Generator[YourType] etc.).
    """
    return _Use(provider)
