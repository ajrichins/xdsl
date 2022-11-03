# RUN: python %s | filecheck %s

from xdsl.frontend.program import FrontendProgram
from xdsl.frontend.context import CodeContext
from xdsl.frontend.dialects.builtin import i32, i64

p = FrontendProgram()
with CodeContext(p):
    #      CHECK: func.func() ["sym_name" = "f1", "function_type" = !fun<[], []>, "sym_visibility" = "private"] {
    # CHECK-NEXT:   func.return()
    # CHECK-NEXT: }
    def f1():
        return

    #      CHECK: func.func() ["sym_name" = "f2", "function_type" = !fun<[], []>, "sym_visibility" = "private"] {
    # CHECK-NEXT:   func.return()
    # CHECK-NEXT: }
    def f2():
        pass

    #      CHECK: func.func() ["sym_name" = "f3", "function_type" = !fun<[], []>, "sym_visibility" = "private"] {
    # CHECK-NEXT:   %{{.*}} : !i32 =
    # CHECK-NEXT:   func.return()
    # CHECK-NEXT: }
    def f3():
        a: i32 = 0

    #      CHECK: func.func() ["sym_name" = "f4", "function_type" = !fun<[], [!i32]>, "sym_visibility" = "private"] {
    # CHECK-NEXT:   %{{.*}} : !i32 =
    # CHECK-NEXT:   func.return(%{{.*}} : !i32)
    # CHECK-NEXT: }
    def f4() -> i32:
        a: i32 = 0
        return a

    #      CHECK: func.func() ["sym_name" = "f5", "function_type" = !fun<[!i32, !i64], []>, "sym_visibility" = "private"] {
    # CHECK-NEXT: ^{{.*}}(%{{.*}} : !i32, %{{.*}} : !i64):
    # CHECK-NEXT:   func.return()
    def f5(a: i32, b: i64):
        pass

p.compile()
p.optimize()
print(p)
