"""ReAct reasoning loop."""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Tuple

from app.core.logging import get_logger
from app.tools.llm_tool import LLMTool

logger = get_logger("arcas.react")

# Matches action: tool_name(arbitrary input, possibly multi-line).
_ACTION_RE = re.compile(r"\s*(\w+)\s*\((.*)\)\s*", re.DOTALL)

_MAX_OBSERVATION_CHARS = 2_000
_MAX_TRANSCRIPT_CHARS = 16_000


class ReActAgent:
    """Simulates ReAct reasoning using structured prompt chaining."""

    def __init__(
        self,
        system_prompt: str,
        tools: Dict[str, Callable[[str], object]],
        max_iterations: int = 5,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self.max_iterations = max_iterations
        self.trace: List[dict] = []

    # Public API
    def run(self, task: str) -> Tuple[str, List[dict]]:
        """Drive the reasoning loop."""
        tool_names = ", ".join(self.tools) or "(none)"
        transcript = (
            f"TASK: {task}\n\n"
            f"Available tools: {tool_names}.\n\n"
            "Reason step by step. On each step output a line beginning with "
            "'THOUGHT:' describing your reasoning. To use a tool, add a line "
            "'ACTION: tool_name(input)'. When you have enough evidence, output "
            "'FINAL ANSWER:' followed by the complete answer.\n\n"
        )

        for iteration in range(self.max_iterations):
            prompt = transcript + "THOUGHT:"

            try:
                step_output = LLMTool.generate(
                    prompt, system_prompt=self.system_prompt
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to caller below
                logger.warning(
                    "ReAct LLM call failed on iteration %d: %s",
                    iteration,
                    exc,
                )
                raise

            # Final answer? - terminate the loop.
            if "FINAL ANSWER:" in step_output:
                final = step_output.split("FINAL ANSWER:", 1)[1].strip()
                self.trace.append(
                    {
                        "type": "thought",
                        "content": _before(step_output, "FINAL ANSWER:"),
                        "iteration": iteration,
                    }
                )
                self.trace.append(
                    {"type": "final", "content": final, "iteration": iteration}
                )
                return final, self.trace

            # Tool call?
            if "ACTION:" in step_output:
                thought = _before(step_output, "ACTION:").strip()
                self.trace.append(
                    {
                        "type": "thought",
                        "content": thought or step_output.strip(),
                        "iteration": iteration,
                    }
                )

                action_part = step_output.split("ACTION:", 1)[1]
                tool_name, tool_input = self._parse_action(action_part)

                self.trace.append(
                    {
                        "type": "action",
                        "tool": tool_name,
                        "input": tool_input[:500],
                        "iteration": iteration,
                    }
                )

                observation = self._dispatch(tool_name, tool_input)
                observation_text = str(observation)[:_MAX_OBSERVATION_CHARS]

                self.trace.append(
                    {
                        "type": "observation",
                        "tool": tool_name,
                        "result": observation_text,
                        "iteration": iteration,
                    }
                )

                transcript += (
                    f"THOUGHT: {thought}\n"
                    f"ACTION: {tool_name}({tool_input[:500]})\n"
                    f"OBSERVATION: {observation_text}\n\n"
                )
                transcript = transcript[-_MAX_TRANSCRIPT_CHARS:]
                continue

            # Neither marker - treat the whole output as the final answer.
            self.trace.append(
                {
                    "type": "final",
                    "content": step_output.strip(),
                    "iteration": iteration,
                }
            )
            return step_output.strip(), self.trace

        # Max iterations reached - ask the model to conclude from the evidence.
        final_prompt = (
            transcript + "FINAL ANSWER: Based on all observations above,"
        )
        try:
            final = LLMTool.generate(
                final_prompt, system_prompt=self.system_prompt
            )
        except Exception:  # noqa: BLE001
            final = "Reasoning did not converge within the iteration budget."
        self.trace.append(
            {
                "type": "final",
                "content": final.strip(),
                "iteration": self.max_iterations,
            }
        )
        return final.strip(), self.trace

    # Internals
    def _dispatch(self, tool_name: str, tool_input: str) -> object:
        tool = self.tools.get(tool_name)
        if tool is None:
            return (
                f"Unknown tool '{tool_name}'. "
                f"Valid tools: {', '.join(self.tools) or '(none)'}."
            )
        try:
            return tool(tool_input)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ReAct tool '%s' raised: %s", tool_name, exc)
            return f"Tool '{tool_name}' failed: {exc}"

    @staticmethod
    def _parse_action(action_str: str) -> Tuple[str, str]:
        """Parse tool_name(input) -> (tool_name, input)."""
        match = _ACTION_RE.match(action_str.strip())
        if match:
            return match.group(1), match.group(2).strip().strip("\"'")
        return "unknown", action_str.strip()


def _before(text: str, marker: str) -> str:
    """Return the portion of text before marker (or all of it)."""
    return text.split(marker, 1)[0].strip()
