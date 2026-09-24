"""Project 8 — Multi-Agent Debate System.
N proposer agents answer independently, a critic scores each proposal,
consensus picks a winner, an aggregator synthesizes the final answer
with a confidence value.
"""
import json


class Debate:
    def __init__(self, proposers: list, critic, aggregator):
        self.proposers = proposers
        self.critic = critic
        self.aggregator = aggregator

    def run(self, question: str) -> dict:
        # Each proposer answers independently
        proposals = [
            p.complete(f"Answer this question: {question}")
            for p in self.proposers
        ]

        # Critic scores all proposals in one call
        critic_prompt = (
            f"Question: {question}\n\nProposals:\n"
            + "\n".join(
                f"{i}. {p}" for i, p in enumerate(proposals)
            )
            + '\n\nReturn JSON: {"scores": [{"index": 0, "score": 0.0-1.0, '
              '"critique": "..."}]}'
        )
        critic_raw = self.critic.complete(critic_prompt)
        critic_data = json.loads(critic_raw)
        score_list = critic_data["scores"]
        scores = [item["score"] for item in score_list]
        critiques = [item["critique"] for item in score_list]

        # Winner: highest score, ties break on lower index
        winner_index = min(
            range(len(scores)),
            key=lambda i: (-scores[i], i)
        )
        winner_score = scores[winner_index]

        # Confidence: winner minus mean of others, clamped
        others = [s for j, s in enumerate(scores) if j != winner_index]
        if others:
            confidence = winner_score - (sum(others) / len(others))
        else:
            confidence = winner_score
        confidence = max(0.0, min(1.0, confidence))

        # Aggregator synthesizes final answer
        agg_prompt = (
            f"Question: {question}\n"
            f"Winning proposal: {proposals[winner_index]}\n"
            f"Critique: {critiques[winner_index]}\n"
            f"Synthesize the best final answer."
        )
        answer = self.aggregator.complete(agg_prompt)

        return {
            "answer": answer,
            "winner_index": winner_index,
            "confidence": confidence,
            "proposals": proposals,
            "scores": scores,
        }
