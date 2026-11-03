"""LLM judges for groundedness, run on a local model that is different from the one that wrote the text.

Both RAGAS and DeepEval measure *faithfulness*: the share of claims in the postmortem that are supported
by the retrieved evidence. A small local judge is noisy, so scores are reported as means over many incidents.
"""
import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

JUDGE_MODEL = os.environ.get("ARGUS_JUDGE_MODEL", "qwen3:4b")


def postmortem_text(pm: dict) -> str:
    """The claims to be judged: root cause, summary and recommended actions."""
    parts = [pm["root_cause"], pm["summary"], *pm["recommended_actions"]]
    return "\n".join(p.strip() for p in parts if p.strip())


def contexts(evidence: dict, pm: dict | None = None) -> list[str]:
    """What a claim may rest on: every log line, the chosen runbook's sections and the metric notes.
    Other runbooks the agent merely retrieved are left out, so a claim copied from the wrong runbook is flagged."""
    rb = (pm or {}).get("runbook_id")
    keep = [(cid, item) for cid, item in evidence.items()
            if item["kind"] != "runbook" or rb is None or cid.startswith(rb + "#")]
    return [f"[{cid}] {item['text']}" for cid, item in keep]


def _chat():
    from langchain_ollama import ChatOllama

    # num_predict caps the reply: a small model sometimes loops forever on JSON output, and an uncapped
    # call turns one bad generation into minutes of wall time. A capped call fails fast and is recorded.
    return ChatOllama(model=JUDGE_MODEL, temperature=0, num_ctx=8192, num_predict=1200, reasoning=False, repeat_penalty=1.1)


def deepeval_faithfulness(pm: dict, evidence: dict, question: str) -> float | None:
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.models import DeepEvalBaseLLM
    from deepeval.test_case import LLMTestCase

    chat = _chat()

    class Local(DeepEvalBaseLLM):
        def __init__(self):
            self.model = chat

        def load_model(self):
            return self.model

        def generate(self, prompt: str, schema=None):
            if schema is not None:
                return self.model.with_structured_output(schema).invoke(prompt)
            return self.model.invoke(prompt).content

        async def a_generate(self, prompt: str, schema=None):
            if schema is not None:
                return await self.model.with_structured_output(schema).ainvoke(prompt)
            return (await self.model.ainvoke(prompt)).content

        def get_model_name(self):
            return JUDGE_MODEL

    metric = FaithfulnessMetric(model=Local(), include_reason=False, async_mode=False, verbose_mode=False)
    case = LLMTestCase(input=question, actual_output=postmortem_text(pm), retrieval_context=contexts(evidence, pm))
    metric.measure(case)
    return float(metric.score)


async def ragas_faithfulness(pm: dict, evidence: dict, question: str) -> float | None:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness

    scorer = Faithfulness(llm=LangchainLLMWrapper(_chat()))
    sample = SingleTurnSample(user_input=question, response=postmortem_text(pm), retrieved_contexts=contexts(evidence, pm))
    score = await scorer.single_turn_ascore(sample)
    return None if score is None else float(score)
