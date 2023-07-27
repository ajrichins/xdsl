#!/usr/bin/env python3

import argparse
import sys
from typing import Sequence

from xdsl.interpreter import Interpreter
from xdsl.interpreters import arith, builtin, func, memref, printf, scf
from xdsl.interpreters.experimental import wgpu
from xdsl.ir import MLContext
from xdsl.tools.command_line_tool import CommandLineTool


class xDSLRunMain(CommandLineTool):
    interpreter: Interpreter

    def __init__(
        self,
        description: str = "xDSL modular runner",
        args: Sequence[str] | None = None,
    ):
        self.available_frontends = {}

        self.ctx = MLContext()
        self.register_all_dialects()
        self.register_all_frontends()
        # arg handling
        arg_parser = argparse.ArgumentParser(description=description)
        self.register_all_arguments(arg_parser)
        self.args = arg_parser.parse_args(args=args)

        self.ctx.allow_unregistered = self.args.allow_unregistered_dialect

    def register_implementations(self, interpreter: Interpreter):
        interpreter.register_implementations(func.FuncFunctions())
        interpreter.register_implementations(memref.MemrefFunctions())
        interpreter.register_implementations(wgpu.WGPUFunctions())
        interpreter.register_implementations(builtin.BuiltinFunctions())
        interpreter.register_implementations(arith.ArithFunctions())
        interpreter.register_implementations(printf.PrintfFunctions())
        interpreter.register_implementations(scf.ScfFunctions())

    def run(self):
        input, file_extension = self.get_input_stream()
        try:
            module = self.parse_chunk(input, file_extension)
            if module is not None:
                interpreter = Interpreter(module)
                self.register_implementations(interpreter)
                result = interpreter.call_op("main", ())
                print(f"result: {result}")
        finally:
            if input is not sys.stdin:
                input.close()


def main():
    return xDSLRunMain().run()


if __name__ == "__main__":
    main()
