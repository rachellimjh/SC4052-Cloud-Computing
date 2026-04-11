"""Benchmark script — evaluate VibeCoder against HumanEval.

Samples problems from the OpenAI HumanEval dataset, sends each to the
agent, collects the generated code, and measures three tiers of quality:

  Tier 1 — Execution Success Rate  (does it run?)
  Tier 2 — Pass@k                  (does it pass all tests?)
  Tier 3 — CodeBLEU                (is it well-written?)

Usage:
    python benchmark.py                    # 15 random problems, 3 samples each
    python benchmark.py --problems 10      # 10 problems
    python benchmark.py --samples 5        # 5 samples per problem
    python benchmark.py --k 10             # Pass@10
    python benchmark.py --seed 123         # different random sample

Results are printed as a table and saved to benchmark_results.json.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from backend.agent.loop import AgentLoop
from backend.agent.providers.base import Provider
from backend.agent.providers.claude import ClaudeProvider
from backend.agent.providers.gemini import GeminiProvider
from backend.agent.tools.read_file import ReadFileTool
from backend.agent.tools.write_file import WriteFileTool
from backend.agent.tools.list_files import ListFilesTool
from backend.agent.tools.run_code import RunCodeTool
from backend.evaluation.humaneval import (
    sample_problems,
    build_agent_prompt,
    get_reference_solution,
    HumanEvalProblem,
)
from backend.evaluation.metrics import evaluate_task

load_dotenv()


def get_provider() -> Provider:
    """Build the LLM provider from environment variables."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if gemini_key:
        print(f"Provider: Gemini")
        return GeminiProvider(api_key=gemini_key)
    elif anthropic_key:
        print(f"Provider: Claude")
        return ClaudeProvider(api_key=anthropic_key)
    else:
        print("Error: Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env")
        sys.exit(1)


def generate_sample(provider: Provider, problem: HumanEvalProblem, workspace: Path) -> str | None:
    """Ask the agent to solve a HumanEval problem and return the generated code."""
    # Clean workspace
    for f in workspace.iterdir():
        if f.is_file():
            f.unlink()

    tools = [
        ReadFileTool(workspace),
        WriteFileTool(workspace),
        ListFilesTool(workspace),
        RunCodeTool(workspace),
    ]
    agent = AgentLoop(provider=provider, tools=tools)
    prompt = build_agent_prompt(problem)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(agent.run(prompt, []))
    except Exception as e:
        print(f"    Agent error: {e}")
        return None
    finally:
        loop.close()

    # Read generated file
    target = workspace / "solution.py"
    if target.exists():
        return target.read_text(encoding="utf-8")

    # Fallback: check if any .py file was written
    py_files = list(workspace.glob("*.py"))
    if py_files:
        return py_files[0].read_text(encoding="utf-8")
    return None


def run_benchmark(
    num_problems: int = 15,
    num_samples: int = 3,
    k: int = 5,
    seed: int = 42,
):
    """Run the full benchmark pipeline."""
    provider = get_provider()
    problems = sample_problems(n=num_problems, seed=seed)
    workspace = Path("workspaces/_benchmark")
    workspace.mkdir(parents=True, exist_ok=True)

    print(f"Problems: {len(problems)}, Samples/problem: {num_samples}, k={k}, seed={seed}\n")

    all_reports = []

    for idx, problem in enumerate(problems):
        print(f"[{idx+1}/{len(problems)}] {problem.task_id} — {problem.entry_point}")

        samples = []
        for i in range(num_samples):
            print(f"  Sample {i+1}/{num_samples}...", end=" ", flush=True)
            start = time.time()
            code = generate_sample(provider, problem, workspace)
            elapsed = time.time() - start

            if code:
                samples.append(code)
                print(f"OK ({elapsed:.1f}s)")
            else:
                print(f"FAILED to generate ({elapsed:.1f}s)")

        if not samples:
            print("  No samples generated, skipping.")
            all_reports.append({
                "task_id": problem.task_id,
                "entry_point": problem.entry_point,
                "n_samples": 0,
                "tier1_execution_success": 0.0,
                "tier2_pass_at_1": 0.0,
                "tier2_pass_at_k": 0.0,
                "tier2_functional_correctness": 0.0,
                "tier3_codebleu": 0.0,
            })
            continue

        # Evaluate all 3 tiers
        reference = get_reference_solution(problem)
        report = evaluate_task(
            task_id=problem.task_id,
            samples=samples,
            test_code=problem.test,
            entry_point=problem.entry_point,
            reference=reference,
            k=k,
        )

        # Print per-task results
        print(f"  Tier 1 — Execution:  {report.execution_success_rate*100:.0f}%")
        print(f"  Tier 2 — Pass@1:     {report.pass_at_1*100:.1f}%")
        print(f"  Tier 2 — Correctness:{report.functional_correctness*100:.0f}%")
        print(f"  Tier 3 — CodeBLEU:   {report.avg_codebleu:.3f}")

        for i, sr in enumerate(report.samples):
            exec_s = "runs" if sr.executes else f"crash({sr.syntax_error})"
            test_s = "PASS" if sr.passes_tests else f"FAIL"
            if sr.test_error and not sr.passes_tests:
                test_s += f"({sr.test_error[:40]})"
            print(f"    Sample {i+1}: {exec_s} | {test_s} | BLEU={sr.codebleu:.3f}")

        all_reports.append({
            "task_id": problem.task_id,
            "entry_point": problem.entry_point,
            "n_samples": report.n_samples,
            "tier1_execution_success": report.execution_success_rate,
            "tier2_pass_at_1": report.pass_at_1,
            "tier2_pass_at_k": report.pass_at_k,
            "tier2_functional_correctness": report.functional_correctness,
            "tier3_codebleu": report.avg_codebleu,
            "samples": [
                {
                    "executes": s.executes,
                    "passes_tests": s.passes_tests,
                    "codebleu": s.codebleu,
                    "error": s.syntax_error or s.test_error,
                }
                for s in report.samples
            ],
        })

    return all_reports


def print_summary(reports: list[dict], k: int):
    """Print a summary table for the report."""
    print(f"\n{'='*80}")
    print("BENCHMARK RESULTS — VibeCoder on HumanEval")
    print(f"{'='*80}")
    print(
        f"{'Task':<28} {'Exec%':>6} {'Pass@1':>7} {'Pass@k':>7} "
        f"{'Corr%':>6} {'BLEU':>6}"
    )
    print(f"{'-'*28} {'-'*6} {'-'*7} {'-'*7} {'-'*6} {'-'*6}")

    sums = {k: 0.0 for k in ["exec", "p1", "pk", "fc", "cb"]}
    n = len(reports)

    for r in reports:
        name = f"{r['entry_point']}"
        print(
            f"{name:<28} "
            f"{r['tier1_execution_success']*100:>5.0f}% "
            f"{r['tier2_pass_at_1']*100:>6.1f}% "
            f"{r['tier2_pass_at_k']*100:>6.1f}% "
            f"{r['tier2_functional_correctness']*100:>5.0f}% "
            f"{r['tier3_codebleu']:>6.3f}"
        )
        sums["exec"] += r["tier1_execution_success"]
        sums["p1"] += r["tier2_pass_at_1"]
        sums["pk"] += r["tier2_pass_at_k"]
        sums["fc"] += r["tier2_functional_correctness"]
        sums["cb"] += r["tier3_codebleu"]

    if n > 0:
        print(f"{'-'*28} {'-'*6} {'-'*7} {'-'*7} {'-'*6} {'-'*6}")
        print(
            f"{'AVERAGE':<28} "
            f"{sums['exec']/n*100:>5.0f}% "
            f"{sums['p1']/n*100:>6.1f}% "
            f"{sums['pk']/n*100:>6.1f}% "
            f"{sums['fc']/n*100:>5.0f}% "
            f"{sums['cb']/n:>6.3f}"
        )

    print(f"\nTier 1: Execution Success Rate — does the code run without errors?")
    print(f"Tier 2: Pass@1 / Pass@{k} / Functional Correctness — does it pass all tests?")
    print(f"Tier 3: CodeBLEU — does it match expert style and structure?")


def main():
    parser = argparse.ArgumentParser(description="Benchmark VibeCoder on HumanEval")
    parser.add_argument("--problems", type=int, default=15, help="Number of HumanEval problems (default: 15)")
    parser.add_argument("--samples", type=int, default=3, help="Samples per problem (default: 3)")
    parser.add_argument("--k", type=int, default=5, help="k for Pass@k (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    print("VibeCoder Benchmark — HumanEval Dataset")
    print("=" * 40)

    reports = run_benchmark(
        num_problems=args.problems,
        num_samples=args.samples,
        k=args.k,
        seed=args.seed,
    )

    print_summary(reports, args.k)

    out_path = Path("benchmark_results.json")
    out_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()
