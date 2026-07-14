"""
Textual TUI for AniDL.

Provides arrow-key browsing for search results and episode selection instead
of typing numbers. This module only handles *browsing and picking* - once you
confirm a selection, this app exits and hands off to AniDL's existing
Rich-based download pipeline (language/host prompts, live per-episode
progress, the summary table). Rich's Live rendering and Textual's screen
buffer both want exclusive control of the terminal, so they intentionally
never run at the same time.

Launch with:  python anidlkey.py --tui
"""

from __future__ import annotations

from typing import Dict, List, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Header,
    Footer,
    Input,
    ListView,
    ListItem,
    Label,
    Static,
    SelectionList,
    Button,
)

import anidlkey


class MessageScreen(Screen):
    """A dead-end screen for errors/info. Esc to go back."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self.message, id="message")
        yield Footer()


class EpisodeScreen(Screen):
    """Pick which episodes to download: arrow keys + space to toggle,
    or type a range (1-5, 1,3,5, all) into the quick-select box."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f5", "confirm", "Download selected"),
    ]

    def __init__(self, details: "anidlkey.AnimeDetails"):
        super().__init__()
        self.details = details

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f"[bold]{self.details.title}[/bold] \u2014 "
            f"{len(self.details.episodes)} episode(s) available",
            id="status",
        )
        yield Input(
            placeholder="Quick select: 1-5, 1,3,5, all  \u2014  Enter to apply",
            id="quick_select",
        )
        selections = [
            (
                f"Episode {ep.number}" + (f" \u2014 {ep.title}" if ep.title else ""),
                ep.number,
            )
            for ep in self.details.episodes
        ]
        yield SelectionList(*selections, id="episodes")
        yield Button("Download selected (f5)", id="download_btn", variant="success")
        yield Static(
            "[dim]space: toggle selected  \u00b7  f5 / button: download selected  "
            "\u00b7  esc: back[/dim]"
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "download_btn":
            self.action_confirm()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "quick_select":
            return
        total = len(self.details.episodes)
        numbers = anidlkey.EpisodeSelector.parse_episode_selection(event.value, total)
        status = self.query_one("#status", Static)
        if not numbers:
            status.update(
                "[red]Couldn't parse that.[/red] Try formats like: "
                "1 | 1-5 | 1,3,5 | 1-3,7-9 | all"
            )
            return
        selection_list = self.query_one("#episodes", SelectionList)
        for n in numbers:
            selection_list.select(n)
        event.input.value = ""
        status.update(
            f"[bold]{self.details.title}[/bold] \u2014 added {len(numbers)} episode(s)"
        )

    def action_confirm(self) -> None:
        selection_list = self.query_one("#episodes", SelectionList)
        chosen = sorted(selection_list.selected)
        if not chosen:
            self.query_one("#status", Static).update(
                "[yellow]Pick at least one episode first "
                "(space to toggle, or use quick-select).[/yellow]"
            )
            return
        self.app.exit({"details": self.details, "episodes": chosen})


class ResultsScreen(Screen):
    """Arrow-key list of search results. Enter fetches details for the highlighted one."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, results: List[Dict[str, str]], downloader: "anidlkey.AniDL"):
        super().__init__()
        self.results = results or []
        self.downloader = downloader

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        if not self.results:
            yield Static(
                "[yellow]No results found. Press esc to try another search.[/yellow]"
            )
        else:
            items = []
            for r in self.results:
                desc = (r.get("description") or "").strip()
                if len(desc) > 90:
                    desc = desc[:90] + "..."
                items.append(ListItem(Label(f"{r['title']}\n[dim]{desc}[/dim]")))
            yield ListView(*items, id="results")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or not (0 <= index < len(self.results)):
            return
        selected = self.results[index]
        self.query_one("#status", Static).update(
            f"Fetching details for '{selected['title']}'..."
        )
        self.fetch_details(selected["url"])

    @work(thread=True)
    def fetch_details(self, url: str) -> None:
        try:
            details = self.downloader.get_anime_details(url)
            error = None
        except Exception as e:
            details = None
            error = str(e)
        self.app.call_from_thread(self._show_episodes, details, error)

    def _show_episodes(
        self, details: Optional["anidlkey.AnimeDetails"], error: Optional[str]
    ) -> None:
        if error:
            self.query_one("#status", Static).update(
                f"[red]Error fetching details: {error}[/red]"
            )
            return
        if not details or not details.episodes:
            self.query_one("#status", Static).update(
                "[yellow]No episodes found for this title.[/yellow]"
            )
            return
        self.app.push_screen(EpisodeScreen(details))


class AniDLTUIApp(App):
    """Root app: just a search box. Everything else is pushed screens."""

    CSS = """
    #results, #episodes {
        height: 1fr;
    }
    #message {
        margin: 2 4;
    }
    """

    BINDINGS = [Binding("ctrl+c", "quit", "Quit")]

    def __init__(self, downloader: "anidlkey.AniDL"):
        super().__init__()
        self.downloader = downloader
        self.title = "AniDL"
        self.sub_title = (
            "Search an anime, then browse results/episodes with the arrow keys"
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Search aniworld.to for an anime:")
        yield Input(placeholder="e.g. One Piece", id="query")
        yield Static("", id="status")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "query":
            return
        query = event.value.strip()
        if not query:
            return
        self.query_one("#status", Static).update(f"Searching for '{query}'...")
        self.do_search(query)

    @work(thread=True)
    def do_search(self, query: str) -> None:
        try:
            results = self.downloader.search_anime(query)
            error = None
        except Exception as e:
            results = []
            error = str(e)
        self.call_from_thread(self._show_results, results, error)

    def _show_results(
        self, results: List[Dict[str, str]], error: Optional[str]
    ) -> None:
        if error:
            self.query_one("#status", Static).update(
                f"[red]Search failed: {error}[/red]"
            )
            return
        self.query_one("#status", Static).update("")
        self.push_screen(ResultsScreen(results, self.downloader))


def run_tui() -> None:
    """Entry point called from `python anidlkey.py --tui`."""
    downloader = anidlkey.AniDL()
    if not downloader.auth_manager.login_flow():
        return

    app = AniDLTUIApp(downloader)
    result = app.run()

    if not result:
        downloader.console.print(
            "[yellow]No episodes selected - nothing to download.[/yellow]"
        )
        return

    details = result["details"]
    episode_numbers = result["episodes"]
    selection_str = ",".join(str(n) for n in episode_numbers)

    downloader.console.print(
        f"\n[bold cyan]{len(episode_numbers)} episode(s) selected for "
        f"'{details.title}'[/bold cyan]"
    )
    downloader.download_episodes_batch(details, episode_selection=selection_str)


if __name__ == "__main__":
    run_tui()
