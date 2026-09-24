"""Project 5 — Human-in-the-Loop Approval Agent.
Uncertainty detection -> pause -> request human input -> resume with validated
context, with a complete ordered audit trail.
"""
import json
import uuid


class UnknownTicket(Exception):
    pass


class ApprovalAgent:
    def __init__(
        self,
        llm,
        confidence_threshold: float = 0.75,
        protected_actions: frozenset = frozenset({
            "delete", "send_email", "refund"
        }),
    ):
        self.llm = llm
        self.confidence_threshold = confidence_threshold
        self.protected_actions = protected_actions
        self.audit_log: list[dict] = []
        self._pending: dict[str, dict] = {}

    def _log(self, event: str, detail: dict) -> None:
        self.audit_log.append({"event": event, "detail": detail})

    def handle(self, request: str) -> dict:
        raw = self.llm.complete(request)
        parsed = json.loads(raw)
        answer = parsed.get("answer", "")
        confidence = parsed.get("confidence", 0.0)
        action = parsed.get("action")

        self._log("request", {"request": request})

        low_conf = confidence < self.confidence_threshold
        protected = action in self.protected_actions

        if not low_conf and not protected:
            self._log("completed", {"answer": answer, "action": action})
            return {"status": "completed", "answer": answer, "ticket": None}

        ticket = str(uuid.uuid4())
        reason = "protected_action" if protected else "low_confidence"
        self._pending[ticket] = {
            "answer": answer,
            "action": action,
            "request": request,
        }
        self._log("paused", {
            "ticket": ticket,
            "reason": reason,
            "confidence": confidence,
            "action": action,
        })
        return {"status": "pending", "ticket": ticket, "reason": reason}

    def resume(
        self, ticket: str, approved: bool, human_note: str = ""
    ) -> dict:
        if ticket not in self._pending:
            raise UnknownTicket(f"Ticket {ticket!r} not found or already resolved")

        pending = self._pending.pop(ticket)
        self._log("human_decision", {
            "ticket": ticket,
            "approved": approved,
            "note": human_note,
        })

        if approved:
            self._log("completed", {
                "ticket": ticket,
                "answer": pending["answer"],
            })
            return {"status": "completed", "answer": pending["answer"]}

        self._log("aborted", {"ticket": ticket})
        return {"status": "aborted", "answer": None}

    def audit_trail(self, ticket: str | None = None) -> list[dict]:
        if ticket is None:
            return self.audit_log
        return [
            e for e in self.audit_log
            if e["detail"].get("ticket") == ticket
        ]
