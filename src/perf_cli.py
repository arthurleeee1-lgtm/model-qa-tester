#!/usr/bin/env python3
"""
Performance Test CLI - Run API infrastructure tests.

Usage:
    python -m src.perf_cli --model deepseek/deepseek-chat-v3.2
    python -m src.perf_cli --config tests/perf_tests.yaml
    python -m src.perf_cli --full -m deepseek/deepseek-chat-v3.2
    python -m src.perf_cli --all
"""

import argparse
import json
import os
import sys
import yaml
from datetime import datetime
from typing import List, Optional, Union

from rich.console import Console

from .config import get_config, get_model_endpoint, MODEL_ENDPOINTS
from .perf import (
    PerfTester, SLOConfig, PerfTestResult, FullPerfResult,
    ConcurrentStats, StabilityStats, TTFBStats
)


def load_perf_config(config_path: str) -> dict:
    """Load performance test configuration from YAML."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_results(results: List[Union[PerfTestResult, FullPerfResult]], output_dir: str, prefix: str = "perf") -> str:
    """Save performance test results to JSON."""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{prefix}_report_{timestamp}.json")
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "total_models": len(results),
        "passed_slo": sum(1 for r in results if r.passed_all_slos()),
        "failed_slo": sum(1 for r in results if not r.passed_all_slos()),
        "results": [r.to_dict() for r in results],
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return output_path


def save_text_results(results: List[Union[PerfTestResult, FullPerfResult]], output_dir: str, full_mode: bool = False) -> str:
    """Save performance test results to a plain text file (matching console output)."""
    from io import StringIO
    from rich.console import Console
    
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "full_perf" if full_mode else "perf"
    output_path = os.path.join(output_dir, f"{prefix}_report_{timestamp}.txt")
    
    # Use a string buffer to capture Rich output
    string_buffer = StringIO()
    text_console = Console(file=string_buffer, width=120, force_terminal=False)
    
    # We'll use the existing PerfTester methods but redirect output
    tester = PerfTester()
    tester.console = text_console # Redirect tester's console
    
    text_console.print(f"\n[bold]═══ {'Full ' if full_mode else ''}Performance Report ═══[/bold]")
    text_console.print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    for r in results:
        if full_mode:
            tester.print_full_result(r)
        else:
            tester.print_result(r)
        text_console.print("\n" + "═"*60 + "\n")
    
    # Print summary table at the end
    if len(results) > 1:
        print_summary(results, full_mode=full_mode, console=text_console)
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(string_buffer.getvalue())
    
    return output_path


def print_summary(results: List[Union[PerfTestResult, FullPerfResult]], full_mode: bool = False, console: Optional[Console] = None) -> None:
    """Print summary of all test results."""
    from rich.table import Table
    
    if console is None:
        from rich.console import Console
        console = Console()
    
    title = "Full Performance Test Summary" if full_mode else "Performance Test Summary"
    console.print(f"\n[bold]═══ {title} ═══[/bold]\n")
    
    table = Table(show_header=True)
    table.add_column("Model", style="cyan")
    table.add_column("P50", justify="right")
    table.add_column("P99", justify="right")
    table.add_column("Error Rate", justify="right")
    
    if full_mode:
        table.add_column("Throughput", justify="right")
        table.add_column("Stability", justify="right")
        table.add_column("TTFB P99", justify="right")
    
    table.add_column("SLO Status", justify="center")
    
    for r in results:
        p50 = f"{r.latency.p50_ms:.0f}ms"
        p99 = f"{r.latency.p99_ms:.0f}ms"
        error_rate = f"{r.errors.error_rate * 100:.1f}%"
        status = "[green]✓ PASS[/green]" if r.passed_all_slos() else "[red]✗ FAIL[/red]"
        
        model_short = r.model.split("/")[-1][:20]
        
        if full_mode and hasattr(r, 'concurrent') and r.concurrent:
            throughput = f"{r.concurrent.throughput_rps:.2f}/s"
            stability = f"{r.stability.stability_score:.0f}" if r.stability else "-"
            ttfb = f"{r.ttfb.p99_ms:.0f}ms" if r.ttfb and r.ttfb.count > 0 else "-"
            table.add_row(model_short, p50, p99, error_rate, throughput, stability, ttfb, status)
        else:
            table.add_row(model_short, p50, p99, error_rate, status)
    
    console.print(table)
    
    passed = sum(1 for r in results if r.passed_all_slos())
    total = len(results)
    console.print(f"\n[bold]Total: {passed}/{total} models passed all SLOs[/bold]\n")


def main():
    parser = argparse.ArgumentParser(
        description="CanopyWave API Performance Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Modes:
  Basic (default):  Latency percentiles + error rate + SLO validation
  Full (--full):    Basic + concurrent + stability + TTFB tests

Examples:
  python -m src.perf_cli -m deepseek/deepseek-chat-v3.2
  python -m src.perf_cli --full -m deepseek/deepseek-chat-v3.2
  python -m src.perf_cli -c tests/perf_tests.yaml --full
  python -m src.perf_cli --all
        """,
    )
    
    parser.add_argument(
        "--model", "-m",
        type=str,
        help="Single model to test",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to performance test config YAML",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Test all configured models",
    )
    parser.add_argument(
        "--full", "-f",
        action="store_true",
        help="Run full test (latency + concurrent + stability + TTFB)",
    )
    parser.add_argument(
        "--warmup", "-w",
        type=int,
        default=3,
        help="Number of warmup requests (default: 3)",
    )
    parser.add_argument(
        "--samples", "-s",
        type=int,
        default=20,
        help="Number of sample requests (default: 20)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="Concurrent requests for throughput test (default: 5)",
    )
    parser.add_argument(
        "--stability-requests",
        type=int,
        default=30,
        help="Number of stability test requests (default: 30)",
    )
    parser.add_argument(
        "--stability-interval",
        type=float,
        default=1.0,
        help="Seconds between stability requests (default: 1.0)",
    )
    parser.add_argument(
        "--ttfb-samples",
        type=int,
        default=10,
        help="Number of TTFB samples (default: 10)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="reports",
        help="Output directory for reports",
    )
    
    args = parser.parse_args()
    
    # Validate config
    config = get_config()
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print("\nPlease set CANOPYWAVE_API_KEY environment variable or create .env file")
        sys.exit(1)
    
    # Determine which models to test
    models_to_test: List[str] = []
    warmup = args.warmup
    samples = args.samples
    
    if args.model:
        models_to_test = [args.model]
    elif args.config:
        perf_config = load_perf_config(args.config)
        models_to_test = perf_config.get("models", [])
        
        # Load test settings from file
        test_settings = perf_config.get("test_settings", {})
        warmup = test_settings.get("warmup_requests", warmup)
        samples = test_settings.get("sample_requests", samples)
    elif args.all:
        models_to_test = list(MODEL_ENDPOINTS.keys())
    else:
        parser.print_help()
        sys.exit(1)
    
    if not models_to_test:
        print("No models specified to test")
        sys.exit(1)
    
    # Create SLO config
    slo_config = SLOConfig()
    if args.config:
        perf_config = load_perf_config(args.config)
        slo_conf = perf_config.get("slo", {})
        slo_config = SLOConfig(
            latency_p50_ms=slo_conf.get("latency_p50_ms", 5000),
            latency_p99_ms=slo_conf.get("latency_p99_ms", 30000),
            error_rate_percent=slo_conf.get("error_rate_percent", 1.0),
            availability_percent=slo_conf.get("availability_percent", 99.9),
            ttfb_p99_ms=slo_conf.get("ttfb_p99_ms", 5000),
            throughput_min_rps=slo_conf.get("throughput_min_rps", 0.1),
            stability_score_min=slo_conf.get("stability_score_min", 80.0),
        )
    
    tester = PerfTester(slo_config=slo_config)
    
    # Run tests
    results: List[Union[PerfTestResult, FullPerfResult]] = []
    
    test_mode = "Full" if args.full else "Basic"
    print(f"\n{test_mode} testing {len(models_to_test)} model(s)...\n")
    
    for model in models_to_test:
        try:
            if args.full:
                # Run full comprehensive test
                result = tester.run_full_test(
                    model=model,
                    warmup_requests=warmup,
                    sample_requests=samples,
                    concurrent_requests=args.concurrent,
                    stability_requests=args.stability_requests,
                    stability_interval=args.stability_interval,
                    ttfb_samples=args.ttfb_samples,
                    show_progress=True,
                )
                tester.print_full_result(result)
            else:
                # Run basic latency test
                result = tester.run_latency_test(
                    model=model,
                    warmup_requests=warmup,
                    sample_requests=samples,
                    show_progress=True,
                )
                tester.print_result(result)
            
            results.append(result)
        except Exception as e:
            print(f"Error testing {model}: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary if multiple models
    if len(results) > 1:
        print_summary(results, full_mode=args.full)
    
    # Save results
    if results:
        prefix = "full_perf" if args.full else "perf"
        json_path = save_results(results, args.output, prefix)
        text_path = save_text_results(results, args.output, args.full)
        print(f"JSON Results saved to: {json_path}")
        print(f"Text Results saved to: {text_path}")
    
    # Exit with error if any SLO failed
    if not all(r.passed_all_slos() for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
