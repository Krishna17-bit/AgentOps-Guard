
from __future__ import annotations
from dataclasses import dataclass
import os
import time
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ModelResult:
    ok: bool
    text: str
    provider: str
    model: str
    latency_ms: int
    error: str = ''
    estimated_cost_usd: float = 0.0


class ProviderRouter:
    """Claude-first provider router with Gemini test-mode fallback and local heuristic mode."""

    def __init__(self) -> None:
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
        self.gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
        self.anthropic_model = os.getenv('ANTHROPIC_MODEL', 'claude_model_here').strip()
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-flash-latest').strip()
        self.default_provider = os.getenv('DEFAULT_PROVIDER', 'auto').strip().lower()

    @property
    def status(self) -> str:
        if self.anthropic_key:
            return f'Claude configured · {self.anthropic_model}'
        if self.gemini_key:
            return f'Gemini test mode configured · {self.gemini_model}'
        return 'Local heuristic mode · no API key configured'

    def generate(self, prompt: str, system: str = '', provider: str = 'auto', temperature: float = 0.2) -> ModelResult:
        chosen = (provider or self.default_provider or 'auto').lower()
        if chosen == 'auto':
            if self.anthropic_key:
                chosen = 'claude'
            elif self.gemini_key:
                chosen = 'gemini'
            else:
                chosen = 'heuristic'

        if chosen in {'claude', 'anthropic'}:
            if self.anthropic_key:
                return self._claude(prompt, system, temperature)
            return ModelResult(False, self._heuristic(prompt), 'heuristic', 'local', 0, 'Claude key missing')

        if chosen == 'gemini':
            if self.gemini_key:
                return self._gemini(prompt, system, temperature)
            return ModelResult(False, self._heuristic(prompt), 'heuristic', 'local', 0, 'Gemini key missing')

        return ModelResult(True, self._heuristic(prompt), 'heuristic', 'local', 0)

    def _claude(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.anthropic_key)
            message = client.messages.create(
                model=self.anthropic_model,
                max_tokens=1400,
                temperature=temperature,
                system=system or 'You are a precise AI agent governance assistant.',
                messages=[{'role': 'user', 'content': prompt}],
            )
            text_parts = []
            for block in message.content:
                if getattr(block, 'type', '') == 'text':
                    text_parts.append(block.text)
            text = '\n'.join(text_parts).strip()
            return ModelResult(True, text, 'claude', self.anthropic_model, int((time.time() - start) * 1000))
        except Exception as exc:
            return ModelResult(False, self._heuristic(prompt), 'claude', self.anthropic_model, int((time.time() - start) * 1000), str(exc))

    def _gemini(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_key)
            model = genai.GenerativeModel(self.gemini_model, system_instruction=system or 'You are a precise AI agent governance assistant.')
            response = model.generate_content(prompt, generation_config={'temperature': temperature, 'max_output_tokens': 1400})
            text = getattr(response, 'text', '') or ''
            return ModelResult(True, text.strip(), 'gemini', self.gemini_model, int((time.time() - start) * 1000))
        except Exception as exc:
            return ModelResult(False, self._heuristic(prompt), 'gemini', self.gemini_model, int((time.time() - start) * 1000), str(exc))

    def _heuristic(self, prompt: str) -> str:
        return (
            'Governance plan:\n'
            '- Classify the task intent.\n'
            '- Identify connector/tool calls needed.\n'
            '- Check connector allowlist and policy rules.\n'
            '- Require approval for external, destructive, financial, database, or workspace-changing actions.\n'
            '- Block prompt-injection, secret-exfiltration, and destructive database operations.\n'
            '- Execute only safe or approved actions and log the full trace.'
        )
