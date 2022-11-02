import ast
from ctypes import cast
import logging

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type
from xdsl.dialects import builtin, cf, func, symref, arith, affine
from xdsl.frontend.visitors.new.type_hints import TypeHintToXDSL
from xdsl.frontend.visitors.new.xdsl_program import XDSLProgram
from xdsl.ir import Attribute, Data, Operation, Block, SSAValue, Region
from xdsl.printer import Printer


@dataclass
class VisitorException(Exception):
    """
    Exception type if there is an error while visiting a node.
    """
    msg: str

    def __str__(self) -> str:
        return f"Exception in AST visitor: {self.msg}."


class ASTToXDSL(ast.NodeVisitor):
    """Translates Python-like frontend AST into xDSL."""

    def __init__(self, imports: Dict[str, Any], program: XDSLProgram, logger: Optional[logging.RootLogger] = None):
        # Initialize type hint converter. We pass imports to get map the type hint name
        # to actual instance.
        self.hint_converter = TypeHintToXDSL(imports)
        self.symbol_table = Dict[str, Attribute]
        
        # Set logging.
        if not logger:
            logger = logging.getLogger("ast_to_xdsl_logger")
            logger.setLevel(logging.INFO)
        self.logger = logger

        # Dont' forget to set the program as well: we will use it to add new operations, blocks, regions.
        self.program = program
    
    def visit(self, node: ast.AST):
        return super().visit(node)

    def generic_visit(self, node: ast.AST):
        raise VisitorException(f"visitor for node {node} does not exist")

    def _cast(self, dst_ty: Attribute, value_ty: Attribute, value: Operation):
        if isinstance(dst_ty, builtin.IntegerType):
            if isinstance(value_ty, builtin.IntegerType):
                dst_width = dst_ty.width.data
                value_width = value_ty.width.data

                # Sanity check
                if value_width == dst_width:
                    return value
                
                raise VisitorException(f"cannot cast {value_ty} to {dst_ty} because there are no casts in arith dialect")
                #self.program.insert_op(cast_op)
                #return self.program.stack.pop()
        raise VisitorException(f"cannot cast {value_ty} to {dst_ty}")

    def visit_AnnAssign(self, node: ast.AnnAssign):
        """
        Visits type-annotated assignment operation, e.g.
        
        a: i32 = 3
        """
        # First, find the type of the LHS based on the type hint and create a new
        # symref declaration.
        lhs_ty = self.hint_converter.convert_hint(node.annotation)
        declare_op = symref.Declare.get(node.target.id)
        self.program.insert_op(declare_op)

        # Make sure the symbol table knows the type information. For now we only allow
        # referring to the symbols within the function, but in future that should change!
        # TODO: fix symbol table.
        self.symbol_table[node.target.id] = lhs_ty

        # Also, smake sure that we know what type the RHS expression should have.
        self.program.inferred_type = lhs_ty

        # Next visit RHS and get the value of that expression and its type.
        self.visit(node.value)
        rhs = self.program.stack.pop()
        rhs_ty = rhs.typ

        # Now, it can be that RHS already used the LHS type, e.g. when visiting
        # a: i32 = 0, constant visitor used the type inferred from the type hint
        # to create 0 constant. ALternatively, it can happen that the type of LHS was
        # not used! For example, if we have x: i32 = 0; y: i64 = x, the type of x
        # is i32 instead of i64, so we must do the type cobersion.
        if lhs_ty != rhs_ty:
            rhs = self._cast(lhs_ty, rhs_ty, rhs)
        
        update_op = symref.Update.get(node.target.id, rhs)
        self.program.insert_op(update_op)
        self.program.inferred_type = None

    def visit_Assign(self, node: ast.Assign):
        """
        Visits assignment operation, e.g.
        
        a = 3
        """
        lhs_ty = self.symbol_table[node.targets[0].id]
        self.program.inferred_type = lhs_ty

        # Get the rhs first.
        self.visit(node.value)
        rhs = self.program.stack.pop()
        rhs_ty = rhs.typ
        
        if lhs_ty != rhs_ty:
            rhs = self._cast(lhs_ty, rhs_ty, rhs)

        update_op = symref.Update.get(node.targets[0].id, rhs)
        self.program.insert_op(update_op)
        self.program.inferred_type = None

    def visit_BinOp(self, node: ast.BinOp):
        """
        Visits a binary operation.
        """
        self.visit(node.right)
        rhs = self.program.stack.pop()
        self.visit(node.left)
        lhs = self.program.stack.pop()

        # Check if types match.
        if lhs.typ != rhs.typ:
            # If not, it can happen that we should cast either LHS or RHS types. For
            # that, try to reuse the inferred type.
            if self.program.inferred_type is None:
                raise VisitorException(f"types of lhs ({lhs.typ}) and rhs ({rhs.typ}) do not match for binary operator {node.op.__class__.__name__} and cannot be inferred")
            if self.program.inferred_type == lhs.typ:
                rhs = self._cast(lhs.typ, rhs.typ, rhs)
            elif self.program.inferred_type == rhs.typ:
                lhs = self._cast(rhs.typ, lhs.typ, lhs)
            else:
                raise VisitorException(f"types of lhs ({lhs.typ}) and rhs ({rhs.typ}) do not match for binary operator {node.op.__class__.__name__} and cannot be inferred")

        # TODO: fix this later!
        assert isinstance(lhs.typ, builtin.IntegerType)

        match node.op.__class__.__name__:
            case "Add":
                op = arith.Addi.get(lhs, rhs)
            case "Sub":
                op = arith.Subi.get(lhs, rhs)
            case "Mult":
                op = arith.Muli.get(lhs, rhs)
            case _:
                # TODO: support more operators!
                raise VisitorException(f"binary operator {node.op.__class__.__name__} is not supported")
        self.program.insert_op(op)

    def visit_Constant(self, node: ast.Constant):
        """
        Visits a constant value.
        """
        target_ty = self.program.inferred_type
        if target_ty is None:
            raise VisitorException(f"unable to infer the type of {node.value} on line {node.lineno}")

        if isinstance(target_ty, builtin.IntegerType):
            value_attr = builtin.IntegerAttr.from_int_and_width(node.value, target_ty.width.data)
        elif isinstance(node.value, builtin.Float32Type):
            value_attr = builtin.FloatAttr.from_float_and_width(node.value, 32)
        elif isinstance(node.value, builtin.Float64Type):
            value_attr = builtin.FloatAttr.from_float_and_width(node.value, 64)
        else:
            raise VisitorException(f"trying to infer an unknown type {target_ty} on lin {node.lineno}")
        constant_op = arith.Constant.from_attr(value_attr, target_ty)
        self.program.insert_op(constant_op)
        return

    def _check_function_signature(self, node: ast.FunctionDef):
        """Throws an exception if this function cannot be lowered to xDSL."""
        # Don't support vararg and its friends.
        if getattr(node.args, "vararg") != None:
            raise VisitorException("`vararg` arguments are not supported")
        if getattr(node.args, "kwarg") != None:
            raise VisitorException("`kwarg` arguments are not supported")
        if getattr(node.args, "kwonlyargs"):
            raise VisitorException("`kwonlyargs` are not supported")
        if getattr(node.args, "kw_defaults"):
            raise VisitorException("`kw_defaults` are not supported")
        if getattr(node.args, "defaults"):
            raise VisitorException("`defaults` are not supported")

        # Explicitly require type annotations on function arguments.
        args = node.args.args
        for i, arg in enumerate(args):
            annotation = arg.annotation
            if annotation is None:
                # TODO: Compiler should complain about all arguments which miss type annotations, and not just the first one.
                raise VisitorException(f"missing a type hint on argument {i} in function {node.name}, line {annotation.lineno}.")

    def _get_argument_types(self, node: ast.FunctionDef):
        args = node.args.args
        arg_types = []
        for arg in args:
            arg_type = self.hint_converter.convert_hint(arg.annotation)
            arg_types.append(arg_type)
        return arg_types
    
    def _get_return_types(self, node: ast.FunctionDef):
        return_type = self.hint_converter.convert_hint(node.returns)
        return_types = []
        if return_type is not None:
            return_types.append(return_type)
        return return_types

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """
        Visits a function definition, e.g.

        def foo():
            ...
        """
        # First, check if function signature is valid.
        self._check_function_signature(node)

        # Then, convert type in the function signature.
        arg_types = self._get_argument_types(node)
        return_types = self._get_return_types(node)

        # Create a region for the function body and entry block.
        entry_block = Block()
        body_region = Region.from_block_list([entry_block])
        func_op = func.FuncOp.from_region(node.name, arg_types, return_types, body_region)
        self.program.insert_op(func_op)
        self.program.insertion_point_from_op(func_op)

        # What about globals?
        self.symbol_table = dict()

        # All arguments are declared using symref.
        for i, arg in enumerate(node.args.args):
            symbol_name = arg.arg #builtin.StringAttr.from_str(arg.arg)
            arg = entry_block.insert_arg(arg_types[i], i)
            entry_block.add_op(symref.Declare.get(symbol_name))
            self.symbol_table[symbol_name] = arg_types[i]
            entry_block.add_op(symref.Update.get(symbol_name, arg))

        # Parse function body.
        for stmt in node.body:
            self.visit(stmt)

        self.program.insertion_point_from_op(func_op.parent_op())


    def visit_Name(self, node: ast.Name):
        """
        Visits a named variable - can be stack-allocated or an argument.
        """
        # TODO: we should have a proper symbol table!
        ty = self.symbol_table[node.id]
        fetch_op = symref.Fetch.get(node.id, ty)
        self.program.insert_op(fetch_op)

    def visit_Return(self, node: ast.Return):
        """
        Visits a return statement in the function.
        """
        if node.value is not None:
            raise VisitorException("returning values from functions is not supported")
        else:
            self.program.insert_op(func.Return.get())

    def visit_With(self, node: ast.With):
        """
        Visits a with block which represents a new module.
        """
        module_op = builtin.ModuleOp.from_region_or_ops([])
        self.program.insert_op(module_op)
        self.program.insertion_point_from_op(module_op)
        for stmt in node.body:
            self.visit(stmt)
        self.program.insertion_point_from_op(module_op.parent_op())
    
    def visit_Pass(self, node: ast.Pass):
        # Region is empty!
        pass