"""Project 4 — Memory-Enabled Conversational Agent.
Short-term rolling buffer + long-term recall with relevance scoring,
LLM-based compression, and cross-session persistence.
"""
import json


class Memory:
    def __init__(self, llm, short_window: int = 4):
        self.llm = llm
        self.short_window = short_window
        self.short_term: list[str] = []
        self.long_term: list[dict] = []

    def add_turn(self, text: str) -> None:
        self.short_term.append(text)
        while len(self.short_term) > self.short_window:
            evicted = self.short_term.pop(0)
            self.long_term.append({"text": evicted, "source": "turn"})

    def relevance(self, query: str, text: str) -> float:
        query_words = set(query.lower().split())
        if not query_words:
            return 0.0
        return len(query_words & set(text.lower().split())) / len(query_words)

    def recall(self, query: str, k: int = 3) -> list[str]:
        scored = [
            (self.relevance(query, e["text"]), i, e["text"])
            for i, e in enumerate(self.long_term)
        ]
        return [
            text for _, _, text in
            sorted(
                (s for s in scored if s[0] > 0),
                key=lambda s: (-s[0], s[1])
            )[:k]
        ]

    def compress(self) -> None:
        turns = [e for e in self.long_term if e["source"] == "turn"]
        if not turns:
            return
        prompt = "Summarize these conversation turns:\n" + "\n".join(
            f"- {e['text']}" for e in turns
        )
        summary = self.llm.complete(prompt)
        self.long_term = [
            e for e in self.long_term if e["source"] == "summary"
        ] + [{"text": summary, "source": "summary"}]

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "short_window": self.short_window,
                "short_term": self.short_term,
                "long_term": self.long_term,
            }, f)

    @classmethod
    def load(cls, llm, path: str) -> "Memory":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        m = cls(llm, short_window=data.get("short_window", 4))
        m.short_term = data.get("short_term", [])
        m.long_term = data.get("long_term", [])
        return m
