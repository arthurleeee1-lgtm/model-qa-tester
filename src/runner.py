"""
Test Runner - Main orchestrator for model testing.

Loads test cases from YAML, executes tests, collects metrics, and generates reports.
"""

import argparse
import json
import os
import sys
import yaml
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from .config import get_config, Config
from .invoker import ModelInvoker, InvokeResult
from .metrics import MetricEvaluator, EvaluationResult, LatencyStats


console = Console()


@dataclass
class TestCase:
    """A single test case definition."""
    id: str
    prompt: str
    metric: str = "contains"
    expected: str = ""
    reference: str = ""
    threshold: float = 0.7
    model: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.7
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Use reference as expected if expected is empty
        if not self.expected and self.reference:
            self.expected = self.reference


@dataclass
class TestResult:
    """Result of a single test execution."""
    test_id: str
    prompt: str
    model: str
    latency: float
    score: float
    passed: bool
    verdict: str
    metric_type: str
    response_content: str = ""
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestSuiteResult:
    """Aggregated results from a test suite run."""
    suite_name: str
    timestamp: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    pass_rate: float
    avg_latency: float
    latency_stats: Dict[str, float]
    results: List[TestResult]
    models_tested: List[str]
    duration_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "timestamp": self.timestamp,
            "summary": {
                "total_tests": self.total_tests,
                "passed_tests": self.passed_tests,
                "failed_tests": self.failed_tests,
                "error_tests": self.error_tests,
                "pass_rate": self.pass_rate,
                "avg_latency": self.avg_latency,
                "duration_seconds": self.duration_seconds,
            },
            "latency_stats": self.latency_stats,
            "models_tested": self.models_tested,
            "results": [r.to_dict() for r in self.results],
        }


class TestRunner:
    """
    Orchestrates test execution and result collection.
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        models: Optional[List[str]] = None,
    ):
        self.config = config or get_config()
        self.models = models or [self.config.default_model]
        self.invoker = ModelInvoker()
        self.evaluator = MetricEvaluator()
    
    def load_tests(self, config_path: str) -> tuple[List[TestCase], List[str]]:
        """Load test cases from YAML file and return (tests, models)."""
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        tests = []
        for t in data.get("tests", []):
            tests.append(TestCase(**t))
        
        # Load models from config if present
        models = data.get("models", [])
        if not models and data.get("config"):
            # Check for single default_model
            default = data.get("config", {}).get("default_model")
            if default:
                models = [default]
                
        return tests, models
    
    def run_single_test(
        self,
        test: TestCase,
        model: str,
    ) -> TestResult:
        """Execute a single test case."""
        # Invoke the model
        result = self.invoker.invoke(
            prompt=test.prompt,
            model=model,
            max_tokens=test.max_tokens,
            temperature=test.temperature,
        )
        
        if not result.success:
            return TestResult(
                test_id=test.id,
                prompt=test.prompt,
                model=model,
                latency=result.latency,
                score=0.0,
                passed=False,
                verdict="ERROR",
                metric_type=test.metric,
                error=result.error,
            )
        
        # Evaluate the response
        eval_result = self.evaluator.evaluate(
            response=result.content,
            expected=test.expected,
            metric=test.metric,
            threshold=test.threshold,
        )
        
        return TestResult(
            test_id=test.id,
            prompt=test.prompt,
            model=model,
            latency=result.latency,
            score=eval_result.score,
            passed=eval_result.passed,
            verdict=eval_result.verdict,
            metric_type=eval_result.metric_type,
            response_content=(result.content or "")[:500],  # Truncate for storage
            details=eval_result.details,
        )
    
    def run_suite(
        self,
        tests: List[TestCase],
        suite_name: str = "QA Test Suite",
        show_progress: bool = True,
    ) -> TestSuiteResult:
        """Run all tests in the suite."""
        start_time = datetime.now()
        results: List[TestResult] = []
        
        total_runs = len(tests) * len(self.models)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            disable=not show_progress,
        ) as progress:
            task = progress.add_task("Running tests...", total=total_runs)
            
            for test in tests:
                test_models = [test.model] if test.model else self.models
                
                for model in test_models:
                    progress.update(task, description=f"Testing {test.id} on {model.split('/')[-1]}")
                    
                    result = self.run_single_test(test, model)
                    results.append(result)
                    
                    progress.advance(task)
        
        # Calculate aggregate statistics
        duration = (datetime.now() - start_time).total_seconds()
        latencies = [r.latency for r in results if r.verdict != "ERROR"]
        latency_stats = LatencyStats(latencies)
        
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed and r.verdict != "ERROR")
        errors = sum(1 for r in results if r.verdict == "ERROR")
        
        return TestSuiteResult(
            suite_name=suite_name,
            timestamp=datetime.now().isoformat(),
            total_tests=len(results),
            passed_tests=passed,
            failed_tests=failed,
            error_tests=errors,
            pass_rate=passed / len(results) if results else 0,
            avg_latency=latency_stats.mean,
            latency_stats=latency_stats.to_dict(),
            results=results,
            models_tested=list(set(r.model for r in results)),
            duration_seconds=duration,
        )
    
    def print_summary(self, suite_result: TestSuiteResult):
        """Print a summary table to console."""
        console.print()
        console.print(f"[bold blue]═══ {suite_result.suite_name} ═══[/bold blue]")
        console.print()
        
        # Summary stats
        table = Table(title="Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Total Tests", str(suite_result.total_tests))
        table.add_row("Passed", f"[green]{suite_result.passed_tests}[/green]")
        table.add_row("Failed", f"[red]{suite_result.failed_tests}[/red]")
        table.add_row("Errors", f"[yellow]{suite_result.error_tests}[/yellow]")
        table.add_row("Pass Rate", f"{suite_result.pass_rate:.1%}")
        table.add_row("Avg Latency", f"{suite_result.avg_latency:.2f}s")
        table.add_row("P50 Latency", f"{suite_result.latency_stats['p50']:.2f}s")
        table.add_row("P99 Latency", f"{suite_result.latency_stats['p99']:.2f}s")
        table.add_row("Duration", f"{suite_result.duration_seconds:.1f}s")
        
        console.print(table)
        
        # Results table
        console.print()
        results_table = Table(title="Test Results")
        results_table.add_column("ID", style="cyan", max_width=20)
        results_table.add_column("Model", max_width=25)
        results_table.add_column("Latency", justify="right")
        results_table.add_column("Score", justify="right")
        results_table.add_column("Verdict")
        
        for r in suite_result.results:
            verdict_style = "green" if r.passed else ("yellow" if r.verdict == "ERROR" else "red")
            model_short = r.model.split("/")[-1][:20]
            
            results_table.add_row(
                r.test_id[:20],
                model_short,
                f"{r.latency:.2f}s",
                f"{r.score:.2f}",
                f"[{verdict_style}]{r.verdict}[/{verdict_style}]"
            )
        
        console.print(results_table)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CanopyWave Model Tester - QA Testing Platform"
    )
    parser.add_argument(
        "--config", "-c",
        default="tests/qa_tests.yaml",
        help="Path to test configuration YAML file"
    )
    parser.add_argument(
        "--output", "-o",
        default="reports",
        help="Output directory for reports"
    )
    parser.add_argument(
        "--model", "-m",
        action="append",
        help="Model(s) to test (can be specified multiple times)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["html", "json", "markdown", "all"],
        default="all",
        help="Output format for reports"
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar"
    )
    
    args = parser.parse_args()
    
    # Validate config
    config = get_config()
    errors = config.validate()
    if errors:
        console.print("[red]Configuration errors:[/red]")
        for e in errors:
            console.print(f"  - {e}")
        console.print("\nPlease set CANOPYWAVE_API_KEY environment variable or create .env file")
        sys.exit(1)
    
    # Check if test file exists
    if not os.path.exists(args.config):
        console.print(f"[red]Test configuration file not found: {args.config}[/red]")
        sys.exit(1)
    
    # Setup runner
    models = args.model if args.model else None
    runner = TestRunner(models=models)
    
    # Load and run tests
    console.print(f"[blue]Loading tests from {args.config}...[/blue]")
    tests, config_models = runner.load_tests(args.config)
    console.print(f"[blue]Found {len(tests)} test cases[/blue]")
    
    # Use models from CLI, or config file, or default
    if args.model:
        runner.models = args.model
    elif config_models:
        runner.models = config_models
    
    suite_result = runner.run_suite(
        tests,
        suite_name=Path(args.config).stem,
        show_progress=not args.no_progress,
    )
    
    # Print summary
    runner.print_summary(suite_result)
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    # Generate reports
    from .report import ReportGenerator
    generator = ReportGenerator(output_dir=args.output)
    
    formats = ["html", "json", "markdown"] if args.format == "all" else [args.format]
    
    for fmt in formats:
        if fmt == "html":
            path = generator.generate_html(suite_result)
            console.print(f"[green]HTML report: {path}[/green]")
        elif fmt == "json":
            path = generator.generate_json(suite_result)
            console.print(f"[green]JSON report: {path}[/green]")
        elif fmt == "markdown":
            path = generator.generate_markdown(suite_result)
            console.print(f"[green]Markdown report: {path}[/green]")
    
    # Always generate text table report
    text_path = generator.generate_text_table(suite_result)
    console.print(f"[green]Text table report: {text_path}[/green]")
    
    # Exit with appropriate code
    sys.exit(0 if suite_result.failed_tests == 0 and suite_result.error_tests == 0 else 1)


if __name__ == "__main__":
    main()
