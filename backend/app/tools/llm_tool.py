import requests

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.tools.llm")


class LLMNotConfiguredError(RuntimeError):
    """Raised when the LLM provider has not been configured."""


class PromptInjectionDetectedError(RuntimeError):
    """Raised when a canary token leaks, proving an injection succeeded."""


class LLMTool:
    """Thin client for the LLM gateway."""

    @staticmethod
    def is_available() -> bool:
        return settings.llm_configured

    @staticmethod
    def generate(user_prompt: str, system_prompt: str = "") -> str:
        """Traced, canary-protected entry point (see _generate)."""
        from app.core.injection_detector import CanaryTokens
        from app.core.telemetry import start_span

        canary = ""
        if getattr(settings, "ENABLE_CANARY_TOKENS", True) and system_prompt:
            # Plant a session-integrity token in the system prompt.
            canary = CanaryTokens.generate()
            system_prompt = CanaryTokens.wrap_system_prompt(system_prompt, canary)

        with start_span(
            "tool.llm", layer=6, prompt_chars=len(user_prompt or "")
        ) as span:
            output = LLMTool._generate(user_prompt, system_prompt)
            span.set_attribute("response_chars", len(output or ""))

        if canary:
            leak = CanaryTokens.detect_leak(output, canary)
            if leak is not None:
                span.set_attribute("canary_leaked", True)
                LLMTool._record_canary_leak(leak)
                raise PromptInjectionDetectedError(leak.detail)

        return output

    @staticmethod
    def _record_canary_leak(signal) -> None:
        logger.error("CANARY LEAK: %s", signal.detail)
        try:
            from app.repositories.audit_repository import AuditRepository

            AuditRepository.record(
                db=None,
                action="canary_leak",
                detail=signal.detail,
            )
        except Exception:  # noqa: BLE001 - audit must never break the request
            pass

    @staticmethod
    def _generate(user_prompt: str, system_prompt: str = "") -> str:
        if not settings.llm_configured:
            raise LLMNotConfiguredError(
                "LLM_API_URL / LLM_API_KEY are not set."
            )

        headers = {
            "Authorization": (
                f"Bearer {settings.LLM_API_KEY}"
            ),
            "Content-Type": "application/json",
        }

        if system_prompt:
            full_prompt = (
                f"<|system|>\n{system_prompt}\n\n"
                f"<|user|>\n{user_prompt}"
            )
        else:
            full_prompt = user_prompt

        payload = {"prompt": full_prompt}

        response = requests.post(
            settings.LLM_API_URL,
            headers=headers,
            json=payload,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        data = response.json()

        return LLMTool._extract_text(data)

    @staticmethod
    def _extract_text(data) -> str:
        """Normalise the various response shapes the gateway can return."""
        try:
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    for key in ("response", "text", "content", "output"):
                        if key in first:
                            return str(first[key])
                return str(first)

            if isinstance(data, dict):
                for key in ("response", "text", "content", "output"):
                    if key in data:
                        return str(data[key])

            return str(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not parse LLM response: %s", exc)
            return str(data)
