import asyncio

from app.orchestration.review_graph import review_graph

result = asyncio.run(
    review_graph.ainvoke(
        {
            "source_code": """
import subprocess

user_input=input()

subprocess.call(
    user_input,
    shell=True
)
"""
        }
    )
)

print(result)
