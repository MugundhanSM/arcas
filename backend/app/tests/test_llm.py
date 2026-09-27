from app.tools.llm_tool import LLMTool

response = LLMTool.generate(
    "Explain what SQL injection is in 3 lines."
)

print(response)
