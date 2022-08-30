from __future__ import annotations
from abc import ABC
from typing import Iterable, Sequence, SupportsIndex, Type, TypeGuard, Any
from xdsl.ir import *
from xdsl.dialects.builtin import *
from xdsl.dialects.arith import *
from xdsl.dialects.rewrite.dialect import RewriteId

_T = TypeVar('_T')


# We have to inherit from the actual List class to get easier Pattern Matching
# That is not possible when inheriting from UserList or FrozenList
class IList(List[_T]):
    _frozen: bool = False

    def freeze(self):
        self._frozen = True

    def append(self, __object: _T) -> None:
        if self._frozen:
            raise Exception("frozen list can not be modified")
        return super().append(__object)

    def extend(self, __iterable: Iterable[_T]) -> None:
        if self._frozen:
            raise Exception("frozen list can not be modified")
        return super().extend(__iterable)

    def insert(self, __index: SupportsIndex, __object: _T) -> None:
        if self._frozen:
            raise Exception("frozen list can not be modified")
        return super().insert(__index, __object)

    def remove(self, __value: _T) -> None:
        if self._frozen:
            raise Exception("frozen list can not be modified")
        return super().remove(__value)

    def pop(self, __index: SupportsIndex = ...) -> _T:
        if self._frozen:
            raise Exception("frozen list can not be modified")
        return super().pop(__index)

    def clear(self) -> None:
        if self._frozen:
            raise Exception("frozen list can not be modified")
        return super().clear()


@dataclass(frozen=True)
class ISSAValue(ABC):
    typ: Attribute


@dataclass(frozen=True)
class IResult(ISSAValue):
    op: IOp
    result_index: int

    def __hash__(self) -> int:
        return hash(id(self.op)) + hash(self.result_index)

    def __eq__(self, __o: IResult) -> bool:
        if isinstance(__o, IResult):
            return self.op == __o.op and self.result_index == __o.result_index
        return False


@dataclass(frozen=True)
class IBlockArg(ISSAValue):
    block: IBlock
    index: int

    def __hash__(self) -> int:
        return hash(id(self))

    def __eq__(self, __o: IBlockArg) -> bool:
        return self is __o

    def __str__(self) -> str:
        return "BlockArg(type:" + self.typ.name + (
            "attached" if self.block is not None else "unattached") + ")"

    def __repr__(self) -> str:
        return "BlockArg(type:" + self.typ.name + (
            "attached" if self.block is not None else "unattached") + ")"


@dataclass(frozen=True)
class IRegion:
    blocks: IList[IBlock]

    def __hash__(self) -> int:
        return hash(id(self))

    def __eq__(self, __o: IRegion) -> bool:
        return self is __o

    @property
    def block(self) -> Optional[IBlock]:
        if len(self.blocks) > 0:
            return self.blocks[0]
        return None

    @property
    def ops(self) -> IList[IOp]:
        if self.block is not None:
            return self.block.ops
        else:
            return IList()

    def __init__(self, blocks: Sequence[IBlock]):
        """Creates a new mutable region and returns an immutable view on it."""
        object.__setattr__(self, "blocks", IList(blocks))
        self.blocks.freeze()

    @classmethod
    def from_mutable(
        cls,
        blocks: Sequence[Block],
        value_map: Optional[dict[SSAValue, ISSAValue]] = None,
        block_map: Optional[dict[Block, IBlock]] = None,
    ) -> IRegion:
        if value_map is None:
            value_map = {}
        if block_map is None:
            block_map = {}
        immutable_blocks = [
            IBlock.from_mutable(block, value_map, block_map)
            for block in blocks
        ]
        assert (blocks[0].parent is not None)
        return IRegion(immutable_blocks)

    def get_mutable_copy(
            self,
            value_mapping: Optional[dict[ISSAValue, SSAValue]] = None,
            block_mapping: Optional[dict[IBlock, Block]] = None) -> Region:
        if value_mapping is None:
            value_mapping = {}
        if block_mapping is None:
            block_mapping = {}
        mutable_blocks: List[Block] = []
        for block in self.blocks:
            mutable_blocks.append(
                block.get_mutable_copy(value_mapping=value_mapping,
                                       block_mapping=block_mapping))
        return Region.from_block_list(mutable_blocks)

    def walk(self, fun: Callable[[IOp], None]) -> None:
        for block in self.blocks:
            block.walk(fun)

    def walk_abortable(self, fun: Callable[[IOp], bool]) -> bool:
        """
        Walks all blocks and ops inside this region. 
        Aborts the walk if fun returns False.
        """
        for block in self.blocks:
            if not block.walk_abortable(fun):
                return False
        return True

    def value_used_inside(self, value: ISSAValue) -> bool:
        use_found = False
        def check_used(op: IOp) -> bool:
            if value in op.operands:
                nonlocal use_found
                use_found = True
                # abort walk
                return False
            return True
        self.walk_abortable(check_used)
        return use_found

@dataclass(frozen=True)
class IBlock:
    args: IList[IBlockArg]
    ops: IList[IOp]

    @property
    def arg_types(self) -> List[Attribute]:
        frozen_arg_types = [arg.typ for arg in self.args]
        return frozen_arg_types

    def __hash__(self) -> int:
        return (id(self))

    def __eq__(self, __o: IBlock) -> bool:
        return self is __o

    def __str__(self) -> str:
        return "block of" + str(len(self.ops)) + " with args: " + str(
            self.args)

    def __repr__(self) -> str:
        return "block of" + str(len(self.ops)) + " with args: " + str(
            self.args)

    def __post_init__(self):
        for arg in self.args:
            object.__setattr__(arg, "block", self)

    def __init__(self, args: Sequence[Attribute] | Sequence[IBlockArg],
                 ops: Sequence[IOp]):
        """Creates a new immutable block."""

        # Type Guards:
        def is_iblock_arg_seq(
                list: Sequence[Any]) -> TypeGuard[Sequence[IBlockArg]]:
            if len(list) == 0:
                return False
            return all([isinstance(elem, IBlockArg) for elem in list])

        def is_type_seq(list: Sequence[Any]) -> TypeGuard[Sequence[Attribute]]:
            return all([isinstance(elem, Attribute) for elem in list])

        if is_type_seq(args):
            block_args: List[IBlockArg] = [
                IBlockArg(type, self, idx) for idx, type in enumerate(args)
            ]
        elif is_iblock_arg_seq(args):
            block_args: List[IBlockArg] = args
            for block_arg in block_args:
                object.__setattr__(block_arg, "block", self)
        else:
            raise Exception("args for IBlock ill structured")

        object.__setattr__(self, "args", IList(block_args))
        object.__setattr__(self, "ops", IList(ops))

        self.args.freeze()
        self.ops.freeze()

    @classmethod
    def from_iblock(cls,
                    ops: Sequence[IOp],
                    old_block: IBlock,
                    env: Optional[dict[ISSAValue, ISSAValue]] = None):
        """Creates a new immutable block to replace an existing immutable block, e.g.
        in the context of rewriting. The number and types of block args are retained 
        and all references to block args of the old block will be updated to the new block

        env --  records updated results and block args of newly created ops/blocks in this 
                process to be used by dependant ops.
        """

        if env is None:
            env = {}

        block_args: List[IBlockArg] = []
        for idx, old_arg in enumerate(old_block.args):
            # The IBlock that will house this IBlockArg is not constructed yet.
            # After construction the block field will be set by the IBlock.
            block_args.append(new_block_arg := IBlockArg(
                old_arg.typ,
                None,  # type: ignore
                idx))
            env[old_arg] = new_block_arg

        # Some of the operations in ops might refer to the block args of old_block
        # In that case it is necessary to substitute these references with the new
        # block args of this block. This is achieved by rebuilding the ops if necessary
        def substitute_if_required(op: IOp) -> IOp:
            substitution_required = False
            # rebuild specific regions of this op if necessary
            new_regions: List[IRegion] = []
            for region in op.regions:
                region_substitution_required = False
                new_blocks: List[IBlock] = []
                for block in region.blocks:
                    # check whether rebuilding is necessary on the level of
                    # individual blocks so the region can reuse unchanged blocks
                    block_substitution_required = False

                    def subst_necessary(op: IOp):
                        for operand in op.operands:
                            if operand in env:
                                nonlocal block_substitution_required
                                block_substitution_required = True

                    # walk all operations nested in this block (and deeper)
                    block.walk(subst_necessary)

                    if block_substitution_required:
                        substitution_required = True
                        region_substitution_required = True
                        # This rebuilds the block and does substitution for all nested ops
                        new_block = IBlock.from_iblock(ops=block.ops,
                                                       old_block=block,
                                                       env=env)
                        new_blocks.append(new_block)
                    else:
                        new_blocks.append(block)
                if region_substitution_required:
                    new_regions.append(IRegion(new_blocks))
                else:
                    new_regions.append(region)

            # update operands of this op if the corresponding op has been rebuilt
            # or in case it is a block_arg, if we have an updated block_arg
            new_operands: List[ISSAValue | IOp | List[IOp]] = []
            for operand in op.operands:
                if operand in env:
                    new_operands.append(env[operand])
                    substitution_required = True
                else:
                    new_operands.append(operand)

            # If any updates to this op are required we rebuild it
            if substitution_required:
                substituted_op = from_op(op,
                                         operands=new_operands,
                                         regions=new_regions,
                                         env=env)
                assert len(substituted_op) == 1
                return substituted_op[-1]
            return op

        ops = [substitute_if_required(op) for op in ops]

        return cls(args=block_args, ops=ops)

    @classmethod
    def from_mutable(
        cls,
        block: Block,
        value_map: Optional[dict[SSAValue, ISSAValue]] = None,
        block_map: Optional[dict[Block, IBlock]] = None,
    ) -> IBlock:
        if value_map is None:
            value_map = {}
        if block_map is None:
            block_map = {}

        args: List[IBlockArg] = []
        for arg in block.args:
            # The IBlock that will house this IBlockArg is not constructed yet.
            # After construction the block field will be set by the IBlock.
            immutable_arg = IBlockArg(arg.typ, None, arg.index)  # type: ignore
            args.append(immutable_arg)
            value_map[arg] = immutable_arg

        immutable_ops = [
            IOp.from_mutable(op, value_map=value_map, block_map=block_map)
            for op in block.ops
        ]

        return IBlock(args, immutable_ops)

    def get_mutable_copy(
            self,
            value_mapping: Optional[dict[ISSAValue, SSAValue]] = None,
            block_mapping: Optional[dict[IBlock, Block]] = None) -> Block:
        if value_mapping is None:
            value_mapping = {}
        if block_mapping is None:
            block_mapping = {}

        new_block = Block.from_arg_types(self.arg_types)
        for idx, arg in enumerate(self.args):
            value_mapping[arg] = new_block.args[idx]
        block_mapping[self] = new_block

        for immutable_op in self.ops:
            new_block.add_op(
                immutable_op.get_mutable_copy(value_mapping=value_mapping,
                                              block_mapping=block_mapping))
        return new_block

    def walk(self, fun: Callable[[IOp], None]) -> None:
        for op in self.ops:
            op.walk(fun)

    def walk_abortable(self, fun: Callable[[IOp], bool]) -> bool:
        for op in self.ops:
            if not op.walk_abortable(fun):
                return False
        return True

def get_immutable_copy(op: Operation) -> IOp:
    return IOp.from_mutable(op, {})


@dataclass(frozen=True)
class OpData:
    """
    These fields are split off from IOp to its own class because they are
    often preserved during rewriting. A new operation of the same type, e.g.
    with changed operands can still use the same OpData instance. This design
    increases sharing in the IR.
    """
    name: str
    op_type: type[Operation]
    attributes: dict[str, Attribute]


@dataclass(frozen=True)
class IOp:
    __match_args__ = ("op_type", "operands", "results", "successors",
                      "regions")
    _op_data: OpData
    operands: IList[ISSAValue]
    results: IList[IResult]
    successors: IList[IBlock]
    regions: IList[IRegion]

    def __init__(self, op_data: OpData, operands: Sequence[ISSAValue],
                 result_types: Sequence[Attribute],
                 successors: Sequence[IBlock],
                 regions: Sequence[IRegion]) -> None:
        object.__setattr__(self, "_op_data", op_data)
        object.__setattr__(self, "operands", IList(operands))
        object.__setattr__(
            self, "results",
            IList([
                IResult(type, self, idx)
                for idx, type in enumerate(result_types)
            ]))
        object.__setattr__(self, "successors", IList(successors))
        object.__setattr__(self, "regions", IList(regions))

        self.operands.freeze()
        self.results.freeze()
        self.successors.freeze()
        self.regions.freeze()

    @classmethod
    def get(cls, name: str, op_type: type[Operation],
            operands: Sequence[ISSAValue], result_types: Sequence[Attribute],
            attributes: dict[str, Attribute], successors: Sequence[IBlock],
            regions: Sequence[IRegion]) -> IOp:
        return cls(OpData(name, op_type, attributes), operands, result_types,
                   successors, regions)

    def __hash__(self) -> int:
        return hash(id(self))

    def __eq__(self, __o: IOp) -> bool:
        return self is __o

    @property
    def name(self) -> str:
        return self._op_data.name

    @property
    def op_type(self) -> Type[Operation]:
        return self._op_data.op_type

    @property
    def attributes(self) -> dict[str, Attribute]:
        return self._op_data.attributes

    @property
    def result(self) -> IResult | None:
        if len(self.results) > 0:
            return self.results[0]
        return None

    @property
    def region(self) -> IRegion | None:
        if len(self.regions) > 0:
            return self.regions[0]
        return None

    @property
    def result_types(self) -> List[Attribute]:
        return [result.typ for result in self.results]

    def get_mutable_copy(
            self,
            value_mapping: Optional[dict[ISSAValue, SSAValue]] = None,
            block_mapping: Optional[dict[IBlock, Block]] = None) -> Operation:
        if value_mapping is None:
            value_mapping = {}
        if block_mapping is None:
            block_mapping = {}

        mutable_operands: List[SSAValue] = []
        for operand in self.operands:
            if operand in value_mapping:
                mutable_operands.append(value_mapping[operand])
            else:
                print(f"ERROR: op {self.name} uses SSAValue before definition")
                # Continuing to enable printing the IR including missing
                # operands for investigation
                mutable_operands.append(
                    OpResult(
                        operand.typ,
                        None,  # type: ignore
                        0))

        mutable_successors: List[Block] = []
        for successor in self.successors:
            if successor in block_mapping:
                mutable_successors.append(block_mapping[successor])
            else:
                raise Exception("Block used before definition")

        mutable_regions: List[Region] = []
        for region in self.regions:
            mutable_regions.append(
                region.get_mutable_copy(value_mapping=value_mapping,
                                        block_mapping=block_mapping))

        new_op: Operation = self.op_type.create(
            operands=mutable_operands,
            result_types=[result.typ for result in self.results],
            attributes=self.attributes.copy(),
            successors=mutable_successors,
            regions=mutable_regions)

        for idx, result in enumerate(self.results):
            m_result = new_op.results[idx]
            value_mapping[result] = m_result

        return new_op

    @classmethod
    def from_mutable(
            cls,
            op: Operation,
            value_map: Optional[dict[SSAValue, ISSAValue]] = None,
            block_map: Optional[dict[Block, IBlock]] = None,
            existing_operands: Optional[Sequence[ISSAValue]] = None) -> IOp:
        """creates an immutable view on an existing mutable op and all nested regions"""
        assert isinstance(op, Operation)
        op_type = op.__class__

        if value_map is None:
            value_map = {}
        if block_map is None:
            block_map = {}

        operands: List[ISSAValue] = []
        if existing_operands is None:
            for operand in op.operands:
                match operand:
                    case OpResult():
                        operands.append(
                            IResult(
                                operand.typ,
                                value_map[operand].op  # type: ignore
                                if operand in value_map else IOp.from_mutable(
                                    operand.op),
                                operand.result_index))
                    case BlockArgument():
                        if operand not in value_map:
                            raise Exception(
                                "Block argument expected in mapping for op: " +
                                op.name)
                        operands.append(value_map[operand])
                    case _:
                        raise Exception(
                            "Operand is expected to be either OpResult or BlockArgument"
                        )
        else:
            operands.extend(existing_operands)

        attributes: dict[str, Attribute] = op.attributes.copy()

        successors: List[IBlock] = []
        for successor in op.successors:
            if successor in block_map:
                successors.append(block_map[successor])
            else:
                # TODO: I think this is not right, build tests with successors
                newImmutableSuccessor = IBlock.from_mutable(successor)
                block_map[successor] = newImmutableSuccessor
                successors.append(newImmutableSuccessor)

        regions: List[IRegion] = []
        for region in op.regions:
            regions.append(
                IRegion.from_mutable(region.blocks, value_map, block_map))

        immutable_op = IOp.get(op.name, op_type, operands,
                               [result.typ for result in op.results],
                               attributes, successors, regions)

        for idx, result in enumerate(op.results):
            value_map[result] = immutable_op.results[idx]

        return immutable_op

    def get_attribute(self, name: str) -> Attribute:
        return self.attributes[name]

    def get_attributes_copy(self) -> dict[str, Attribute]:
        return self.attributes.copy()

    def walk(self, fun: Callable[[IOp], None]) -> None:
        fun(self)
        for region in self.regions:
            region.walk(fun)

    def walk_abortable(self, fun: Callable[[IOp], bool]) -> bool:
        if not fun(self):
            return False
        for region in self.regions:
            if not region.walk_abortable(fun):
                return False
        return True

def new_op(op_type: type[Operation],
           operands: Optional[Sequence[ISSAValue | IOp
                                       | Sequence[IOp]]] = None,
           result_types: Optional[Sequence[Attribute]] = None,
           attributes: Optional[dict[str, Attribute]] = None,
           successors: Optional[Sequence[IBlock]] = None,
           regions: Optional[Sequence[IRegion]] = None) -> List[IOp]:
    """Creates a new operation with the specified arguments. 
    Returns a list of all created IOps in the current nesting of calls 
    to `new_op` and `from_op` with this new IOp last.
    """
    if operands is None:
        operands = []
    if result_types is None:
        result_types = []
    if attributes is None:
        attributes = {}
    if successors is None:
        successors = []
    if regions is None:
        regions = []

    (new_operands, rewritten_ops) = _unpack_operands(operands)

    op = IOp.get(op_type.name, op_type, new_operands, result_types, attributes,
                 successors, regions)
    rewritten_ops.append(op)
    return rewritten_ops


def from_op(old_op: IOp,
            operands: Optional[Sequence[ISSAValue | IOp
                                        | Sequence[IOp]]] = None,
            result_types: Optional[Sequence[Attribute]] = None,
            attributes: Optional[dict[str, Attribute]] = None,
            successors: Optional[Sequence[IBlock]] = None,
            regions: Optional[Sequence[IRegion]] = None,
            env: Optional[dict[ISSAValue, ISSAValue]] = None) -> List[IOp]:
    """Creates a new operation by assuming all fields of `old_op`, apart from 
    those specified via the arguments. Returns a list of all created IOps in
    the current nesting of calls to `new_op` and `from_op` with this new IOp
    last.
    If `env` is specified all operands will be updated if they are included in
    the mapping and a mapping of all results of `old_op` to this op will be added  
    """
    if operands is None:
        operands = list(old_op.operands)
    if result_types is None:
        result_types = list(old_op.result_types)
    if successors is None:
        successors = list(old_op.successors)
    if regions is None:
        regions = list(old_op.regions)

    (new_operands, rewritten_ops) = _unpack_operands(operands, env)
    if attributes is None:
        op = IOp(
            old_op._op_data,  # type: ignore
            new_operands,
            result_types,
            successors,
            regions)
    else:
        op = IOp.get(old_op.name, old_op.op_type, new_operands, result_types,
                     attributes, successors, regions)
    rewritten_ops.append(op)
    if env is not None:
        # env not None means this is used in the context a remapping of values,
        # e.g. of a Block rebuilding.
        # As other operations depending on this op might have to be updated as
        # well, we have to add a mapping to the new results of this op to env.
        for idx, result in enumerate(op.results):
            env[old_op.results[idx]] = result
    return rewritten_ops


def _unpack_operands(
    operands: Sequence[ISSAValue | IOp | Sequence[IOp]],
    env: Optional[dict[ISSAValue, ISSAValue]] = None
) -> tuple[list[ISSAValue], list[IOp]]:
    """Maps all structures supplied in `operands` to a corresponding
    ISSAValue to be used as operand for constructing an IOp. 
    This facilitates nesting of calls to `new_op` and `from_op`
    If the ISSAValue has a mapping in `env` it is updated.
    Returns the formerly newly created IOps as well (`rewritten_ops`).
    """
    if env is None:
        env = {}
    unpacked_operands: list[ISSAValue] = []
    rewritten_ops: list[IOp] = []
    for operand in operands:
        if isinstance(operand, IOp):
            assert operand.result is not None
            operand = operand.result
        if isinstance(ops := operand, list):
            assert ops[-1].result is not None
            # avoid adding duplicates to rewritten ops
            for op in reversed(ops):
                if op in rewritten_ops:
                    # We don't want duplicates, but we have to remove the
                    # posterior instance and insert at the beginning
                    # or we get dead references
                    rewritten_ops.remove(op)
                rewritten_ops = [op] + rewritten_ops
            operand = ops[-1].result
        assert isinstance(operand, ISSAValue)
        if operand in env:
            operand = env[operand]
        assert not isinstance(operand, list)
        if isinstance(operand, IResult) and operand.op.op_type == RewriteId:
            operand = operand.op.operands[-1]
        unpacked_operands.append(operand)
    return (unpacked_operands, rewritten_ops)