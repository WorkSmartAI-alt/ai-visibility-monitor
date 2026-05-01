from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich import box as rich_box
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


def run_interactive_setup() -> None:  # legacy shim — new code uses avm.wizard
    """
    Prompt for domain and 5 buyer queries, write queries.md and sites.json,
    then return. Caller decides whether to run the citation check after.
    Exits cleanly on Ctrl+C without writing partial files.
    """
    if _RICH_AVAILABLE:
        console = Console()
        console.print()
        console.print(Panel(
            "\n  Let's set up your buyer queries.\n ",
            title="[bold blue]AI VISIBILITY MONITOR - INTERACTIVE SETUP[/bold blue]",
            box=rich_box.ROUNDED,
        ))
    else:
        print("\n=== AI VISIBILITY MONITOR - INTERACTIVE SETUP ===\n")
        print("Let's set up your buyer queries.\n")

    def prompt(msg: str) -> str:
        print(msg)
        return input("  > ").strip()

    def say(msg: str) -> None:
        print(f"  {msg}")

    try:
        # Check for existing queries.md before asking anything
        queries_path = Path("queries.md")
        overwrite_queries = True
        if queries_path.exists() and queries_path.read_text(encoding="utf-8").strip():
            resp = prompt("\n  queries.md already exists. Overwrite? [y/N]")
            if resp.lower() != "y":
                say("Keeping existing queries.md.")
                return

        print()
        domain = prompt("  What's your domain? (e.g., work-smart.ai)")
        while not domain:
            domain = prompt("  Domain cannot be empty. Try again:")

        print()
        say("Now enter 5 buyer queries - the actual questions a real")
        say("prospect would type into ChatGPT or Claude when looking")
        say("for what you sell.")
        print()

        queries: list[str] = []
        for i in range(1, 6):
            while True:
                q = prompt(f"  Buyer query {i}:")
                if q:
                    queries.append(q)
                    break
                say("Query cannot be empty. Try again:")

        print()
        ready = prompt("  Ready to save and run? [Y/n]")
        if ready.lower() == "n":
            say("Aborted. No files written.")
            sys.exit(0)

    except KeyboardInterrupt:
        print()
        print("\n  Aborted. No files written.")
        sys.exit(0)

    # Write queries.md (no partial writes - compose first, then write once)
    lines = [
        "# Target Queries · AI Visibility Monitor",
        "",
        "> Five buyer queries tracked monthly.",
        "",
        *queries,
        "",
        "## Rules for picking queries",
        "",
        "- Buyer language, not keyword language.",
        "- One geo query, one category-defining query, one product-specific query.",
    ]
    queries_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    say("Saved to queries.md")

    # Write sites.json if it does not exist
    sites_path = Path("sites.json")
    if not sites_path.exists():
        sites_data = [{"name": domain, "url": f"https://{domain}", "owner": "self"}]
        sites_path.write_text(json.dumps(sites_data, indent=2) + "\n", encoding="utf-8")
        say("Created sites.json")

    say("Running citation check...")
    print()
