"""
Run all 8 demo scenarios in sequence with pauses between each.
Usage: python demo/run_all.py [--scenarios 1 3 5]
"""
import argparse
import importlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "financeflow"))

BOLD  = "\033[1m"; CYAN = "\033[96m"; GREEN = "\033[92m"; RESET = "\033[0m"

SCENARIOS = {
    1: ("scenario_1_clean",            "Clean Traffic — All FAST_PATH"),
    2: ("scenario_2_rbac",             "RBAC Violation — OPA BLOCK"),
    3: ("scenario_3_injection_input",  "Direct Prompt Injection — Instant Kill"),
    4: ("scenario_4_injection_output", "Indirect Injection via Tool Output"),
    5: ("scenario_5_exfiltration",     "Data Exfiltration Chain"),
    6: ("scenario_6_domain_block",     "Malicious Domain / Shell Command"),
    7: ("scenario_7_rate_limit",       "Rate Limiting — Burst"),
    8: ("scenario_8_degradation",      "Graceful Degradation"),
}


def main():
    parser = argparse.ArgumentParser(description="Run AgentGuard-X demo scenarios")
    parser.add_argument(
        "--scenarios", nargs="+", type=int,
        default=list(SCENARIOS.keys()),
        help="Which scenario numbers to run (default: all)",
    )
    args = parser.parse_args()

    demo_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, demo_dir)

    print(f"\n{BOLD}{CYAN}{'═'*62}{RESET}")
    print(f"{BOLD}{CYAN}  AgentGuard-X × FinanceFlow — Demo Suite{RESET}")
    print(f"{BOLD}{CYAN}{'═'*62}{RESET}")
    print(f"  Running scenarios: {args.scenarios}\n")

    for num in args.scenarios:
        if num not in SCENARIOS:
            print(f"  Unknown scenario {num} — skipping")
            continue
        module_name, description = SCENARIOS[num]
        print(f"{BOLD}{CYAN}━━ Scenario {num}: {description} ━━{RESET}")
        try:
            mod = importlib.import_module(module_name)
            mod.run()
        except Exception as e:
            print(f"  ERROR in scenario {num}: {e}")
        if num != args.scenarios[-1]:
            print("  [Pausing 3s before next scenario...]\n")
            time.sleep(3)

    print(f"\n{BOLD}{GREEN}All scenarios complete.{RESET}")
    print("Open http://localhost:3000 for the live dashboard.\n")


if __name__ == "__main__":
    main()
