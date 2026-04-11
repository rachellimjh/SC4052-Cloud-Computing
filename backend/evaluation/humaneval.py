"""HumanEval dataset loader.

Loads problems from the OpenAI HumanEval JSONL file and provides
utilities for sampling and formatting prompts for the agent.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "HumanEval.jsonl"


@dataclass
class HumanEvalProblem:
    """A single HumanEval problem."""
    task_id: str           # e.g. "HumanEval/0"
    prompt: str            # function signature + docstring (feed to model)
    entry_point: str       # function name, e.g. "has_close_elements"
    canonical_solution: str  # reference body (4-space indented)
    test: str              # check(candidate) function with asserts


def load_dataset(path: Path = DATASET_PATH) -> list[HumanEvalProblem]:
    """Load all 164 HumanEval problems from the JSONL file."""
    problems = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            problems.append(HumanEvalProblem(
                task_id=d["task_id"],
                prompt=d["prompt"],
                entry_point=d["entry_point"],
                canonical_solution=d["canonical_solution"],
                test=d["test"],
            ))
    return problems


def sample_problems(n: int = 15, seed: int | None = 42) -> list[HumanEvalProblem]:
    """Randomly sample n problems from HumanEval.

    Uses a fixed seed by default so benchmark runs are reproducible.
    """
    problems = load_dataset()
    rng = random.Random(seed)
    return rng.sample(problems, min(n, len(problems)))


def build_agent_prompt(problem: HumanEvalProblem) -> str:
    """Build a natural-language prompt for the agent from a HumanEval problem.

    Instead of asking the agent to complete a function stub (which is how
    Codex was evaluated), we ask it to write a complete Python file — this
    matches how a vibe-coding user would interact with the agent.
    """
    return (
        f"Write a Python file called solution.py that implements the following function.\n"
        f"The function must be named `{problem.entry_point}`.\n"
        f"Here is the function signature and docstring:\n\n"
        f"```python\n{problem.prompt}```\n\n"
        f"Make sure the function is complete and correct. Write ONLY the solution.py file."
    )


def get_reference_solution(problem: HumanEvalProblem) -> str:
    """Get the full reference solution (prompt + canonical body)."""
    return problem.prompt + problem.canonical_solution
