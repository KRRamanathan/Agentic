"""Project 7 — Idempotent Event Automation Agent.
Consume webhook/queue events with idempotent execution, bounded retries with
exponential backoff, and a dead-letter queue.
"""
import time as time_module


class EventProcessor:
    def __init__(
        self,
        handlers: dict,
        max_retries: int = 3,
        sleep=None,
    ):
        self.handlers = handlers
        self.max_retries = max_retries
        self.sleep = sleep or time_module.sleep
        self.processed: dict = {}
        self.dead_letter: list[dict] = []

    def _seen(self, event_id: str) -> bool:
        if event_id in self.processed:
            return True
        return any(e["event"]["id"] == event_id for e in self.dead_letter)

    def process(self, event: dict) -> dict:
        event_id = event["id"]

        if self._seen(event_id):
            return {"status": "duplicate"}

        handler = self.handlers.get(event["type"])
        if handler is None:
            self.dead_letter.append({
                "event": event,
                "error": f"Unknown event type: {event['type']}",
                "attempts": 0,
            })
            return {"status": "dead_letter"}

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                result = handler(event["payload"])
                self.processed[event_id] = result
                return {"status": "ok", "result": result}
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    self.sleep(2 ** attempt)

        self.dead_letter.append({
            "event": event,
            "error": last_error,
            "attempts": self.max_retries + 1,
        })
        return {"status": "dead_letter"}

    def replay_dead_letter(self) -> int:
        to_replay = self.dead_letter[:]
        self.dead_letter.clear()
        recovered = 0
        for entry in to_replay:
            event = entry["event"]
            # Bypass idempotency for replay
            handler = self.handlers.get(event["type"])
            if handler is None:
                self.dead_letter.append(entry)
                continue
            try:
                result = handler(event["payload"])
                self.processed[event["id"]] = result
                recovered += 1
            except Exception as exc:
                entry["error"] = str(exc)
                self.dead_letter.append(entry)
        return recovered
