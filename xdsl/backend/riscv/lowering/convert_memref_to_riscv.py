from collections.abc import Sequence
from typing import Any, cast

from xdsl.backend.riscv.lowering.utils import (
    cast_operands_to_regs,
    register_type_for_type,
)
from xdsl.dialects import memref, riscv
from xdsl.dialects.builtin import (
    Float32Type,
    IntegerType,
    ModuleOp,
    UnrealizedConversionCastOp,
)
from xdsl.ir import MLContext, Operation, SSAValue
from xdsl.ir.core import Attribute
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import (
    GreedyRewritePatternApplier,
    PatternRewriter,
    PatternRewriteWalker,
    RewritePattern,
    op_type_rewrite_pattern,
)
from xdsl.utils.exceptions import DiagnosticException


class ConvertMemrefAllocOp(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: memref.Alloc, rewriter: PatternRewriter) -> None:
        raise DiagnosticException("Lowering memref.alloc not implemented yet")


class ConvertMemrefDeallocOp(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: memref.Dealloc, rewriter: PatternRewriter) -> None:
        raise DiagnosticException("Lowering memref.dealloc not implemented yet")


def memref_shape_ops(
    mem: SSAValue,
    indices: Sequence[SSAValue],
    shape: Sequence[int],
    element_type: Attribute,
) -> tuple[list[Operation], SSAValue]:
    """
    Returns ssa value representing pointer into the memref at given indices.
    The pointer is byte-indexed, and the indices are strided by element size, so the index
    into the flat memory buffer needs to be multiplied by the size of the element.
    """

    assert len(shape) == len(indices)

    # Only handle a small subset of elements
    # Might be useful as a helper for other passes in the future
    match element_type:
        case IntegerType():
            bitwidth = element_type.width.data
            if bitwidth != 32:
                raise DiagnosticException(
                    f"Unsupported memref element type for riscv lowering: {element_type}"
                )
            bytes_per_element = element_type.width.data // 8
        case Float32Type():
            bytes_per_element = 4
        case _:
            raise DiagnosticException(
                f"Unsupported memref element type for riscv lowering: {element_type}"
            )

    ops: list[Operation] = []

    match indices:
        case [offset_in_elements]:
            pass
        case [idx1, idx2]:
            ops = [
                cols := riscv.LiOp(shape[1]),
                row_offset := riscv.MulOp(cols, idx1),
                offset := riscv.AddOp(row_offset, idx2),
            ]
            offset_in_elements = offset.rd
        case _:
            raise DiagnosticException(
                f"Unsupported memref shape {shape}, only support 1D and 2D memrefs."
            )

    ops.extend(
        [
            bytes_per_element_op := riscv.LiOp(bytes_per_element),
            offset_bytes := riscv.MulOp(
                offset_in_elements,
                bytes_per_element_op.rd,
                comment="multiply by element size",
            ),
            ptr := riscv.AddOp(mem, offset_bytes),
        ]
    )

    return ops, ptr.rd


class ConvertMemrefStoreOp(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: memref.Store, rewriter: PatternRewriter):
        value, mem, *indices = cast_operands_to_regs(rewriter)

        assert isinstance(op.memref.type, memref.MemRefType)
        memref_type = cast(memref.MemRefType[Any], op.memref.type)
        shape = memref_type.get_shape()

        ops, ptr = memref_shape_ops(mem, indices, shape, memref_type.element_type)

        rewriter.insert_op_before_matched_op(ops)
        if isinstance(value.type, riscv.IntRegisterType):
            new_op = riscv.SwOp(
                ptr, value, 0, comment=f"store int value to memref of shape {shape}"
            )
        else:
            new_op = riscv.FSwOp(
                ptr, value, 0, comment=f"store float value to memref of shape {shape}"
            )
        rewriter.replace_matched_op(new_op)


class ConvertMemrefLoadOp(RewritePattern):
    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: memref.Load, rewriter: PatternRewriter):
        mem, *indices = cast_operands_to_regs(rewriter)

        assert isinstance(op.memref.type, memref.MemRefType)
        memref_type = cast(memref.MemRefType[Any], op.memref.type)
        shape = memref_type.get_shape()
        ops, ptr = memref_shape_ops(mem, indices, shape, memref_type.element_type)
        rewriter.insert_op_before_matched_op(ops)

        result_register_type = register_type_for_type(op.res.type)

        if result_register_type is riscv.IntRegisterType:
            lw_op = riscv.LwOp(
                ptr, 0, comment=f"load value from memref of shape {shape}"
            )
        else:
            lw_op = riscv.FLwOp(
                ptr, 0, comment=f"load value from memref of shape {shape}"
            )

        rewriter.replace_matched_op(
            [
                lw := lw_op,
                UnrealizedConversionCastOp.get(lw.results, (op.res.type,)),
            ],
        )


class ConvertMemrefToRiscvPass(ModulePass):
    name = "convert-memref-to-riscv"

    def apply(self, ctx: MLContext, op: ModuleOp) -> None:
        PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    ConvertMemrefAllocOp(),
                    ConvertMemrefDeallocOp(),
                    ConvertMemrefStoreOp(),
                    ConvertMemrefLoadOp(),
                ]
            )
        ).rewrite_module(op)
