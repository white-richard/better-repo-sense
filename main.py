import os
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta

import questionary
from git import Repo
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
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


class RepoSense:
    def __init__(self) -> None:
        self.repo_dir = "temp_repo_stats"
        self.repo = None
        self.repo_url = ""
        self.available_exts = []
        self.target_extensions = []
        self.since_date = "2026-01-01"

    def run(self) -> None:
        console.print(
            Panel.fit("[bold #ffb86c]Claude Repo Sense[/bold #ffb86c]", border_style="#ffb86c"),
        )
        self.repo_url = Prompt.ask("[bold white]Enter GitHub Repo URL[/bold white]").strip()

        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)

        with console.status(
            f"[bold #ffb86c]Cloning {self.repo_url}...[/bold #ffb86c]",
            spinner="dots",
        ):
            self.repo = Repo.clone_from(self.repo_url, self.repo_dir)

        with console.status("[bold #ffb86c]Scanning repository...[/bold #ffb86c]", spinner="dots"):
            self.available_exts = get_unique_extensions(self.repo_dir)

        self.main_menu()

    def main_menu(self) -> None:
        while True:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    "View File Extensions",
                    "Filter Extensions",
                    "View Weekly Commit Activity",
                    "View Git Contributions (+/- lines)",
                    "View Filtered Diffs for User",
                    "View Commit Graph",
                    "Exit",
                ],
                style=questionary.Style(
                    [
                        ("qmark", "fg:#ffb86c bold"),
                        ("question", "bold"),
                        ("pointer", "fg:#ffb86c bold"),
                        ("highlighted", "fg:#ffb86c bold"),
                    ],
                ),
            ).ask()

            if choice == "View File Extensions":
                self.view_file_extensions()
            elif choice == "Filter Extensions":
                self.filter_extensions()
            elif choice == "View Weekly Commit Activity":
                self.view_weekly_activity()
            elif choice == "View Git Contributions (+/- lines)":
                self.view_git_contributions()
            elif choice == "View Filtered Diffs for User":
                self.view_filtered_diffs()
            elif choice == "View Commit Graph":
                self.view_commit_graph()
            elif choice == "Exit" or choice is None:
                self.cleanup()
                break

    def view_file_extensions(self) -> None:
        console.print("\n[bold #8be9fd]File extensions found:[/bold #8be9fd]")
        ext_table = Table(box=box.ROUNDED, show_header=True, header_style="bold #ffb86c")
        ext_table.add_column("No.", justify="right")
        ext_table.add_column("Extension")
        ext_table.add_column("Files", justify="right")
        ext_table.add_column("Lines", justify="right")

        for i, (ext, data) in enumerate(self.available_exts, 1):
            ext_table.add_row(str(i), ext, str(data["files"]), str(data["lines"]))
        console.print(ext_table)

    def filter_extensions(self) -> None:
        choices = [
            questionary.Choice(
                title=f"{ext} ({data['files']} files, {data['lines']} lines)",
                value=ext,
            )
            for ext, data in self.available_exts
        ]
        target = questionary.checkbox(
            "Select extensions to filter by (space to select, enter to confirm, none for all):",
            choices=choices,
            style=questionary.Style([("highlighted", "fg:#ffb86c bold")]),
        ).ask()
        if target is not None:
            self.target_extensions = target
            console.print(
                f"[bold #50fa7b]Filter updated to: {', '.join(target) if target else 'All extensions'}[/bold #50fa7b]",
            )

    def _get_stats(self):
        stats = defaultdict(lambda: {"add": 0, "del": 0})
        log_args = [
            "main",
            f"--since={self.since_date}",
            "--numstat",
            "--no-merges",
            "--pretty=format:%aN",
        ]
        with console.status("[bold #ffb86c]Analyzing git log...[/bold #ffb86c]", spinner="dots"):
            raw_log = self.repo.git.log(*log_args)
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
                    file_ext = os.path.splitext(file_path)[1]
                    if self.target_extensions and file_ext not in self.target_extensions:
                        continue
                    stats[current_author]["add"] += int(add)
                    stats[current_author]["del"] += int(delete)
        return stats

    def view_git_contributions(self) -> None:
        stats = self._get_stats()
        if not stats:
            console.print("\n[bold #ff5555]No activity found for those criteria.[/bold #ff5555]")
            return

        stats_table = Table(box=box.ROUNDED, show_header=True, header_style="bold #ffb86c")
        stats_table.add_column("Author")
        stats_table.add_column("+ Lines", style="#50fa7b", justify="right")
        stats_table.add_column("- Lines", style="#ff5555", justify="right")
        stats_table.add_column("Total", style="#8be9fd", justify="right")

        for author, counts in stats.items():
            total = counts["add"] - counts["del"]
            stats_table.add_row(author[:25], str(counts["add"]), str(counts["del"]), str(total))

        console.print("\n[bold #8be9fd]Git Contributions:[/bold #8be9fd]")
        console.print(stats_table)

    def view_weekly_activity(self) -> None:
        weekly_log_args = [
            "main",
            f"--since={self.since_date}",
            "--no-merges",
            "--pretty=format:%aN|%ad",
            "--date=short",
        ]
        with console.status(
            "[bold #ffb86c]Analyzing weekly activity...[/bold #ffb86c]",
            spinner="dots",
        ):
            weekly_log = self.repo.git.log(*weekly_log_args)

        weekly_commits = defaultdict(int)
        user_weekly_commits = defaultdict(lambda: defaultdict(int))
        for line in weekly_log.splitlines():
            if line.strip():
                try:
                    author, date_str = line.strip().split("|", 1)
                    date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    week_start = date - timedelta(days=date.weekday())
                    weekly_commits[week_start] += 1
                    user_weekly_commits[author][week_start] += 1
                except ValueError:
                    pass

        if not weekly_commits:
            console.print("\n[bold #ff5555]No weekly activity found.[/bold #ff5555]")
            return

        console.print("\n[bold #8be9fd]Contributions per week (Overall):[/bold #8be9fd]")
        self._print_bar_chart(weekly_commits)

        for author, counts in user_weekly_commits.items():
            console.print(
                f"\n[bold #8be9fd]Contributions per week ({author}):[/bold #8be9fd]",
            )
            self._print_bar_chart(counts)

    def _print_bar_chart(self, commit_dict) -> None:
        max_commits = max(commit_dict.values())
        chart_table = Table(box=box.SIMPLE, show_header=False)
        chart_table.add_column("Week", style="bold #f1fa8c")
        chart_table.add_column("Chart", style="#50fa7b")
        chart_table.add_column("Count", style="#8be9fd", justify="right")

        for week in sorted(commit_dict.keys()):
            count = commit_dict[week]
            bar_len = int((count / max_commits) * 40) if max_commits > 0 else 0
            chart_table.add_row(week.strftime("%Y-%m-%d"), "█" * bar_len, str(count))
        console.print(chart_table)

    def view_filtered_diffs(self) -> None:
        stats = self._get_stats()
        if not stats:
            console.print("\n[bold #ff5555]No activity found.[/bold #ff5555]")
            return

        choices = [*list(stats.keys()), questionary.Choice("Back", value=None)]
        selected_user = questionary.select(
            "Select author to view diffs for:",
            choices=choices,
        ).ask()

        if selected_user:
            cmd = [
                "git",
                "-C",
                self.repo_dir,
                "log",
                "main",
                "-p",
                "--color=always",
                f"--since={self.since_date}",
                f"--author={selected_user}",
            ]
            if self.target_extensions:
                cmd.append("--")
                for ext in self.target_extensions:
                    cmd.append(f"*{ext}")
            env = os.environ.copy()
            env["GIT_PAGER"] = "less -+F -R"
            subprocess.run(cmd, env=env)

    def view_commit_graph(self) -> None:
        cmd = [
            "git",
            "-C",
            self.repo_dir,
            "log",
            "--graph",
            "--oneline",
            "--decorate",
            "--all",
            "--color=always",
        ]
        env = os.environ.copy()
        env["GIT_PAGER"] = "less -+F -R"
        subprocess.run(cmd, env=env)

    def cleanup(self) -> None:
        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)


if __name__ == "__main__":
    app = RepoSense()
    app.run()
