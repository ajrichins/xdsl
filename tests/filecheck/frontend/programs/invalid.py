# RUN: python %s | filecheck %s

from xdsl.frontend.exception import FrontendProgramException
from xdsl.frontend.program import FrontendProgram
from xdsl.frontend.context import CodeContext
from xdsl.frontend.dialects.builtin import i32

p = FrontendProgram()

#      CHECK: Cannot compile program without the code context
# CHECK-NEXT:     p = FrontendProgram()
# CHECK-NEXT:     with CodeContext(p):
# CHECK-NEXT:         # Your code here.
try:
    p.compile(desymref=False)
except FrontendProgramException as e:
    print(e.msg)

#      CHECK: Cannot print the program IR without compiling it first. Make sure to use:
# CHECK-NEXT:     p = FrontendProgram()
# CHECK-NEXT:     with CodeContext(p):
# CHECK-NEXT:         # Your code here.
# CHECK-NEXT:     p.compile()
with CodeContext(p):

    def foo():
        return


try:
    print(p.xdsl())
except FrontendProgramException as e:
    print(e.msg)

with CodeContext(p):
    # CHECK: Expected 'foo' to return a type.
    def foo() -> i32:
        pass


try:
    p.compile(desymref=False)
    print(p.xdsl())
except FrontendProgramException as e:
    print(e.msg)
