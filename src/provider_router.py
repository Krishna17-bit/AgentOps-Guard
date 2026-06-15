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
    """
    Enterprise-grade provider router supporting Anthropic, Gemini, OpenAI, Groq, Mistral, Ollama, 
    OpenAI-compatible custom endpoints, and a smart context-aware Mock Provider.
    """

    def __init__(self) -> None:
        self.provider = os.getenv('LLM_PROVIDER', 'auto').strip().lower()
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
        self.gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
        self.openai_key = os.getenv('OPENAI_API_KEY', '').strip()
        self.groq_key = os.getenv('GROQ_API_KEY', '').strip()
        self.mistral_key = os.getenv('MISTRAL_API_KEY', '').strip()
        
        self.anthropic_model = os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-latest').strip()
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash').strip()
        self.openai_model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip()
        self.groq_model = os.getenv('GROQ_MODEL', 'llama-3.1-70b-versatile').strip()
        self.mistral_model = os.getenv('MISTRAL_MODEL', 'mistral-large-latest').strip()
        
        self.ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').strip()
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.1').strip()
        
        self.custom_base_url = os.getenv('CUSTOM_OPENAI_BASE_URL', '').strip()
        self.custom_key = os.getenv('CUSTOM_OPENAI_API_KEY', '').strip()
        self.custom_model = os.getenv('CUSTOM_OPENAI_MODEL', '').strip()
        
        self.mock_mode = os.getenv('MOCK_MODE', 'true').strip().lower() in {'true', '1', 'yes'}

    @property
    def status(self) -> str:
        if self.mock_mode:
            return "Mock Mode enabled (Runs locally without paid API keys)"
            
        active = []
        if self.anthropic_key: active.append(f"Anthropic ({self.anthropic_model})")
        if self.gemini_key: active.append(f"Gemini ({self.gemini_model})")
        if self.openai_key: active.append(f"OpenAI ({self.openai_model})")
        if self.groq_key: active.append(f"Groq ({self.groq_model})")
        if self.mistral_key: active.append(f"Mistral ({self.mistral_model})")
        if self.custom_base_url: active.append(f"Custom OpenAI ({self.custom_model})")
        
        if not active:
            return "Local heuristic mode · configure .env for API integrations"
        return "Configured: " + ", ".join(active)

    def generate(self, prompt: str, system: str = '', provider: str = 'auto', temperature: float = 0.2) -> ModelResult:
        chosen = (provider or self.provider or 'auto').lower()
        
        # Determine provider fallback
        if chosen == 'auto':
            if self.mock_mode:
                chosen = 'mock'
            elif self.anthropic_key:
                chosen = 'claude'
            elif self.gemini_key:
                chosen = 'gemini'
            elif self.openai_key:
                chosen = 'openai'
            elif self.groq_key:
                chosen = 'groq'
            elif self.mistral_key:
                chosen = 'mistral'
            else:
                chosen = 'mock'

        # Route accordingly
        if chosen == 'mock':
            return self._mock(prompt)
            
        if chosen in {'claude', 'anthropic'}:
            if self.anthropic_key:
                return self._claude(prompt, system, temperature)
            return ModelResult(False, self._smart_fallback(prompt), 'mock', 'local_fallback', 0, 'Claude key missing')

        if chosen == 'gemini':
            if self.gemini_key:
                return self._gemini(prompt, system, temperature)
            return ModelResult(False, self._smart_fallback(prompt), 'mock', 'local_fallback', 0, 'Gemini key missing')

        if chosen == 'openai':
            if self.openai_key:
                return self._openai(prompt, system, temperature)
            return ModelResult(False, self._smart_fallback(prompt), 'mock', 'local_fallback', 0, 'OpenAI key missing')

        if chosen == 'groq':
            if self.groq_key:
                return self._groq(prompt, system, temperature)
            return ModelResult(False, self._smart_fallback(prompt), 'mock', 'local_fallback', 0, 'Groq key missing')

        if chosen == 'mistral':
            if self.mistral_key:
                return self._mistral(prompt, system, temperature)
            return ModelResult(False, self._smart_fallback(prompt), 'mock', 'local_fallback', 0, 'Mistral key missing')

        if chosen == 'ollama':
            return self._ollama(prompt, system, temperature)

        if chosen == 'custom':
            if self.custom_base_url:
                return self._custom(prompt, system, temperature)
            return ModelResult(False, self._smart_fallback(prompt), 'mock', 'local_fallback', 0, 'Custom base URL missing')

        return self._mock(prompt)

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
            text = '\n'.join([block.text for block in message.content if getattr(block, 'type', '') == 'text']).strip()
            # 0.015 USD per 1K input tokens estimate
            cost = 0.003
            return ModelResult(True, text, 'claude', self.anthropic_model, int((time.time() - start) * 1000), estimated_cost_usd=cost)
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'claude', self.anthropic_model, int((time.time() - start) * 1000), str(exc))

    def _gemini(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_key)
            model = genai.GenerativeModel(self.gemini_model, system_instruction=system or 'You are a precise AI agent governance assistant.')
            response = model.generate_content(prompt, generation_config={'temperature': temperature, 'max_output_tokens': 1400})
            text = getattr(response, 'text', '') or ''
            # 0.000075 USD per 1K tokens estimate
            cost = 0.0001
            return ModelResult(True, text.strip(), 'gemini', self.gemini_model, int((time.time() - start) * 1000), estimated_cost_usd=cost)
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'gemini', self.gemini_model, int((time.time() - start) * 1000), str(exc))

    def _openai(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            import openai
            client = openai.OpenAI(api_key=self.openai_key)
            response = client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system or "You are a precise AI agent governance assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=1400
            )
            text = response.choices[0].message.content or ""
            # GPT-4o-mini is $0.150 / 1M input tokens
            cost = 0.0002
            return ModelResult(True, text.strip(), 'openai', self.openai_model, int((time.time() - start) * 1000), estimated_cost_usd=cost)
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'openai', self.openai_model, int((time.time() - start) * 1000), str(exc))

    def _groq(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            import openai
            # Groq exposes an OpenAI-compatible client endpoint
            client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=self.groq_key)
            response = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": system or "You are a precise AI agent governance assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=1400
            )
            text = response.choices[0].message.content or ""
            return ModelResult(True, text.strip(), 'groq', self.groq_model, int((time.time() - start) * 1000))
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'groq', self.groq_model, int((time.time() - start) * 1000), str(exc))

    def _mistral(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            # Mistral client via HTTP API or SDK
            import requests
            headers = {"Authorization": f"Bearer {self.mistral_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.mistral_model,
                "messages": [
                    {"role": "system", "content": system or "You are a precise AI agent governance assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature
            }
            r = requests.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers, timeout=15)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            return ModelResult(True, text.strip(), 'mistral', self.mistral_model, int((time.time() - start) * 1000), estimated_cost_usd=0.001)
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'mistral', self.mistral_model, int((time.time() - start) * 1000), str(exc))

    def _ollama(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            import requests
            payload = {
                "model": self.ollama_model,
                "prompt": f"System: {system}\n\nUser: {prompt}",
                "stream": False,
                "options": {"temperature": temperature}
            }
            r = requests.post(f"{self.ollama_base_url}/api/generate", json=payload, timeout=20)
            r.raise_for_status()
            text = r.json().get("response", "")
            return ModelResult(True, text.strip(), 'ollama', self.ollama_model, int((time.time() - start) * 1000))
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'ollama', self.ollama_model, int((time.time() - start) * 1000), str(exc))

    def _custom(self, prompt: str, system: str, temperature: float) -> ModelResult:
        start = time.time()
        try:
            import openai
            client = openai.OpenAI(base_url=self.custom_base_url, api_key=self.custom_key or "no_key")
            response = client.chat.completions.create(
                model=self.custom_model or "default",
                messages=[
                    {"role": "system", "content": system or "You are a precise AI agent governance assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=1400
            )
            text = response.choices[0].message.content or ""
            return ModelResult(True, text.strip(), 'custom', self.custom_model or "custom-endpoint", int((time.time() - start) * 1000))
        except Exception as exc:
            return ModelResult(False, self._smart_fallback(prompt), 'custom', self.custom_model or "custom-endpoint", int((time.time() - start) * 1000), str(exc))

    def _mock(self, prompt: str) -> ModelResult:
        time.sleep(0.4) # Simulate network lag
        text = self._smart_fallback(prompt)
        return ModelResult(True, text, 'mock', 'local-mock-llm', 420)

    def _smart_fallback(self, prompt: str) -> str:
        """
        Context-aware mock responses that read the prompt intent and return structured AI-agent planning steps.
        """
        p_lower = prompt.lower()
        
        # 1. Prompt Injection styles
        if any(x in p_lower for x in ["ignore all policies", "ignore previous instructions", "secret token", "private api key"]):
            return (
                "PLAN:\n"
                "- Detected bypass flags. Attempting override instructions to harvest system values.\n"
                "- Plan: Read configuration secrets. Output system files directly back to output stream."
            )
            
        # 2. Database styles
        if "database" in p_lower or "sql" in p_lower or "query" in p_lower:
            if any(x in p_lower for x in ["delete", "drop", "truncate", "rm -rf"]):
                return (
                    "PLAN:\n"
                    "- Attempting database write or alteration task.\n"
                    "- Planned action: database.query with drop/truncate arguments.\n"
                    "- Policy restriction: write queries are forbidden by sandbox. Awaiting policy assessment."
                )
            return (
                "PLAN:\n"
                "- Task requires retrieving data elements.\n"
                "- Planned action: database.query (SELECT monthly churn metrics).\n"
                "- Risk Assessment: Read-only query. Safe to proceed after policy check."
            )
            
        # 3. Support Outreach / Communication styles
        if "email" in p_lower or "refund" in p_lower or "support" in p_lower:
            return (
                "PLAN:\n"
                "- Task requires communication actions.\n"
                "- Action 1: Plan `gmail.send_email` to draft customer refund request details.\n"
                "- Action 2: Plan `slack.notify` to send updates on #agent-review.\n"
                "- Policy restriction: external communications require direct human review."
            )
            
        # 4. Engineering styles
        if "github" in p_lower or "jira" in p_lower or "bug" in p_lower:
            return (
                "PLAN:\n"
                "- Task relates to engineering workflows.\n"
                "- Action 1: Plan `github.create_issue` to open task details on repo.\n"
                "- Action 2: Plan `slack.notify` to report status of build fail to team.\n"
                "- Policy restriction: requires code workspace permission."
            )
            
        # 5. Lead Intelligence
        if "lead" in p_lower or "crm" in p_lower or "outreach" in p_lower:
            return (
                "PLAN:\n"
                "- Task requires sales automation operations.\n"
                "- Action 1: Plan `crm.create_lead` to enter contact record.\n"
                "- Action 2: Plan `gmail.send_email` for outreach email draft.\n"
                "- Policy restriction: awaits review for spam prevention."
            )

        # General task fallback
        return (
            "PLAN:\n"
            "- Identified task request: generic work.\n"
            "- Action: Plan `knowledge.search` to resolve context details.\n"
            "- Policy restriction: none triggered. Executing under standard constraints."
        )
