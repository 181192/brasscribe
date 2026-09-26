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
    _patch_scalar_cast()


def _patch_scalar_cast() -> None:
    """aten::Int/Bool on a folded length-1 array: NumPy 2 refuses int(array([n])), so use .item().

    Traced einops rearranges produce these (shape products computed as tensors).
    """
    import numpy as np
    from coremltools.converters.mil.frontend.torch import ops

    if getattr(ops._cast, "_scalar_patch", False):
        return
    original = ops._cast

    def _cast(context, node, dtype, dtype_name):
        x = ops._get_inputs(context, node, expected=1)[0]
        if x.can_be_folded_to_const() and isinstance(x.val, np.ndarray) and x.val.size == 1:
            from coremltools.converters.mil import Builder as mb
            context.add(mb.const(val=dtype(x.val.item()), name=node.name), node.name)
            return
        original(context, node, dtype, dtype_name)

    _cast._scalar_patch = True
    ops._cast = _cast
