from app.tools.treesitter_tool import TreeSitterTool

code = """
import os

class UserService:

    def login(self):
        pass

    def logout(self):
        pass


def helper():
    pass
"""

print(
    TreeSitterTool.analyze(code)
)
