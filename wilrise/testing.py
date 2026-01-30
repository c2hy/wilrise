"""Testing helpers. Use in tests only; not part of stable public API for app code."""

import inspect
from collections.abc import Callable
from typing import Any

from wilrise.params import Param
from wilrise.params import get_param_meta as get_param_meta_impl


def get_param_meta(fn: Callable[..., Any], param_name: str) -> tuple[Any, Param | None]:
    """Return (effective_default, param_meta) for a parameter of a callable.

    For use in tests that need to assert Param metadata. param_meta is None
    when the parameter has no Param annotation or default.
    """
    sig = inspect.signature(fn)
    param = sig.parameters[param_name]
    return get_param_meta_impl(param)
