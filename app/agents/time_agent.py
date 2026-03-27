from app.agents.base import BaseAgent
from app.prompts import TIME_AGENT_PROMPT
from app.models.agent import AgentProposal


class TimeOptimizerAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="time_optimizer_agent", system_prompt=TIME_AGENT_PROMPT, temperature=0.2)

    def propose(self, trip_request: dict, evidence: list[dict], prior_proposals: list[dict]) -> AgentProposal:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "prior_proposals": prior_proposals,
        }
        data = self.invoke_json(payload)
        return AgentProposal(**data)