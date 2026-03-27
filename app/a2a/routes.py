from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.budget_agent import BudgetAgent
from app.agents.experience_agent import ExperienceAgent
from app.agents.time_agent import TimeOptimizerAgent
from app.agents.critic_agent import CriticAgent

router = APIRouter(prefix="/a2a", tags=["a2a"])

budget_agent = BudgetAgent()
experience_agent = ExperienceAgent()
time_agent = TimeOptimizerAgent()
critic_agent = CriticAgent()


class JSONRPCRequest(BaseModel):
    jsonrpc: str
    method: str
    params: dict
    id: int | str | None = 1


def _jsonrpc_result(req_id, result: dict):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


def _jsonrpc_error(req_id, code: int, message: str):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


@router.post("/budget")
async def budget_rpc(req: JSONRPCRequest):
    if req.method != "propose":
        return _jsonrpc_error(req.id, -32601, "Method not found")

    try:
        proposal = budget_agent.propose(
            trip_request=req.params.get("trip_request", {}),
            evidence=req.params.get("evidence", []),
            prior_proposals=req.params.get("prior_proposals", []),
        )
        return _jsonrpc_result(req.id, proposal.model_dump())
    except Exception as exc:
        return _jsonrpc_error(req.id, -32000, f"Budget agent failed: {str(exc)}")


@router.post("/experience")
async def experience_rpc(req: JSONRPCRequest):
    if req.method != "propose":
        return _jsonrpc_error(req.id, -32601, "Method not found")

    try:
        proposal = experience_agent.propose(
            trip_request=req.params.get("trip_request", {}),
            evidence=req.params.get("evidence", []),
            prior_proposals=req.params.get("prior_proposals", []),
        )
        return _jsonrpc_result(req.id, proposal.model_dump())
    except Exception as exc:
        return _jsonrpc_error(req.id, -32000, f"Experience agent failed: {str(exc)}")


@router.post("/time")
async def time_rpc(req: JSONRPCRequest):
    if req.method != "propose":
        return _jsonrpc_error(req.id, -32601, "Method not found")

    try:
        proposal = time_agent.propose(
            trip_request=req.params.get("trip_request", {}),
            evidence=req.params.get("evidence", []),
            prior_proposals=req.params.get("prior_proposals", []),
        )
        return _jsonrpc_result(req.id, proposal.model_dump())
    except Exception as exc:
        return _jsonrpc_error(req.id, -32000, f"Time agent failed: {str(exc)}")


@router.post("/critic")
async def critic_rpc(req: JSONRPCRequest):
    if req.method != "review":
        return _jsonrpc_error(req.id, -32601, "Method not found")

    try:
        result = critic_agent.review(
            trip_request=req.params.get("trip_request", {}),
            evidence=req.params.get("evidence", []),
            proposals=req.params.get("proposals", []),
        )
        return _jsonrpc_result(req.id, result)
    except Exception as exc:
        return _jsonrpc_error(req.id, -32000, f"Critic agent failed: {str(exc)}")