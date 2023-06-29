# type: ignore
from xdsl.ir import Dialect

from .base import (
    RISCV_CORE,
    AddiOp,
    AddOp,
    AndiOp,
    AndOp,
    AuipcOp,
    BeqOp,
    BgeOp,
    BgeuOp,
    BltOp,
    BltuOp,
    BneOp,
    CommentOp,
    CustomAssemblyInstructionOp,
    DivOp,
    DivuOp,
    EbreakOp,
    EcallOp,
    GetRegisterOp,
    JalOp,
    JalrOp,
    JOp,
    LbOp,
    LbuOp,
    LhOp,
    LhuOp,
    LiOp,
    LuiOp,
    LwOp,
    MulhOp,
    MulhsuOp,
    MulhuOp,
    MulOp,
    MVOp,
    NopOp,
    OriOp,
    OrOp,
    IntegerRegister,
    IntegerRegisters,
    IntegerRegisterType,
    RemOp,
    RemuOp,
    ReturnOp,
    SbOp,
    ScfgwOp,
    ShOp,
    SlliOp,
    SllOp,
    SltiOp,
    SltiuOp,
    SltOp,
    SltuOp,
    SraiOp,
    SraOp,
    SrliOp,
    SrlOp,
    SubOp,
    SwOp,
    WfiOp,
    XoriOp,
    XorOp,
)
from .core import (
    DirectiveOp,
    LabelOp,
    RISCVInstruction,
    RISCVOp,
    print_assembly,
    riscv_code,
)
from .F import (
    RISCV_F,
    FAddSOp,
    FClassSOp,
    FCvtSWOp,
    FCvtSWuOp,
    FCvtWSOp,
    FCvtWuSOp,
    FDivSOp,
    FeqSOP,
    FleSOP,
    FloatRegister,
    FloatRegisters,
    FloatRegisterType,
    FltSOP,
    FLwOp,
    FMAddSOp,
    FMaxSOp,
    FMinSOp,
    FMSubSOp,
    FMulSOp,
    FMvWXOp,
    FMvXWOp,
    FNMAddSOp,
    FNMSubSOp,
    FSgnJNSOp,
    FSgnJSOp,
    FSgnJXSOp,
    FSqrtSOp,
    FSubSOp,
    FSwOp,
)
from .Zicsr import (
    RISCV_ZICSR,
    CsrrciOp,
    CsrrcOp,
    CsrrsiOp,
    CsrrsOp,
    CsrrwiOp,
    CsrrwOp,
)

RISCV = Dialect(
    [*RISCV_CORE.operations, *RISCV_ZICSR.operations, *RISCV_F.operations],
    [*RISCV_CORE.attributes, *RISCV_ZICSR.attributes, *RISCV_F.attributes],
)
