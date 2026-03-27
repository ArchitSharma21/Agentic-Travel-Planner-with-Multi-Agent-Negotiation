from app.agents.base import BaseAgent
from app.prompts import CRITIC_AGENT_PROMPT


class CriticAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="critic_agent", system_prompt=CRITIC_AGENT_PROMPT, temperature=0.1)

    def review(self, trip_request: dict, evidence: list[dict], proposals: list[dict]) -> dict:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "proposals": proposals,
        }
        return self.invoke_json(payload)