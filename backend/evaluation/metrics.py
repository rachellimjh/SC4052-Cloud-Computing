"""Three-tier evaluation metrics for Coding-as-a-Service.

Tier 1 — Execution Success Rate: Does the generated code run without
         syntax errors, import errors, or runtime crashes?

Tier 2 — Pass@k / Functional Correctness: Out of the code that runs,
         how many pass all assertion tests? Uses the unbiased Pass@k
         estimator from the Codex paper (arXiv:2107.03374).

Tier 3 — CodeBLEU: Out of the code that works, how well does it match
         the style and structure of a reference solution? Combines
         n-gram match, AST match, and data-flow match.
"""

import ast
import math
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Data classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class SampleResult:
    """Evaluation result for a single generated sample."""
    # Tier 1
    executes: bool
    syntax_error: str | None = None

    # Tier 2
    passes_tests: bool = False
    test_error: str | None = None

    # Tier 3
    codebleu: float = 0.0


@dataclass
class TaskReport:
    """Evaluation report for one HumanEval task across n samples."""
    task_id: str
    n_samples: int

    # Tier 1
    execution_success_rate: float = 0.0

    # Tier 2
    pass_at_1: float = 0.0
    pass_at_k: float = 0.0
    functional_correctness: float = 0.0

    # Tier 3
    avg_codebleu: float = 0.0

    samples: list[SampleResult] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tier 1: Execution Success Rate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_execution(code: str, timeout: int = 10) -> tuple[bool, str | None]:
    """Check if code executes without crashing.

    Writes code to a temp file and runs it. Returns (success, error_msg).
    This catches SyntaxError, IndentationError, TypeError, NameError, etc.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return True, None
        # Extract the last line of stderr (the actual error)
        err_lines = result.stderr.strip().split("\n")
        error_msg = err_lines[-1] if err_lines else "Unknown error"
        return False, error_msg
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)
    finally:
        Path(temp_path).unlink(missing_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tier 2: Pass@k / Functional Correctness
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased Pass@k estimator from the Codex paper.

    Args:
        n: Total number of generated samples.
        c: Number of correct samples (passed all tests).
        k: The k in Pass@k.

    Returns:
        1 - C(n-c, k) / C(n, k)
    """
    if n < k:
        return 1.0 if c > 0 else 0.0
    if c == 0:
        return 0.0
    if c >= n:
        return 1.0

    log_prod = 0.0
    for i in range(k):
        log_prod += math.log(n - c - i) - math.log(n - i)
    return 1.0 - math.exp(log_prod)


def run_humaneval_tests(
    code: str, test_code: str, entry_point: str, timeout: int = 10,
) -> tuple[bool, str | None]:
    """Run HumanEval assertion tests against generated code.

    Combines the generated code with the test harness and calls
    check(entry_point) as specified by the HumanEval protocol.
    """
    full_code = code + "\n\n" + test_code + f"\ncheck({entry_point})\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return True, None
        err_lines = result.stderr.strip().split("\n")
        error_msg = err_lines[-1] if err_lines else "Unknown error"
        return False, error_msg
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)
    finally:
        Path(temp_path).unlink(missing_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Tier 3: CodeBLEU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _tokenize(code: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for code."""
    import re
    return re.findall(r"[a-zA-Z_]\w*|[^\s]", code)


def _ngram_match(candidate_tokens: list[str], reference_tokens: list[str], n: int) -> float:
    """Compute n-gram precision (BLEU-style) between candidate and reference."""
    if len(candidate_tokens) < n or len(reference_tokens) < n:
        return 0.0

    cand_ngrams = Counter(
        tuple(candidate_tokens[i:i+n]) for i in range(len(candidate_tokens) - n + 1)
    )
    ref_ngrams = Counter(
        tuple(reference_tokens[i:i+n]) for i in range(len(reference_tokens) - n + 1)
    )

    clipped = sum(min(cand_ngrams[ng], ref_ngrams[ng]) for ng in cand_ngrams)
    total = sum(cand_ngrams.values())
    return clipped / total if total > 0 else 0.0


def _ngram_score(candidate: str, reference: str) -> float:
    """Weighted n-gram match (1-gram through 4-gram, equal weights)."""
    cand_tok = _tokenize(candidate)
    ref_tok = _tokenize(reference)

    if not cand_tok or not ref_tok:
        return 0.0

    scores = []
    for n in range(1, 5):
        scores.append(_ngram_match(cand_tok, ref_tok, n))

    # Brevity penalty (from BLEU)
    bp = min(1.0, math.exp(1 - len(ref_tok) / len(cand_tok))) if cand_tok else 0.0
    return bp * (sum(scores) / len(scores))


def _get_ast_nodes(code: str) -> set[str]:
    """Extract the set of AST node type names from code."""
    try:
        tree = ast.parse(code)
        return {type(node).__name__ for node in ast.walk(tree)}
    except SyntaxError:
        return set()


def _ast_match(candidate: str, reference: str) -> float:
    """Compute AST structure similarity (Jaccard index of node types)."""
    cand_nodes = _get_ast_nodes(candidate)
    ref_nodes = _get_ast_nodes(reference)
    if not cand_nodes or not ref_nodes:
        return 0.0
    intersection = cand_nodes & ref_nodes
    union = cand_nodes | ref_nodes
    return len(intersection) / len(union)


def _get_data_flow(code: str) -> set[tuple[str, str]]:
    """Extract variable-to-operation edges as a proxy for data flow.

    For each assignment like `x = foo(y)`, we extract edges:
    ("x", "Store") and ("foo", "Call"), etc.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()

    edges = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            ctx = type(node.ctx).__name__  # Load, Store, Del
            edges.add((node.id, ctx))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                edges.add((node.func.id, "Call"))
            elif isinstance(node.func, ast.Attribute):
                edges.add((node.func.attr, "Call"))
    return edges


def _data_flow_match(candidate: str, reference: str) -> float:
    """Compute data-flow similarity (Jaccard index of variable-operation edges)."""
    cand_df = _get_data_flow(candidate)
    ref_df = _get_data_flow(reference)
    if not cand_df or not ref_df:
        return 0.0
    intersection = cand_df & ref_df
    union = cand_df | ref_df
    return len(intersection) / len(union)


def compute_codebleu(candidate: str, reference: str) -> float:
    """Compute CodeBLEU score (0.0 to 1.0).

    CodeBLEU = alpha * ngram_match
             + beta  * ast_match
             + gamma * data_flow_match

    Weights from the original CodeBLEU paper (Ren et al., 2020):
    alpha=0.25, beta=0.25, gamma=0.25, plus 0.25 for weighted ngrams.
    We simplify to equal 1/3 weights across the three components.
    """
    ngram = _ngram_score(candidate, reference)
    ast_m = _ast_match(candidate, reference)
    df_m = _data_flow_match(candidate, reference)

    score = (ngram + ast_m + df_m) / 3.0
    return round(score, 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Full evaluation pipeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_task(
    task_id: str,
    samples: list[str],
    test_code: str,
    entry_point: str,
    reference: str,
    k: int = 5,
) -> TaskReport:
    """Run all 3 tiers of evaluation on generated samples for one task.

    Args:
        task_id: HumanEval task identifier.
        samples: List of generated code strings.
        test_code: The check(candidate) test function from HumanEval.
        entry_point: The function name being tested.
        reference: The canonical/reference solution.
        k: The k for Pass@k.
    """
    n = len(samples)
    results = []
    exec_count = 0
    pass_count = 0
    codebleu_sum = 0.0

    for code in samples:
        sr = SampleResult(executes=False)

        # Tier 1: Does it run?
        executes, exec_err = check_execution(code)
        sr.executes = executes
        sr.syntax_error = exec_err
        if executes:
            exec_count += 1

        # Tier 2: Does it pass tests? (only if it executes)
        if executes:
            passes, test_err = run_humaneval_tests(code, test_code, entry_point)
            sr.passes_tests = passes
            sr.test_error = test_err
            if passes:
                pass_count += 1

        # Tier 3: CodeBLEU (compute for all samples, even failing ones)
        sr.codebleu = compute_codebleu(code, reference)
        codebleu_sum += sr.codebleu

        results.append(sr)

    return TaskReport(
        task_id=task_id,
        n_samples=n,
        execution_success_rate=round(exec_count / n, 4) if n > 0 else 0.0,
        pass_at_1=round(pass_at_k(n, pass_count, 1), 4),
        pass_at_k=round(pass_at_k(n, pass_count, min(k, n)), 4),
        functional_correctness=round(pass_count / n, 4) if n > 0 else 0.0,
        avg_codebleu=round(codebleu_sum / n, 4) if n > 0 else 0.0,
        samples=results,
    )
