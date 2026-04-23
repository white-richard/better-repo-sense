import os
import shutil
import subprocess
from collections import defaultdict

import questionary
from git import Repo
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()


def get_unique_extensions(repo_path) -> list:
    """Scan the repo to find all unique file extensions, file counts, and line counts."""
    extensions = defaultdict(lambda: {"files": 0, "lines": 0})
    for root, dirs, files in os.walk(repo_path):
        # Skip the .git directory
        if ".git" in dirs:
            dirs.remove(".git")
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext:
                extensions[ext]["files"] += 1
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        extensions[ext]["lines"] += sum(1 for _ in f)
                except Exception:
                    pass
    return sorted(extensions.items())


def get_git_stats() -> None:
    console.print(Panel.fit("[bold blue]Repo Sense[/bold blue]", border_style="blue"))
    repo_url = Prompt.ask("[bold green]Enter GitHub Repo URL[/bold green]").strip()
    since_date = "2026-01-01"

    repo_dir = "temp_repo_stats"

    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)

    with console.status(f"[bold yellow]Cloning {repo_url}...[/bold yellow]", spinner="dots"):
        repo = Repo.clone_from(repo_url, repo_dir)

    with console.status("[bold yellow]Scanning repository...[/bold yellow]", spinner="dots"):
        available_exts = get_unique_extensions(repo_dir)

    console.print("\n[bold cyan]File extensions found in this repository:[/bold cyan]")
    ext_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    ext_table.add_column("No.", justify="right")
    ext_table.add_column("Extension")
    ext_table.add_column("Files", justify="right")
    ext_table.add_column("Lines", justify="right")

    for i, (ext, data) in enumerate(available_exts, 1):
        ext_table.add_row(str(i), ext, str(data["files"]), str(data["lines"]))

    console.print(ext_table)

    choices = [
        questionary.Choice(title=f"{ext} ({data['files']} files, {data['lines']} lines)", value=ext)
        for ext, data in available_exts
    ]
    target_extensions = questionary.checkbox(
        "Select extensions to filter by (j/k to move, Space to select, Enter to confirm, none for all):",
        choices=choices,
    ).ask()

    if target_extensions is None:
        target_extensions = []

    stats = defaultdict(lambda: {"add": 0, "del": 0})

    log_args = [
        f"--since={since_date}",
        "--numstat",
        "--no-merges",
        "--pretty=format:%aN",
    ]

    with console.status("[bold yellow]Analyzing git log...[/bold yellow]", spinner="dots"):
        raw_log = repo.git.log(*log_args)

        current_author = None
        for line in raw_log.splitlines():
            if not line.strip():
                continue

            if not line[0].isdigit() and not line.startswith("-"):
                current_author = line.strip()
                continue

            parts = line.split("\t")
            if len(parts) == 3:
                add, delete, file_path = parts
                if add == "-" or delete == "-":
                    continue

                # Check against user's filter
                file_ext = os.path.splitext(file_path)[1]
                if target_extensions and file_ext not in target_extensions:
                    continue

                stats[current_author]["add"] += int(add)
                stats[current_author]["del"] += int(delete)

    if not stats:
        console.print("\n[bold red]No activity found for those criteria.[/bold red]")
    else:
        stats_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        stats_table.add_column("Author")
        stats_table.add_column("+ Lines", style="green", justify="right")
        stats_table.add_column("- Lines", style="red", justify="right")
        stats_table.add_column("Total", style="cyan", justify="right")

        for author, counts in stats.items():
            total = counts["add"] - counts["del"]
            stats_table.add_row(author[:25], str(counts["add"]), str(counts["del"]), str(total))

        console.print("\n[bold cyan]Git Contributions:[/bold cyan]")
        console.print(stats_table)

        if Confirm.ask(
            "\n[bold green]View filtered diffs for a specific user in TUI?[/bold green]",
        ):
            choices = [*list(stats.keys()), questionary.Choice("❌ Exit", value=None)]
            while True:
                selected_user = questionary.select(
                    "Select author to view diffs for (j/k to move, Enter to confirm):",
                    choices=choices,
                ).ask()

                if not selected_user:
                    break

                cmd = [
                    "git",
                    "-C",
                    repo_dir,
                    "log",
                    "-p",
                    "--color=always",
                    f"--since={since_date}",
                    f"--author={selected_user}",
                ]
                if target_extensions:
                    cmd.append("--")
                    for ext in target_extensions:
                        cmd.append(f"*{ext}")
                env = os.environ.copy()
                env["GIT_PAGER"] = "less -+F -R"
                subprocess.run(cmd, env=env)

    shutil.rmtree(repo_dir)


if __name__ == "__main__":
    get_git_stats()
