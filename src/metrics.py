"""
Evaluation Metrics for Model Quality Assessment.

Supports multiple evaluation dimensions:
- Correctness (exact_match, contains)
- Semantic Similarity (BERTScore, cosine similarity)
- Text Quality (BLEU, ROUGE)
- Fluency & Coherence
- Composite Scoring
"""

import re
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from enum import Enum


class MetricType(Enum):
    """Types of evaluation metrics."""
    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    CONTAINS_ANY = "contains_any"
    REGEX_MATCH = "regex_match"
    SEMANTIC_SIMILARITY = "ss_score"
    BLEU = "bleu"
    ROUGE = "rouge"
    COMPOSITE = "composite"


@dataclass
class EvaluationResult:
    """Result of an evaluation."""
    score: float  # 0.0 to 1.0
    passed: bool
    metric_type: str
    details: Dict[str, Any] = field(default_factory=dict)
    verdict: str = ""
    
    def __post_init__(self):
        if not self.verdict:
            self.verdict = "PASS" if self.passed else "FAIL"


class MetricEvaluator:
    """
    Evaluates model responses using various metrics.
    """
    
    def __init__(self, embedder_model: str = "all-mpnet-base-v2"):
        self._embedder = None
        self._embedder_model = embedder_model
    
    @property
    def embedder(self):
        """Lazy-load sentence transformer model."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self._embedder_model)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for semantic similarity. "
                    "Install with: pip install sentence-transformers"
                )
        return self._embedder
    
    def exact_match(
        self,
        response: str,
        expected: str,
        normalize: bool = True,
        **kwargs
    ) -> EvaluationResult:
        """
        Check if response exactly matches expected value.
        
        Args:
            response: Model response text
            expected: Expected exact match
            normalize: If True, normalize whitespace and case
        """
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.EXACT_MATCH.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        
        if normalize:
            resp_norm = self._normalize(response)
            exp_norm = self._normalize(expected)
            # Also check if expected is contained in response (for math answers)
            matched = exp_norm == resp_norm or exp_norm in resp_norm
        else:
            matched = expected == response or expected in response
        
        return EvaluationResult(
            score=1.0 if matched else 0.0,
            passed=matched,
            metric_type=MetricType.EXACT_MATCH.value,
            details={"expected": expected, "response_preview": response[:200]}
        )
    
    def contains(
        self,
        response: str,
        keywords: str | List[str],
        case_sensitive: bool = False,
        **kwargs
    ) -> EvaluationResult:
        """
        Check if response contains all specified keywords.
        
        Args:
            response: Model response text
            keywords: Keyword(s) to check for
            case_sensitive: Whether to match case
        """
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.CONTAINS.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        
        if isinstance(keywords, str):
            keywords = [keywords]
        
        check_response = response if case_sensitive else response.lower()
        
        found = []
        missing = []
        
        for kw in keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in check_response:
                found.append(kw)
            else:
                missing.append(kw)
        
        score = len(found) / len(keywords) if keywords else 0
        passed = len(missing) == 0
        
        return EvaluationResult(
            score=score,
            passed=passed,
            metric_type=MetricType.CONTAINS.value,
            details={"found": found, "missing": missing}
        )
    
    def contains_any(
        self,
        response: str,
        keywords: List[str],
        case_sensitive: bool = False,
        **kwargs
    ) -> EvaluationResult:
        """Check if response contains at least one of the keywords."""
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.CONTAINS_ANY.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        
        check_response = response if case_sensitive else response.lower()
        
        for kw in keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in check_response:
                return EvaluationResult(
                    score=1.0,
                    passed=True,
                    metric_type=MetricType.CONTAINS_ANY.value,
                    details={"matched": kw}
                )
        
        return EvaluationResult(
            score=0.0,
            passed=False,
            metric_type=MetricType.CONTAINS_ANY.value,
            details={"keywords": keywords}
        )
    
    def regex_match(
        self,
        response: str,
        pattern: str,
        **kwargs
    ) -> EvaluationResult:
        """Check if response matches a regex pattern."""
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.REGEX_MATCH.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        try:
            match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
            matched = match is not None
            
            return EvaluationResult(
                score=1.0 if matched else 0.0,
                passed=matched,
                metric_type=MetricType.REGEX_MATCH.value,
                details={
                    "pattern": pattern,
                    "matched_text": match.group() if match else None
                }
            )
        except re.error as e:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.REGEX_MATCH.value,
                details={"error": f"Invalid regex: {e}"}
            )
    
    def semantic_similarity(
        self,
        response: str,
        reference: str,
        threshold: float = 0.7,
        **kwargs
    ) -> EvaluationResult:
        """
        Calculate semantic similarity using sentence embeddings.
        
        Args:
            response: Model response text
            reference: Reference text for comparison
            threshold: Minimum score to pass (0.0 to 1.0)
        """
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.SEMANTIC_SIMILARITY.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        try:
            from sentence_transformers import util
            
            vec1 = self.embedder.encode(response, convert_to_tensor=True)
            vec2 = self.embedder.encode(reference, convert_to_tensor=True)
            
            score = float(util.cos_sim(vec1, vec2).item())
            # Normalize score to 0-1 range (cosine sim ranges from -1 to 1)
            normalized_score = (score + 1) / 2
            
            return EvaluationResult(
                score=normalized_score,
                passed=normalized_score >= threshold,
                metric_type=MetricType.SEMANTIC_SIMILARITY.value,
                details={
                    "raw_cosine_sim": score,
                    "threshold": threshold,
                    "reference_preview": reference[:100]
                }
            )
        except Exception as e:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.SEMANTIC_SIMILARITY.value,
                details={"error": str(e)}
            )
    
    def bleu_score(
        self,
        response: str,
        reference: str,
        threshold: float = 0.3,
        **kwargs
    ) -> EvaluationResult:
        """
        Calculate BLEU score for response vs reference.
        
        Uses simple n-gram overlap calculation.
        """
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.BLEU.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        try:
            # Simple BLEU implementation
            response_tokens = response.lower().split()
            reference_tokens = reference.lower().split()
            
            if not response_tokens or not reference_tokens:
                return EvaluationResult(
                    score=0.0,
                    passed=False,
                    metric_type=MetricType.BLEU.value,
                    details={"error": "Empty text"}
                )
            
            # Calculate n-gram precision for n=1,2,3,4
            precisions = []
            for n in range(1, min(5, len(response_tokens) + 1)):
                resp_ngrams = self._get_ngrams(response_tokens, n)
                ref_ngrams = self._get_ngrams(reference_tokens, n)
                
                if not resp_ngrams:
                    break
                    
                matches = sum(1 for ng in resp_ngrams if ng in ref_ngrams)
                precision = matches / len(resp_ngrams)
                precisions.append(precision)
            
            if not precisions:
                score = 0.0
            else:
                # Geometric mean of precisions
                log_precisions = [np.log(p + 1e-10) for p in precisions]
                score = np.exp(np.mean(log_precisions))
            
            # Brevity penalty
            bp = min(1.0, np.exp(1 - len(reference_tokens) / max(len(response_tokens), 1)))
            score *= bp
            
            return EvaluationResult(
                score=score,
                passed=score >= threshold,
                metric_type=MetricType.BLEU.value,
                details={
                    "brevity_penalty": bp,
                    "precisions": precisions,
                    "threshold": threshold
                }
            )
        except Exception as e:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.BLEU.value,
                details={"error": str(e)}
            )
    
    def rouge_score(
        self,
        response: str,
        reference: str,
        threshold: float = 0.3,
        **kwargs
    ) -> EvaluationResult:
        """
        Calculate ROUGE-L score (longest common subsequence).
        """
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.ROUGE.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        try:
            response_tokens = response.lower().split()
            reference_tokens = reference.lower().split()
            
            if not response_tokens or not reference_tokens:
                return EvaluationResult(
                    score=0.0,
                    passed=False,
                    metric_type=MetricType.ROUGE.value,
                    details={"error": "Empty text"}
                )
            
            # Calculate LCS length
            lcs_length = self._lcs_length(response_tokens, reference_tokens)
            
            # ROUGE-L uses F1 of LCS-based precision and recall
            precision = lcs_length / len(response_tokens) if response_tokens else 0
            recall = lcs_length / len(reference_tokens) if reference_tokens else 0
            
            if precision + recall > 0:
                f1 = 2 * precision * recall / (precision + recall)
            else:
                f1 = 0.0
            
            return EvaluationResult(
                score=f1,
                passed=f1 >= threshold,
                metric_type=MetricType.ROUGE.value,
                details={
                    "precision": precision,
                    "recall": recall,
                    "lcs_length": lcs_length,
                    "threshold": threshold
                }
            )
        except Exception as e:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.ROUGE.value,
                details={"error": str(e)}
            )
    
    def composite_score(
        self,
        response: str,
        reference: str,
        weights: Optional[Dict[str, float]] = None,
        **kwargs
    ) -> EvaluationResult:
        """
        Calculate composite score using multiple metrics.
        
        Default weights:
        - Correctness (semantic similarity): 0.4
        - Relevance (contains key concepts): 0.2
        - Faithfulness (ROUGE): 0.15
        - Fluency (length/coherence proxy): 0.15
        - Diversity: 0.1
        """
        # Handle None response
        if response is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=MetricType.COMPOSITE.value,
                details={"error": "Response is None"},
                verdict="ERROR"
            )
        if weights is None:
            weights = {
                "semantic": 0.4,
                "relevance": 0.2,
                "faithfulness": 0.15,
                "fluency": 0.15,
                "diversity": 0.1
            }
        
        scores = {}
        
        # Semantic similarity
        ss_result = self.semantic_similarity(response, reference)
        scores["semantic"] = ss_result.score
        
        # ROUGE as faithfulness proxy
        rouge_result = self.rouge_score(response, reference)
        scores["faithfulness"] = rouge_result.score
        
        # Length ratio as fluency proxy (penalize too short or too long)
        len_ratio = len(response) / max(len(reference), 1)
        fluency = 1.0 - min(abs(1.0 - len_ratio), 1.0) * 0.5
        scores["fluency"] = fluency
        
        # Word diversity (unique words ratio)
        words = response.lower().split()
        if words:
            diversity = len(set(words)) / len(words)
        else:
            diversity = 0
        scores["diversity"] = diversity
        
        # Relevance (BLEU as proxy)
        bleu_result = self.bleu_score(response, reference)
        scores["relevance"] = bleu_result.score
        
        # Calculate weighted composite
        composite = sum(scores.get(k, 0) * w for k, w in weights.items())
        
        return EvaluationResult(
            score=composite,
            passed=composite >= 0.5,
            metric_type=MetricType.COMPOSITE.value,
            details={
                "component_scores": scores,
                "weights": weights
            }
        )
    
    def evaluate(
        self,
        response: str,
        expected: str,
        metric: str,
        **kwargs
    ) -> EvaluationResult:
        """
        Evaluate response using specified metric.
        
        Args:
            response: Model response text
            expected: Expected value or reference
            metric: Metric type (exact_match, contains, ss_score, etc.)
            **kwargs: Additional metric-specific arguments
        """
        metric_map: Dict[str, Callable] = {
            "exact_match": self.exact_match,
            "contains": self.contains,
            "contains_any": self.contains_any,
            "regex_match": self.regex_match,
            "ss_score": self.semantic_similarity,
            "semantic_similarity": self.semantic_similarity,
            "bleu": self.bleu_score,
            "rouge": self.rouge_score,
            "composite": self.composite_score,
        }
        
        evaluator = metric_map.get(metric.lower())
        
        if evaluator is None:
            return EvaluationResult(
                score=0.0,
                passed=False,
                metric_type=metric,
                details={"error": f"Unknown metric: {metric}"}
            )
        
        # For contains metrics, expected might be a string or list
        if metric.lower() in ("contains", "contains_any"):
            return evaluator(response, expected, **kwargs)
        elif metric.lower() in ("ss_score", "semantic_similarity", "bleu", "rouge", "composite"):
            return evaluator(response, expected, **kwargs)
        else:
            return evaluator(response, expected, **kwargs)
    
    # Helper methods
    
    def _normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        # Remove extra whitespace
        text = " ".join(text.split())
        # Lowercase
        text = text.lower()
        # Remove common punctuation for numeric comparisons
        text = re.sub(r'[,\.\:\;\!\?\-]', '', text)
        return text.strip()
    
    def _get_ngrams(self, tokens: List[str], n: int) -> List[Tuple[str, ...]]:
        """Get n-grams from token list."""
        return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]
    
    def _lcs_length(self, a: List[str], b: List[str]) -> int:
        """Calculate longest common subsequence length."""
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        return dp[m][n]


# Convenience function
def evaluate(
    resp: Dict[str, Any],
    expected: str,
    metric: str,
    **kwargs
) -> Tuple[float, str]:
    """
    Convenience function for evaluating API response.
    
    Args:
        resp: API response dict
        expected: Expected value
        metric: Metric type
        
    Returns:
        Tuple of (score, verdict)
    """
    # Extract text from response
    if "error" in resp:
        return 0.0, "ERROR"
    
    try:
        text = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return 0.0, "ERROR"
    
    evaluator = MetricEvaluator()
    result = evaluator.evaluate(text, expected, metric, **kwargs)
    
    return result.score, result.verdict


class LatencyStats:
    """Calculate latency statistics from a list of latencies."""
    
    def __init__(self, latencies: List[float]):
        self.latencies = sorted(latencies)
        self.count = len(latencies)
    
    @property
    def min(self) -> float:
        return self.latencies[0] if self.latencies else 0
    
    @property
    def max(self) -> float:
        return self.latencies[-1] if self.latencies else 0
    
    @property
    def mean(self) -> float:
        return np.mean(self.latencies) if self.latencies else 0
    
    @property
    def median(self) -> float:
        return np.median(self.latencies) if self.latencies else 0
    
    @property
    def p50(self) -> float:
        return self._percentile(50)
    
    @property
    def p90(self) -> float:
        return self._percentile(90)
    
    @property
    def p95(self) -> float:
        return self._percentile(95)
    
    @property
    def p99(self) -> float:
        return self._percentile(99)
    
    def _percentile(self, p: float) -> float:
        if not self.latencies:
            return 0
        return float(np.percentile(self.latencies, p))
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "median": self.median,
            "p50": self.p50,
            "p90": self.p90,
            "p95": self.p95,
            "p99": self.p99,
        }
