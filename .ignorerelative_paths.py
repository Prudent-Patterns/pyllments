from pathlib import Path
from pyllments.exp.module_a import A

class B(A):
    def __init__(self):
        super().__init__()
        self.pathb = Path(__file__)
        # self.pathb_rel = type(self).get_rel_path()

a = A()
b = B()
# print(f"Path A: {a.patha}\nPath B: {b.patha}\nPath B (from file): {b.pathb}\nPath B (from class): {b.pathb_rel}")
print(f"Base Path A: {a.get_base_path()}\nParent of Base Path A: {a.get_base_path().parent}\nBase Path B: {b.get_base_path()}\nParent of Base Path B: {b.get_base_path().parent}")