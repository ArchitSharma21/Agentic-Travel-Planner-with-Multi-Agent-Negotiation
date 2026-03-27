from __future__ import annotations

import json
from typing import Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent
from a2a.utils import get_message_text, new_agent_text_message, new_task, new_text_artifact


class ProposalExecutor(AgentExecutor):
    def __init__(self, handler: Callable[[dict], dict], name: str):
        self.handler = handler
        self.name = name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                final=False,
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(f"{self.name} processing request..."),
                ),
            )
        )

        raw_text = get_message_text(context.message)
        payload = json.loads(raw_text) if raw_text else {}

        result = self.handler(payload)

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                artifact=new_text_artifact(
                    name="result",
                    text=json.dumps(result, ensure_ascii=False),
                ),
            )
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                final=True,
                status=TaskStatus(
                    state=TaskState.completed,
                    message=new_agent_text_message(f"{self.name} completed."),
                ),
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")