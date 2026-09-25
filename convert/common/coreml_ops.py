"""Aliases for torch op names that coremltools' torch frontend lacks under that spelling."""

from __future__ import annotations

ALIASES = {
    "greater_equal": "ge",
    "less_equal": "le",
    "greater": "gt",
    "less": "lt",
    "logical_and": "logical_and",
    "not_equal": "ne",
}


def register_aliases() -> None:
    from coremltools.converters.mil.frontend.torch.torch_op_registry import _TORCH_OPS_REGISTRY as reg
    for alias, target in ALIASES.items():
        func = reg.get_func(target)
        if func is not None and reg.get_func(alias) is None:
            reg.set_func_by_name(func, alias)
