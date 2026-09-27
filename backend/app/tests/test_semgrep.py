from app.tools.semgrep_tool import SemgrepTool

code = """
import subprocess

user_input = input()

subprocess.call(user_input, shell=True)
"""

result = SemgrepTool.analyze(code)

print(result)
