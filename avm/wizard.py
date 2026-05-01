from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path


def should_run_wizard() -> bool:
    queries_missing = not Path("queries.md").exists()
    sites_missing = not Path("sites.json").exists()
    env_path = Path(".env")
    key_missing = not os.environ.get("ANTHROPIC_API_KEY") and not (
        env_path.exists() and "ANTHROPIC_API_KEY=" in env_path.read_text()
    )
    return queries_missing or sites_missing or key_missing


def run_wizard(force: bool = False) -> bool:
    """
    Run the first-time setup wizard.

    Returns True if user confirmed to proceed with the citation check.
    Returns False if they chose to exit after setup.
    Sys.exits on Ctrl+C with no partial files written.

    force=True: re-run even if config already exists (avm setup).
    """
    try:
        from rich.console import Console
        from rich import box as rich_box
        from rich.panel import Panel
        console = Console()
        _RICH = True
    except ImportError:
        console = None
        _RICH = False

    def say(msg: str) -> None:
        print(f"  {msg}")

    def step_header(n: int, total: int, title: str) -> None:
        print()
        if _RICH:
            console.print(f"  [bold]▸ Step {n} of {total}: {title}[/bold]")
        else:
            print(f"  ▸ Step {n} of {total}: {title}")

    def ask_yn(prompt_text: str, default_yes: bool = True) -> bool:
        hint = "[Y/n]" if default_yes else "[y/N]"
        raw = input(f"  {prompt_text} {hint} ").strip().lower()
        return raw not in ("n", "no") if default_yes else raw in ("y", "yes")

    def ask(prompt_text: str) -> str:
        return input(f"  {prompt_text} ").strip()

    # Files written so far (for Ctrl+C cleanup)
    written: list[Path] = []

    try:
        if _RICH:
            console.print()
            console.print(Panel(
                "AI Visibility Monitor · first-time setup",
                box=rich_box.ROUNDED,
                padding=(0, 2),
            ))
        else:
            print("\n=== AI Visibility Monitor · first-time setup ===")

        print()
        say("Looks like this is your first run. Let's get you set up.")
        say("This takes about 2 minutes. Hit Ctrl+C any time to cancel.")

        # Step 1: Dependencies (calls preflight)
        step_header(1, 4, "Dependencies")
        say("Checking required packages (anthropic, rich)...")
        from avm.preflight import check_dependencies
        check_dependencies()
        say("Dependencies OK.")

        # Step 2: Anthropic API key
        step_header(2, 4, "Anthropic API key")
        env_path = Path(".env")
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not api_key and env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

        if api_key:
            say("Anthropic API key detected.")
        else:
            say("The tool runs your queries through Claude. You need an")
            say("Anthropic API key. Get one at:")
            say("https://console.anthropic.com/settings/keys")
            print()

            while True:
                try:
                    key_input = getpass.getpass("  Paste your key (starts with sk-ant-): ").strip()
                except Exception:
                    key_input = ask("Paste your key (starts with sk-ant-):")
                if key_input.startswith(("sk-ant-", "sk-")):
                    api_key = key_input
                    break
                if key_input:
                    say("That doesn't look like an Anthropic key. Try again.")
                else:
                    say("Key cannot be empty.")

            print()
            say("Save it for future runs?")
            say("  [1] Save to .env in this folder (recommended, gitignored)")
            say("  [2] Save to ~/.zshrc (system-wide)")
            say("  [3] Don't save, ask me again next time")
            print()

            while True:
                choice = ask(">")
                if choice in ("1", "2", "3"):
                    break
                say("Enter 1, 2, or 3.")

            if choice == "1":
                existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
                lines = [l for l in existing.splitlines() if not l.startswith("ANTHROPIC_API_KEY=")]
                lines.append(f'ANTHROPIC_API_KEY="{api_key}"')
                env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                written.append(env_path)
                os.environ["ANTHROPIC_API_KEY"] = api_key
                say("Saved to .env. (.env is gitignored, won't be committed.)")
            elif choice == "2":
                zshrc = Path.home() / ".zshrc"
                with zshrc.open("a", encoding="utf-8") as f:
                    f.write(f'\nexport ANTHROPIC_API_KEY="{api_key}"\n')
                os.environ["ANTHROPIC_API_KEY"] = api_key
                say(f"Added to {zshrc}. Run 'source ~/.zshrc' or open a new terminal.")
            else:
                os.environ["ANTHROPIC_API_KEY"] = api_key
                say("OK, not saved. You'll need to set it each session.")

        # Optional: OpenAI and Perplexity keys
        print()
        say("Optional: set OpenAI and Perplexity API keys to enable multi-engine citations.")
        say("(Press Enter to skip any of these.)")
        print()

        for key_name, label, env_var in [
            ("OpenAI", "ChatGPT citations", "OPENAI_API_KEY"),
            ("Perplexity", "Perplexity citations", "PERPLEXITY_API_KEY"),
        ]:
            if os.environ.get(env_var):
                say(f"{key_name} key already set.")
                continue
            val = ask(f"{key_name} API key (blank to skip):")
            if val:
                os.environ[env_var] = val
                existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
                lines_existing = [l for l in existing.splitlines() if not l.startswith(f"{env_var}=")]
                lines_existing.append(f'{env_var}="{val}"')
                env_path.write_text("\n".join(lines_existing) + "\n", encoding="utf-8")
                if env_path not in written:
                    written.append(env_path)
                say(f"{key_name} key saved to .env.")

        # Step 3: Domain + competitors
        step_header(3, 4, "Your domain and competitors")
        sites_path = Path("sites.json")

        if sites_path.exists() and not force:
            say("sites.json already exists, keeping it.")
            sites_data = json.loads(sites_path.read_text(encoding="utf-8"))
        else:
            if sites_path.exists() and force:
                overwrite = ask_yn("sites.json already exists. Overwrite?", default_yes=False)
                if not overwrite:
                    say("Keeping existing sites.json.")
                    sites_data = json.loads(sites_path.read_text(encoding="utf-8"))
                    sites_path = None  # type: ignore[assignment]
                else:
                    sites_path = Path("sites.json")
                    sites_data = None
            else:
                sites_data = None

            if sites_data is None:
                print()
                while True:
                    domain = ask("What's your primary domain (e.g. work-smart.ai)?")
                    if domain:
                        domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
                        break
                    say("Domain cannot be empty.")

                sites_data = [{"name": domain, "url": f"https://{domain}", "owner": "self"}]

                print()
                add_comp = ask_yn("Add competitors? They show up in the citation report.", default_yes=True)
                if add_comp:
                    say("Enter domains one at a time. Blank line to finish.")
                    i = 1
                    while True:
                        comp = ask(f"Competitor {i} (or blank to finish):")
                        if not comp:
                            break
                        comp = comp.replace("https://", "").replace("http://", "").rstrip("/")
                        sites_data.append({"name": comp, "url": f"https://{comp}", "owner": "competitor"})
                        i += 1

                if sites_path is not None:
                    sites_path = Path("sites.json")
                sites_path = Path("sites.json")
                sites_path.write_text(json.dumps(sites_data, indent=2) + "\n", encoding="utf-8")
                written.append(sites_path)
                say(f"Saved sites.json ({len(sites_data) - 1} competitor(s) added).")

        # Step 4: Buyer queries
        step_header(4, 4, "Buyer queries")
        queries_path = Path("queries.md")
        skip_queries = False

        if queries_path.exists():
            if force:
                overwrite = ask_yn("queries.md already exists. Overwrite?", default_yes=False)
                if not overwrite:
                    say("Keeping existing queries.md.")
                    skip_queries = True
            else:
                say("queries.md already exists, keeping it.")
                skip_queries = True

        if not skip_queries:
            say("What 5 questions do your buyers ask AI engines about your")
            say("category? Examples:")
            say('  "best fractional head of ai for mid-market"')
            say('  "fractional head of ai miami"')
            print()

            queries: list[str] = []
            for i in range(1, 6):
                while True:
                    q = ask(f"Query {i}:")
                    if q:
                        queries.append(q)
                        break
                    say("Cannot be empty. Try again.")

            lines = [
                "# Buyer queries",
                "",
                "# 5 questions a real prospect would type into ChatGPT or Claude",
                "",
                *queries,
                "",
            ]
            queries_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            written.append(queries_path)
            say(f"Saved {len(queries)} queries to queries.md.")

        # Done
        print()
        if _RICH:
            console.print("  [bold green]▸ Setup complete[/bold green]")
        else:
            say("▸ Setup complete")

        saved = []
        if any(p.name == "queries.md" for p in written):
            saved.append("queries.md")
        if any(p.name == "sites.json" for p in written):
            saved.append("sites.json")
        if any(p.name == ".env" for p in written):
            saved.append(".env")
        say("Config saved to: " + ", ".join(saved) if saved else "Config already existed.")

        print()
        say("Ready to run the citation check?")
        say("  [Y] Run now (~$0.30, ~90 seconds)")
        say("  [N] Exit, run later with: avm")
        print()

        proceed = ask_yn(">", default_yes=True)
        return proceed

    except KeyboardInterrupt:
        print()
        say("Aborted. Cleaning up partial files...")
        for p in written:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        say("No files written.")
        sys.exit(0)
