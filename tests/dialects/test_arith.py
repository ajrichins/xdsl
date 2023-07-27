from typing import TypeVar
import pytest

from xdsl.dialects.arith import (
    Addi,
    BinaryOperation,
    Constant,
    DivUI,
    DivSI,
    Subi,
    FloorDivSI,
    CeilDivSI,
    CeilDivUI,
    RemUI,
    RemSI,
    MinUI,
    MinSI,
    MaxUI,
    MaxSI,
    AndI,
    OrI,
    XOrI,
    ShLI,
    ShRUI,
    ShRSI,
    Cmpi,
    Addf,
    Subf,
    Mulf,
    Divf,
    Maxf,
    Minf,
    IndexCastOp,
    FPToSIOp,
    SIToFPOp,
    ExtFOp,
    TruncFOp,
    Cmpf,
    Negf,
    TruncIOp,
    ExtSIOp,
    ExtUIOp,
)
from xdsl.dialects.builtin import (
    i32,
    i64,
    f32,
    f64,
    IndexType,
    IntegerType,
)
from xdsl.ir import Attribute
from xdsl.utils.exceptions import VerifyException

_BinOpArgT = TypeVar("_BinOpArgT", bound=Attribute)


class Test_integer_arith_construction:
    operand_typ = i32
    a = Constant.from_int_and_width(1, operand_typ)
    b = Constant.from_int_and_width(1, operand_typ)

    @pytest.mark.parametrize(
        "OpClass",
        [
            Addi,
            Subi,
            DivUI,
            DivSI,
            FloorDivSI,
            CeilDivSI,
            CeilDivUI,
            RemUI,
            RemSI,
            MinUI,
            MinSI,
            MaxUI,
            MaxSI,
            AndI,
            OrI,
            XOrI,
            ShLI,
            ShRUI,
            ShRSI,
        ],
    )
    @pytest.mark.parametrize("return_typ", [None, operand_typ])
    def test_arith_ops_init(
        self,
        OpClass: type[BinaryOperation[_BinOpArgT]],
        return_typ: Attribute,
    ):
        op = OpClass(self.a, self.b)

        assert isinstance(op, OpClass)
        assert op.lhs.owner is self.a
        assert op.rhs.owner is self.b
        assert op.result.typ == self.operand_typ

    def test_Cmpi(self):
        _ = Cmpi.get(self.a, self.b, 2)

    @pytest.mark.parametrize(
        "input",
        ["eq", "ne", "slt", "sle", "ult", "ule", "ugt", "uge"],
    )
    def test_Cmpi_from_mnemonic(self, input: str):
        _ = Cmpi.get(self.a, self.b, input)


class Test_float_arith_construction:
    a = Constant.from_float_and_width(1.1, f32)
    b = Constant.from_float_and_width(2.2, f32)

    @pytest.mark.parametrize(
        "func",
        [Addf, Subf, Mulf, Divf, Maxf, Minf],
    )
    def test_arith_ops(self, func: type[BinaryOperation[_BinOpArgT]]):
        op = func(self.a, self.b)
        assert op.operands[0].owner is self.a
        assert op.operands[1].owner is self.b


def test_index_cast_op():
    a = Constant.from_int_and_width(0, 32)
    cast = IndexCastOp.get(a, IndexType())

    assert cast.result.typ == IndexType()
    assert cast.input.typ == i32
    assert cast.input.owner == a


def test_cast_fp_and_si_ops():
    a = Constant.from_int_and_width(0, 32)
    fp = SIToFPOp.get(a, f32)
    si = FPToSIOp.get(fp, i32)

    assert fp.input == a.result
    assert fp.result == si.input
    assert isinstance(si.result.typ, IntegerType)
    assert fp.result.typ == f32


def test_negf_op():
    a = Constant.from_float_and_width(1.0, f32)
    neg_a = Negf.get(a)

    b = Constant.from_float_and_width(1.0, f64)
    neg_b = Negf.get(b)

    assert neg_a.result.typ == f32
    assert neg_b.result.typ == f64


def test_extend_truncate_fpops():
    a = Constant.from_float_and_width(1.0, f32)
    b = Constant.from_float_and_width(2.0, f64)
    ext_op = ExtFOp.get(a, f64)
    trunc_op = TruncFOp.get(b, f32)

    assert ext_op.input == a.result
    assert ext_op.result.typ == f64
    assert trunc_op.input == b.result
    assert trunc_op.result.typ == f32


def test_cmpf_from_mnemonic():
    a = Constant.from_float_and_width(1.0, f64)
    b = Constant.from_float_and_width(2.0, f64)
    operations = [
        "false",
        "oeq",
        "ogt",
        "oge",
        "olt",
        "ole",
        "one",
        "ord",
        "ueq",
        "ugt",
        "uge",
        "ult",
        "ule",
        "une",
        "uno",
        "true",
    ]
    cmpf_ops = [Cmpf.get(a, b, operations[i]) for i in range(len(operations))]

    for index, op in enumerate(cmpf_ops):
        assert op.lhs.typ == f64
        assert op.rhs.typ == f64
        assert op.predicate.value.data == index


def test_cmpf_get():
    a = Constant.from_float_and_width(1.0, f32)
    b = Constant.from_float_and_width(2.0, f32)

    cmpf_op = Cmpf.get(a, b, 1)

    assert cmpf_op.lhs.typ == f32
    assert cmpf_op.rhs.typ == f32
    assert cmpf_op.predicate.value.data == 1


def test_cmpf_missmatch_type():
    a = Constant.from_float_and_width(1.0, f32)
    b = Constant.from_float_and_width(2.0, f64)

    with pytest.raises(TypeError) as e:
        _cmpf_op = Cmpf.get(a, b, 1)
    assert (
        e.value.args[0]
        == "Comparison operands must have same type, but provided f32 and f64"
    )


def test_cmpi_mismatch_type():
    a = Constant.from_int_and_width(1, i32)
    b = Constant.from_int_and_width(2, i64)

    with pytest.raises(TypeError) as e:
        _cmpi_op = Cmpi.get(a, b, 1)
    assert (
        e.value.args[0]
        == "Comparison operands must have same type, but provided i32 and i64"
    )


def test_cmpf_incorrect_comparison():
    a = Constant.from_float_and_width(1.0, f32)
    b = Constant.from_float_and_width(2.0, f32)

    with pytest.raises(VerifyException) as e:
        # 'eq' is a comparison op for cmpi but not cmpf
        _cmpf_op = Cmpf.get(a, b, "eq")
    assert e.value.args[0] == "Unknown comparison mnemonic: eq"


def test_cmpi_incorrect_comparison():
    a = Constant.from_int_and_width(1, i32)
    b = Constant.from_int_and_width(2, i32)

    with pytest.raises(VerifyException) as e:
        # 'oeq' is a comparison op for cmpf but not cmpi
        _cmpi_op = Cmpi.get(a, b, "oeq")
    assert e.value.args[0] == "Unknown comparison mnemonic: oeq"


def test_cmpi_index_type():
    a = Constant.from_int_and_width(1, IndexType())
    b = Constant.from_int_and_width(2, IndexType())

    Cmpi.get(a, b, "eq").verify()


def test_extend_truncate_iops():
    a = Constant.from_int_and_width(1, i32)
    b = Constant.from_int_and_width(2, i64)
    exts_op = ExtSIOp.get(a, i64)
    extu_op = ExtUIOp.get(a, i64)
    trunc_op = TruncIOp.get(b, i32)

    assert exts_op.input == a.result
    assert exts_op.result.typ == i64
    assert extu_op.input == a.result
    assert extu_op.result.typ == i64
    assert trunc_op.input == b.result
    assert trunc_op.result.typ == i32
