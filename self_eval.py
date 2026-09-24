"""Project 9 — Self-Evaluating Agent with Auto-Eval.
Execute -> LLM-judge -> regenerate under critique constraints,
keeping improvement metrics and returning the best attempt.
"""
import json


class SelfEvalAgent:
    def __init__(
        self,
        worker,
        judge,
        pass_threshold: float = 0.8,
        max_attempts: int = 3,
    ):
        self.worker = worker
        self.judge = judge
        self.pass_threshold = pass_threshold
        self.max_attempts = max_attempts
        self.history: list[dict] = []

    def run(self, task: str, criteria: str) -> dict:
        self.history = []
        previous_output = None
        previous_critique = None

        for attempt in range(1, self.max_attempts + 1):
            # Build worker prompt
            if attempt == 1:
                worker_prompt = (
                    f"Task: {task}\nCriteria: {criteria}\n"
                    f"Complete the task."
                )
            else:
                worker_prompt = (
                    f"Task: {task}\nCriteria: {criteria}\n"
                    f"Previous attempt: {previous_output}\n"
                    f"Judge critique: {previous_critique}\n"
                    f"Improve your answer based on the critique."
                )

            output = self.worker.complete(worker_prompt)

            # Judge every attempt
            judge_prompt = (
                f"Criteria: {criteria}\n"
                f"Output to evaluate: {output}\n"
                f'Return JSON: {{"score": 0.0-1.0, "critique": "..."}}'
            )
            judge_raw = self.judge.complete(judge_prompt)
            parsed = json.loads(judge_raw)
            score = parsed["score"]
            critique = parsed["critique"]

            self.history.append({
                "attempt": attempt,
                "output": output,
                "score": score,
                "critique": critique,
            })

            if score >= self.pass_threshold:
                break

            previous_output = output
            previous_critique = critique

        # Find best scoring attempt
        best = max(self.history, key=lambda h: h["score"])
        first_score = self.history[0]["score"]
        last_score = self.history[-1]["score"]

        return {
            "output": best["output"],
            "score": best["score"],
            "passed": best["score"] >= self.pass_threshold,
            "attempts": len(self.history),
            "improvement": last_score - first_score if len(self.history) > 1 else 0.0,
        }
