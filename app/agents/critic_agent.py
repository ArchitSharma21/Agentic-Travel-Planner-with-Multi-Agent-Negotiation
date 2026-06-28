from app.agents.base import BaseAgent
from app.prompts import CRITIC_AGENT_PROMPT


class CriticAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="critic_agent", system_prompt=CRITIC_AGENT_PROMPT, temperature=0.1)

    def review(
        self,
        trip_request: dict,
        evidence: list[dict],
        proposals: list[dict],
        pricing_context: dict | None = None,
        llm_config: dict | None = None,
    ) -> dict:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "pricing_context": pricing_context or {},
            "proposals": proposals,
        }
        data = self.invoke_json(payload, llm_config=llm_config)
        return self.normalize_critic_result(data)
