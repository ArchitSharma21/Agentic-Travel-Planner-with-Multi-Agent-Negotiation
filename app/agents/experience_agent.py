from app.agents.base import BaseAgent
from app.prompts import EXPERIENCE_AGENT_PROMPT
from app.models.agent import AgentProposal


class ExperienceAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="experience_agent", system_prompt=EXPERIENCE_AGENT_PROMPT, temperature=0.4)

    def propose(self, trip_request: dict, evidence: list[dict], prior_proposals: list[dict]) -> AgentProposal:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "prior_proposals": prior_proposals,
        }
        data = self.invoke_json(payload)
        return AgentProposal(**data)