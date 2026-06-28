from app.agents.base import BaseAgent
from app.prompts import EXPERIENCE_AGENT_PROMPT
from app.models.agent import AgentProposal


class ExperienceAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="experience_agent", system_prompt=EXPERIENCE_AGENT_PROMPT, temperature=0.4)

    def propose(
        self,
        trip_request: dict,
        evidence: list[dict],
        prior_proposals: list[dict],
        pricing_context: dict | None = None,
        llm_config: dict | None = None,
    ) -> AgentProposal:
        payload = {
            "trip_request": trip_request,
            "evidence": evidence,
            "pricing_context": pricing_context or {},
            "prior_proposals": prior_proposals,
        }
        data = self.invoke_json(payload, llm_config=llm_config)
        data = self.normalize_proposal(
            data,
            default_objective="maximize experience quality",
        )
        return AgentProposal(**data)
