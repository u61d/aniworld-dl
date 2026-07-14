import json
import re
import sys
import time
import os
import html
import logging
import random
import subprocess
import hashlib
import socket
import glob
from typing import Dict, List, Optional, Tuple
import pickle
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus, urlencode, urlunparse
from keyauth import api
import dl
from settings import SettingsManager
from mal import MALClient

try:
    import requests
    import cloudscraper
    from bs4 import BeautifulSoup
    from rich.console import Console
    from rich.table import Table
    import platform
    from time import sleep
    from datetime import datetime, UTC
    from rich.prompt import Prompt, IntPrompt, Confirm
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.theme import Theme
    from rich.align import Align
    from rich.layout import Layout
    from rich.live import Live
    from rich import box
    from rich.columns import Columns
    import threading
except ImportError as e:
    print(
        f"Missing required packages. Install with: pip install requests cloudscraper beautifulsoup4 rich yt-dlp keyauth"
    )
    sys.exit(1)

settings_manager = SettingsManager()


def clear():
    if platform.system() == "Windows":
        os.system("cls & title AniDL - made by halid2ud")
    elif platform.system() == "Linux":
        os.system("clear")
        sys.stdout.write("\033]0;AniDL - made by halid2ud\007")
        sys.stdout.flush()
    elif platform.system() == "Darwin":
        os.system("clear && printf '\033[3J'")
        os.system('echo -n -e "\033]0;AniDL - made by halid2ud\007"')


logging.basicConfig(
    level=(
        logging.DEBUG
        if settings_manager.settings.get("verbose_logging", False)
        else logging.INFO
    ),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("shadowcrawler_debug.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


class Config:
    BASE_URL = "https://aniworld.to"
    SERIES_URL = "https://s.to"
    TIMEOUT = 30
    AUTH_FILE = "auth_data.json"
    CONSOLE_THEME = Theme(
        {
            "info": "cyan",
            "warning": "yellow",
            "error": "red bold",
            "success": "green bold",
            "highlight": "bold magenta",
            "auth_success": "bold green",
            "auth_error": "bold red",
            "auth_warning": "bold yellow",
            "auth_info": "bold cyan",
            "banner": "bold magenta",
            "menu_option": "bold white",
            "input_prompt": "bold cyan",
            "debug": "dim white",
        }
    )
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def getchecksum():
    md5_hash = hashlib.md5()
    file = open("".join(sys.argv), "rb")
    md5_hash.update(file.read())
    digest = md5_hash.hexdigest()
    return digest


def load_webhook_config() -> Optional[str]:
    """Load the Discord webhook URL from an environment variable or a local,
    gitignored secrets file. Never hardcode credentials/webhooks in source -
    a value committed to a public repo is effectively public and can be
    spammed by anyone who reads the code.

    Resolution order:
      1. ANIDL_WEBHOOK_URL environment variable
      2. secrets.json (see secrets.json.example) - ignored by git
    Returns None if no webhook is configured, which disables login
    notifications entirely.
    """
    env_webhook = os.environ.get("ANIDL_WEBHOOK_URL")
    if env_webhook:
        return env_webhook

    secrets_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "secrets.json"
    )
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            webhook = data.get("webhook_url")
            return webhook or None
        except (json.JSONDecodeError, OSError):
            return None

    return None


# Initialize KeyAuth
keyauthapp = api(
    name="PromoGen",  # App name
    ownerid="TMVsgPDjV2",  # Account ID
    version="1.0",  # Application version. Used for automatic downloads see video here https://www.youtube.com/watch?v=kW195PLCBKs
    hash_to_check=getchecksum(),
)


class SystemInfoCollector:
    """Collect the minimal system info needed to spot license-key sharing/abuse.

    Deliberately does NOT enumerate local network interfaces or resolve a
    private LAN IP - that data isn't needed to tell whether a license key is
    being used from an unexpected place, and collecting it is overreach for
    a login-notification feature.
    """

    @staticmethod
    def get_system_info() -> dict:
        """Get basic, non-invasive system info"""
        return {
            "platform": platform.system(),
            "hostname": socket.gethostname(),
            "python_version": platform.python_version(),
        }


class DiscordNotifier:
    """Optional login notifier. Disabled automatically if no webhook is
    configured (see load_webhook_config). Only sends the minimum needed to
    flag license-abuse: username, the IP KeyAuth already recorded for the
    account, hostname, OS, and login time - nothing else."""

    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def send_system_info(self, user_data, system_info: dict):
        """Send minimal login info to the configured Discord webhook, if any."""
        if not self.enabled:
            return False

        try:
            embed = {
                "title": "License login",
                "color": 0x00FF00,
                "timestamp": datetime.utcnow().isoformat(),
                "fields": [
                    {"name": "Username", "value": user_data.username, "inline": True},
                    {"name": "Account IP", "value": user_data.ip, "inline": True},
                    {
                        "name": "System",
                        "value": system_info["platform"],
                        "inline": True,
                    },
                    {
                        "name": "Hostname",
                        "value": system_info["hostname"],
                        "inline": True,
                    },
                    {
                        "name": "Login Time",
                        "value": datetime.fromtimestamp(
                            int(user_data.lastlogin)
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                        "inline": True,
                    },
                ],
            }

            payload = {"embeds": [embed]}

            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True

        except Exception as e:
            print(f"Failed to send Discord notification: {e}")
            return False


class AuthManager:
    """Simplified authentication manager for license key only"""

    def __init__(self, console: Console):
        self.console = console
        self.auth_file = Config.AUTH_FILE
        self.authenticated = False
        self.user_data = None

        self.discord_notifier = DiscordNotifier(load_webhook_config())
        self.system_collector = SystemInfoCollector()
        self.telemetry_enabled = settings_manager.settings.get(
            "license_telemetry", True
        )

    def load_auth_data(self):
        """Load authentication data from file"""
        if not os.path.exists(self.auth_file):
            return None

        try:
            with open(self.auth_file, "r") as f:
                return json.load(f)
        except Exception as e:
            self.console.print(
                f"[auth_warning]Warning: Failed to load auth data: {e}[/auth_warning]"
            )
            return None

    def save_auth_data(self, license_key: str, remember: bool = True):
        """Save authentication data to file"""
        auth_data = {
            "license_key": license_key if remember else "",
            "remember_me": remember,
            "last_login": datetime.now(UTC).isoformat(),
        }

        try:
            with open(self.auth_file, "w") as f:
                json.dump(auth_data, f, indent=4)
            return True
        except Exception as e:
            self.console.print(
                f"[auth_error]Error: Failed to save auth data: {e}[/auth_error]"
            )
            return False

    def attempt_auto_login(self):
        """Attempt automatic login with saved license key"""
        auth_data = self.load_auth_data()

        if not auth_data or not auth_data.get("remember_me"):
            return False

        license_key = auth_data.get("license_key")

        if not license_key:
            return False

        self.console.print("[auth_info]Attempting auto-login...[/auth_info]")

        try:
            keyauthapp.license(license_key)
            self.authenticated = True
            self.save_auth_data(license_key, True)
            # Clear screen immediately after successful authentication
            clear()
            return True

        except Exception as e:
            self.console.print(
                f"[auth_warning]Warning: Auto-login failed: {str(e)}[/auth_warning]"
            )
            # Clear invalid credentials
            self.save_auth_data("", False)
            return False

    def login_flow(self):
        """Main authentication flow"""
        clear()

        # Try auto-login first
        if (
            settings_manager.settings.get("auto_login", True)
            and self.attempt_auto_login()
        ):
            self.display_user_info()
            return True

        # Manual login flow
        while not self.authenticated:
            try:
                license_key = Prompt.ask(
                    "[input_prompt]Enter your license key[/input_prompt]",
                    console=self.console,
                )
                if not license_key.strip():
                    self.console.print(
                        "[auth_error]Error: License key cannot be empty![/auth_error]"
                    )
                    continue

                two_fa = Prompt.ask(
                    "[input_prompt]2FA Code (press Enter if not using 2FA)[/input_prompt]",
                    default="",
                    console=self.console,
                )

                remember = (
                    Prompt.ask(
                        "[input_prompt]Remember login?[/input_prompt]",
                        choices=["y", "n"],
                        default="y",
                        console=self.console,
                    )
                    == "y"
                )

                self.perform_license_login(license_key, two_fa, remember)

            except KeyboardInterrupt:
                self.console.print("\n[auth_warning]Goodbye![/auth_warning]")
                sys.exit(0)
            except Exception as e:
                self.console.print(
                    f"[auth_error]Error: Unexpected error: {e}[/auth_error]"
                )
                sleep(2)

        return self.authenticated

    def perform_license_login(
        self, license_key: str, two_fa: str = "", remember: bool = True
    ):
        """Perform license-only login"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Authenticating with license...", start=False
            )
            progress.start_task(task)

            verbose = settings_manager.settings.get("verbose_logging", False)

            try:
                if verbose:
                    self.console.print(
                        f"[debug]Attempting license login with key: {license_key[:10]}...[/debug]"
                    )

                keyauthapp.license(license_key, two_fa)

                if not keyauthapp.user_data:
                    self.console.print(
                        "[auth_error]Error: No user data returned from KeyAuth[/auth_error]"
                    )
                    return

                if verbose:
                    self.console.print(
                        f"[debug]User data received: {keyauthapp.user_data.__dict__}[/debug]"
                    )

                if self.telemetry_enabled and self.discord_notifier.enabled:
                    self.console.print(
                        "[info]Note: basic login info (username, hostname, OS) is sent for "
                        "license-abuse monitoring. Disable via the 'license_telemetry' setting.[/info]"
                    )
                    system_info = self.system_collector.get_system_info()
                    self.discord_notifier.send_system_info(
                        keyauthapp.user_data, system_info
                    )

                if verbose:
                    if hasattr(keyauthapp.user_data, "subscriptions"):
                        self.console.print(
                            f"[debug]Subscriptions: {keyauthapp.user_data.subscriptions}[/debug]"
                        )
                    else:
                        self.console.print(
                            "[debug]No subscriptions attribute found[/debug]"
                        )

                progress.update(
                    task, description="[green]License authentication successful!"
                )
                time.sleep(2)
                if settings_manager.settings.get("clear_console", True):
                    clear()

                self.authenticated = True
                if remember:
                    self.save_auth_data(license_key, True)

                self.display_user_info()

            except Exception as e:
                progress.update(task, description="[red]License authentication failed")
                self.console.print(
                    f"[auth_error]Error: License authentication failed: {str(e)}[/auth_error]"
                )
                if verbose:
                    self.console.print(
                        f"[debug]Exception details: {type(e).__name__}: {e}[/debug]"
                    )
                sleep(2)

    def display_user_info(self):
        """Display user information after successful login"""
        try:
            keyauthapp.fetchStats()

            # Create user info table
            user_table = Table(title="User Information", box=box.ROUNDED, style="green")
            user_table.add_column("Property", style="bold cyan")
            user_table.add_column("Value", style="white")

            user_table.add_row("Username", keyauthapp.user_data.username)
            user_table.add_row("IP Address", keyauthapp.user_data.ip)
            user_table.add_row("Hardware ID", keyauthapp.user_data.hwid[:20] + "...")
            user_table.add_row(
                "Created",
                datetime.fromtimestamp(
                    int(keyauthapp.user_data.createdate), UTC
                ).strftime("%Y-%m-%d %H:%M:%S"),
            )
            user_table.add_row(
                "Last Login",
                datetime.fromtimestamp(
                    int(keyauthapp.user_data.lastlogin), UTC
                ).strftime("%Y-%m-%d %H:%M:%S"),
            )
            user_table.add_row(
                "Expires",
                datetime.fromtimestamp(int(keyauthapp.user_data.expires), UTC).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            )

            # Subscription info
            subs = keyauthapp.user_data.subscriptions
            if subs:
                sub_table = Table(
                    title="Active Subscriptions", box=box.ROUNDED, style="yellow"
                )
                sub_table.add_column("#", style="bold")
                sub_table.add_column("Subscription", style="cyan")
                sub_table.add_column("Expires", style="yellow")
                sub_table.add_column("Time Left", style="green")

                for i, sub_data in enumerate(subs):
                    sub_name = sub_data["subscription"]
                    expiry = datetime.fromtimestamp(
                        int(sub_data["expiry"]), UTC
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    timeleft = sub_data["timeleft"]

                    sub_table.add_row(str(i + 1), sub_name, expiry, timeleft)

            # Display everything
            self.console.print()
            self.console.print(user_table)
            if "sub_table" in locals():
                self.console.print(sub_table)

            # Success message
            success_panel = Panel(
                Align.center(
                    Text("Authentication Successful!\n", style="bold green")
                    + Text("Welcome to AniDL", style="bold white")
                ),
                box=box.DOUBLE,
                style="green",
            )
            self.console.print(success_panel)

            # Wait for user to continue
            Prompt.ask(
                "\n[bold green]Press Enter to continue to the main application...[/bold green]",
                default="",
                console=self.console,
            )

        except Exception as e:
            return


class ShadowUtils:
    def deduplicate_results(self, results):
        """Remove duplicate results while preserving order"""
        seen = set()
        unique_results = []
        for result in results:
            key = result.get("url", result.get("title", ""))
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
        return unique_results


class AnimeSearchResult:
    def __init__(self, title, url, description=""):
        self.title = title
        self.url = url
        self.description = description


class Episode:
    def __init__(self, title, number, url, language="GerSub"):
        self.title = title
        self.number = number
        self.url = url
        self.language = language


class Season:
    def __init__(self, number, title):
        self.number = number
        self.title = title


class HostLink:
    def __init__(self, name, url, quality="HD"):
        self.name = name
        self.url = url
        self.quality = quality


class AnimeDetails:
    def __init__(
        self,
        title,
        url,
        description="",
        Movie=None,
        episodes=None,
        seasons=None,
        genre=None,
        year=None,
        status="unknown",
        image_url=None,
    ):
        self.title = title
        self.url = url
        self.description = description
        self.episodes = episodes or []
        self.seasons = seasons or []
        self.genre = genre
        self.movies = List[Movie]
        self.year = year
        self.status = status
        self.image_url = image_url


class EpisodeSelector:
    """Flexible episode selection utility"""

    @staticmethod
    def parse_episode_selection(selection_str: str, total_episodes: int) -> List[int]:
        """
        Parse episode selection string into list of episode numbers
        Supports: 1, 1-5, 1,3,5, 1-3,7-9, all
        """
        if not selection_str.strip():
            return []

        selection_str = selection_str.strip().lower()

        if selection_str == "all":
            return list(range(1, total_episodes + 1))

        episodes = []
        parts = selection_str.split(",")

        for part in parts:
            part = part.strip()
            if "-" in part:
                # Range selection
                try:
                    start, end = map(int, part.split("-"))
                    episodes.extend(range(start, end + 1))
                except ValueError:
                    continue
            else:
                # Single episode
                try:
                    episodes.append(int(part))
                except ValueError:
                    continue

        # Filter valid episodes and remove duplicates
        valid_episodes = list(set(ep for ep in episodes if 1 <= ep <= total_episodes))
        return sorted(valid_episodes)


class AniDL:
    """Main scraper class for AniWorld.to"""

    def __init__(self):
        theme_name = settings_manager.settings.get("theme", "dark")

        # Define a light theme if needed
        light_theme = Theme(
            {
                "info": "black",
                "warning": "yellow",
                "error": "red bold",
                "success": "green bold",
                "highlight": "bold magenta",
                "auth_success": "bold green",
                "auth_error": "bold red",
                "auth_warning": "bold yellow",
                "auth_info": "bold cyan",
                "banner": "bold magenta",
                "menu_option": "bold black",
                "input_prompt": "bold cyan",
            }
        )

        if theme_name == "light":
            self.console = Console(theme=light_theme)
        else:
            self.console = Console(theme=Config.CONSOLE_THEME)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("cloudscraper").setLevel(logging.WARNING)
        self.base_url = Config.BASE_URL
        self.session = None
        self.utils = ShadowUtils()
        self._init_session()
        self.auth_manager = AuthManager(self.console)
        self.settings_manager = SettingsManager(console=self.console)
        self.mal_client = MALClient()

    def _init_session(self):
        """Initialize scraping session with proper headers"""
        try:
            # try cloudscraper first for Cloudflare protection
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            self.console.print("[green]✓[/green] CloudScraper initialized")
        except Exception as e:
            # fallback to regular requests
            self.session = requests.Session()
            self.console.print("[yellow]⚠[/yellow] Using regular requests session")

        # set headers
        self.session.headers.update(Config.DEFAULT_HEADERS)

    def type_banner(self, text: str, delay: float = 0.01):
        for line in text.splitlines():
            for char in line:
                self.console.print(char, end="", soft_wrap=True, highlight=False)
                sleep(delay)
            self.console.print()

    def display_banner(self):
        """Display the animated AniDL banner"""
        banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                     ★ made by halid2ud ★                     ║
    ║                      AniWorld.to Scraper                      ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
        self.type_banner(banner, delay=0.0025)

        if self.auth_manager.authenticated:
            self.display_user_info_compact()

    def display_user_info_compact(self):
        """Display compact user information in the main interface"""
        try:
            # Fetch latest user stats
            keyauthapp.fetchStats()

            # Create compact user info panel
            user_info = f"[bold cyan]{keyauthapp.user_data.username}[/bold cyan] | "
            # user_info += f"{keyauthapp.user_data.ip} | "
            user_info += f"Expires: [yellow]{datetime.fromtimestamp(int(keyauthapp.user_data.expires), UTC).strftime('%Y-%m-%d %H:%M')}[/yellow]"

            # Add subscription info if available
            subs = keyauthapp.user_data.subscriptions
            if subs:
                sub_info = " | Subs: "
                sub_names = [sub["subscription"] for sub in subs]
                sub_info += "[green]" + ", ".join(sub_names) + "[/green]"
                user_info += sub_info

            # Create a panel for the user info
            user_panel = Panel(
                Align.center(user_info),
                title="[bold green]User Status[/bold green]",
                box=box.ROUNDED,
                style="dim",
            )

            self.console.print(user_panel)

        except Exception as e:
            # Fallback to basic info if fetchStats fails
            self.console.print(
                f"[dim]👤 Authenticated User | Status: [green]Active[/green][/dim]"
            )

    def search_anime(self, query: str) -> List[Dict[str, str]]:
        """
        Search for anime using AniWorld's AJAX search API
        Following the exact API specification provided with improved filtering
        """
        search_url = f"{self.base_url}/ajax/search"

        # Prepare headers exactly as specified
        headers = {
            "Referer": f"{self.base_url}/search?q={quote_plus(query)}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # Prepare payload
        data = {"keyword": query}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("[cyan]Searching anime...", start=False)
            progress.start_task(task)

            try:
                # Send POST request to search API
                timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                response = self.session.post(
                    search_url, headers=headers, data=data, timeout=timeout
                )

                response.raise_for_status()

                # Parse the response line by line
                search_results = []
                response_lines = response.text.strip().splitlines()

                for i, line in enumerate(response_lines):
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        # Parse each line as JSON (could be array or single object)
                        json_data = json.loads(line)

                        # Handle both array and single object responses
                        anime_list = (
                            json_data if isinstance(json_data, list) else [json_data]
                        )

                        for j, anime_data in enumerate(anime_list):

                            # Extract and clean title (remove HTML tags)
                            title = anime_data.get("title", "")
                            title = re.sub(
                                r"<[^>]+>", "", title
                            )  # Remove all HTML tags
                            title = html.unescape(title)  # Decode HTML entities

                            # Extract and clean description
                            description = anime_data.get("description", "")
                            description = re.sub(
                                r"<[^>]+>", "", description
                            )  # Remove all HTML tags
                            description = html.unescape(
                                description
                            )  # Decode HTML entities like &#8230;

                            # Convert relative link to full URL
                            link = anime_data.get("link", "")

                            # IMPROVED FILTERING: Only include main anime stream links, exclude season/episode specific URLs
                            if link and link.startswith("/anime/stream/"):
                                # Extract the part after /anime/stream/ and check if it's a main anime page
                                stream_path = link[
                                    14:
                                ]  # Remove '/anime/stream/' prefix

                                # Count path segments - main anime pages should have only one segment (the anime name)
                                path_segments = [
                                    seg for seg in stream_path.split("/") if seg
                                ]

                                # Only include if it's a main anime page (single segment, no staffel/episode paths)
                                if len(path_segments) == 1 and not any(
                                    x in stream_path.lower()
                                    for x in ["staffel", "episode", "season"]
                                ):
                                    if not link.startswith("http"):
                                        url = urljoin(self.base_url, link)
                                    else:
                                        url = link

                                    # Add to results if we have at least a title and URL
                                    if title and url:
                                        result = {
                                            "title": title,
                                            "description": description,
                                            "url": url,
                                        }
                                        search_results.append(result)
                                    else:
                                        continue

                    except json.JSONDecodeError as e:
                        self.console.print(
                            f"[dim]Skipping malformed JSON line: {line[:50]}...[/dim]",
                            style="dim",
                        )
                        continue
                    except Exception as e:
                        self.console.print(f"[red]Unexpected error: {e}[/red]")
                        continue

                progress.update(
                    task,
                    completed=100,
                    description=f"[green]Found {len(search_results)} results!",
                )
                progress.stop()
                time.sleep(1.5)
                if self.settings_manager.settings.get("clear_console", True):
                    clear()

                # Remove duplicates while preserving order
                deduplicated = self.utils.deduplicate_results(search_results)
                return deduplicated

            except requests.exceptions.Timeout as e:
                progress.update(task, description=f"[red]Timeout error: {str(e)}")
                self.console.print(f"[red]Request timeout: {e}[/red]")
                return []
            except requests.exceptions.ConnectionError as e:
                progress.update(task, description=f"[red]Connection error: {str(e)}")
                self.console.print(f"[red]Connection error: {e}[/red]")
                return []
            except requests.exceptions.HTTPError as e:
                progress.update(task, description=f"[red]HTTP error: {str(e)}")
                self.console.print(f"[red]HTTP error: {e}[/red]")

                # Log response details for HTTP errors
                if hasattr(e, "response") and e.response is not None:
                    return []
            except requests.exceptions.RequestException as e:
                progress.update(task, description=f"[red]Network error: {str(e)}")
                self.console.print(f"[red]Network error during search: {e}[/red]")
                return []
            except Exception as e:
                progress.update(task, description=f"[red]Error: {str(e)}")
                self.console.print(f"[red]Error during search: {e}[/red]")
                return []

    def download_episode(
        self, urls: List[str], filenames: List[str] = None, progress_tracker=None
    ) -> bool:
        """Enhanced download that uses dl.py directly"""
        try:
            # Ensure downloads directory exists
            downloads_dir = self.settings_manager.settings.get(
                "download_folder", "downloads"
            )
            os.makedirs(downloads_dir, exist_ok=True)

            self.console.print(
                f"[cyan]Starting download of {len(urls)} episodes...[/cyan]"
            )

            # Change to downloads directory for dl.py
            original_cwd = os.getcwd()
            os.chdir(downloads_dir)

            try:
                success = True
                for i, url in enumerate(urls):
                    try:
                        # Optional: show progress if filenames provided
                        if filenames and i < len(filenames):
                            self.console.print(
                                f"[dim]Downloading: {filenames[i]}[/dim]"
                            )

                        dl.download(url)
                    except Exception as e:
                        self.console.print(f"[red]Error downloading {url}: {e}[/red]")
                        success = False
                        continue

                return success
            finally:
                os.chdir(original_cwd)

        except Exception as e:
            self.console.print(f"[red]Error during download: {e}[/red]")
            return False

    def download_episodes_batch(self, details: AnimeDetails) -> None:
        """Batch download with live episode processing UI"""
        if not details.episodes:
            self.console.print("[red][ERROR][/red] No episodes available!")
            return

        try:
            total_eps = len(details.episodes)

            self.console.print(
                f"\n[bold cyan]Available episodes:[/bold cyan] 1-{total_eps}"
            )
            self.console.print("[dim]Examples: 1 | 1-5 | 1,3,5 | 1-3,7-9 | all[/dim]")

            ep_input = Prompt.ask("Which episodes to download?", default="1").strip()
            episode_numbers = EpisodeSelector.parse_episode_selection(
                ep_input, total_eps
            )

            if not episode_numbers:
                self.console.print("[red]No valid episodes selected[/red]")
                return

            selected_episodes = [details.episodes[i - 1] for i in episode_numbers]

            # check for already downloaded episodes by looking at actual files
            new_episodes = []
            skipped_count = 0
            downloads_dir = self.settings_manager.settings.get(
                "download_folder", "downloads"
            )

            for episode in selected_episodes:
                # create expected filename pattern
                safe_title = "".join(
                    c for c in details.title if c.isalnum() or c in (" ", "-", "_")
                ).strip()
                season_num = getattr(episode, "season", 1)

                # check for any language variant of this episode
                episode_patterns = [
                    f"{safe_title}_S{season_num:02d}E{episode.number:02d}_*.mp4",
                    f"{safe_title}_S{season_num:02d}E{episode.number:02d}*.mp4",
                ]

                # check if any file matching the pattern exists
                file_exists = False
                if os.path.exists(downloads_dir):
                    for pattern in episode_patterns:
                        matching_files = glob.glob(os.path.join(downloads_dir, pattern))
                        if matching_files:
                            file_exists = True
                            break

                if file_exists:
                    skipped_count += 1
                    self.console.print(
                        f"[dim]Episode {episode.number} already exists[/dim]"
                    )
                else:
                    new_episodes.append(episode)

            if skipped_count > 0:
                self.console.print(
                    f"[yellow][SKIP][/yellow] Skipping {skipped_count} already downloaded episodes"
                )

            if not new_episodes:
                self.console.print(
                    "[green]All selected episodes already downloaded![/green]"
                )
                return

            # language selection
            timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
            first_ep_response = self.session.get(new_episodes[0].url, timeout=timeout)
            first_ep_soup = BeautifulSoup(first_ep_response.text, "html.parser")
            available_languages = self._detect_episode_language(first_ep_soup)
            default_lang = self.settings_manager.settings.get("default_language")
            if default_lang and default_lang in available_languages:
                selected_language = default_lang
            else:
                selected_language = self.select_language(available_languages)
            self.console.print(f"[green]Using language:[/green] {selected_language}")

            # host selection - FIXED: Pass the selected_language parameter
            first_episode_hosts = self.get_episode_hosts(
                new_episodes[0].url, selected_language
            )
            if not first_episode_hosts:
                self.console.print("[red]No hosts found for episodes![/red]")
                return

            default_host = self.settings_manager.settings.get("default_host")
            if default_host:
                matching_host = next(
                    (
                        h
                        for h in first_episode_hosts
                        if h.name.lower() == default_host.lower()
                    ),
                    None,
                )
                if matching_host:
                    self.console.print(
                        f"[green]✓[/green] Using default host: {default_host}"
                    )
                    selected_host = matching_host
                else:
                    selected_host = self.select_host_once(first_episode_hosts)
            else:
                selected_host = self.select_host_once(first_episode_hosts)
                if not selected_host:
                    return
            self.console.print(f"[green]Using host:[/green] {selected_host.name}")

            episode_data = []
            failed_episodes = []

            # Process each new episode
            for episode in new_episodes:
                try:
                    self._switch_episode_language(episode.url, selected_language)
                    sleep(0.5)
                    # FIXED: Pass the selected_language parameter here too
                    hosts = self.get_episode_hosts(episode.url, selected_language)
                    matching_host = next(
                        (
                            h
                            for h in hosts
                            if h.name.lower() == selected_host.name.lower()
                        ),
                        None,
                    )

                    if matching_host:
                        download_url = self.get_download_url_from_host(matching_host)
                        if download_url:
                            safe_title = "".join(
                                c
                                for c in details.title
                                if c.isalnum() or c in (" ", "-", "_")
                            ).strip()
                            season_num = getattr(episode, "season", 1)
                            lang_suffix = selected_language.replace(" ", "_")
                            filename = f"{safe_title}_S{season_num:02d}E{episode.number:02d}_{lang_suffix}.mp4"
                            episode_data.append(
                                {
                                    "url": download_url,
                                    "filename": filename,
                                    "episode": episode,
                                }
                            )
                        else:
                            failed_episodes.append(episode)
                    else:
                        failed_episodes.append(episode)

                except Exception as e:
                    failed_episodes.append(episode)

            if failed_episodes:
                self.console.print(
                    f"[yellow][WARNING][/yellow] Failed to process {len(failed_episodes)} episodes"
                )

            if not episode_data:
                self.console.print("[red]No downloadable episodes found.[/red]")
                return

            if (
                Prompt.ask("\nProceed with download?", choices=["y", "n"], default="y")
                == "n"
            ):
                return

            urls = [d["url"] for d in episode_data]
            filenames = [d["filename"] for d in episode_data]

            # Actually call the download function
            success = self.download_episode(urls, filenames)

            if success:
                self.console.print("[green]Download completed successfully![/green]")
            else:
                self.console.print("[red]Download failed or partially completed[/red]")

        except Exception as e:
            self.console.print(f"[red][ERROR][/red] {e}")

    def select_host_once(self, hosts: List[HostLink]) -> Optional[HostLink]:
        """Select a host once for batch downloads"""
        if not hosts:
            self.console.print("[red]No hosts available![/red]")
            return None

        if len(hosts) == 1:
            self.console.print(
                f"[green]Using only available host: {hosts[0].name}[/green]"
            )
            return hosts[0]

        # Display host selection table
        table = Table(
            title="Select Host for All Episodes",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", width=3)
        table.add_column("Host", style="green")
        table.add_column("Quality", style="yellow")

        for i, host in enumerate(hosts, 1):
            table.add_row(str(i), host.name, host.quality)

        self.console.print(table)

        try:
            choice = IntPrompt.ask(
                "Select host for all downloads",
                default=1,
                show_default=True,
                console=self.console,
            )

            if 1 <= choice <= len(hosts):
                return hosts[choice - 1]
            else:
                self.console.print("[red]Invalid selection![/red]")
                return None

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Cancelled by user[/yellow]")
            return None

    def get_download_url_from_host(self, host: HostLink) -> Optional[str]:
        """Get the actual download URL from a host link"""
        try:
            # follow the redirect to get the actual video URL
            timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
            response = self.session.get(host.url, allow_redirects=True, timeout=timeout)
            soup = BeautifulSoup(response.text, "html.parser")

            final_url = response.url
            return final_url
        except Exception as e:
            return None

    def display_search_results(
        self, results: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """Display search results and let user choose"""

        if not results:
            self.console.print("[red]No anime found![/red]")
            return None

        table = Table(
            title="🔍 Search Results", show_header=True, header_style="bold magenta"
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("URL", style="dim", width=30)

        for i, result in enumerate(results, 1):
            # Truncate description for display
            desc_preview = (
                result["description"][:60] + "..."
                if len(result["description"]) > 60
                else result["description"]
            )
            url_preview = (
                result["url"][-27:] if len(result["url"]) > 30 else result["url"]
            )
            table.add_row(str(i), result["title"], desc_preview, url_preview)

        self.console.print(table)

        try:
            choice = IntPrompt.ask(
                "Select anime by number",
                default=1,
                show_default=True,
                console=self.console,
            )

            if 1 <= choice <= len(results):
                selected = results[choice - 1]
                return selected
            else:
                self.console.print("[red]Invalid selection![/red]")
                return None

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Cancelled by user[/yellow]")
            return None

    def get_anime_details(self, anime_url: str) -> Optional[AnimeDetails]:

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching anime details...", total=None)

            try:
                timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                response = self.session.get(anime_url, timeout=timeout)

                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Extract anime title - try multiple selectors
                title_elem = (
                    soup.find("h1", class_="series-title")
                    or soup.find("h1")
                    or soup.find("div", class_="series-title")
                )
                title = (
                    title_elem.get_text(strip=True) if title_elem else "Unknown Title"
                )

                # Extract description - try multiple approaches
                desc_elem = (
                    soup.find("div", class_="seri_des")
                    or soup.find("div", class_="description")
                    or soup.find("p", class_="seri_des")
                )
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                # Extract image - more robust approach
                img_elem = None
                cover_box = soup.find("div", class_="seriesCoverBox")
                if cover_box:
                    img_elem = cover_box.find("img")
                if not img_elem:
                    # Try alternative selectors
                    img_elem = soup.find("img", class_="seriesCover")

                image_url = img_elem.get("src") if img_elem else None
                # Handle data URLs or relative URLs
                if (
                    image_url
                    and not image_url.startswith("http")
                    and not image_url.startswith("data:")
                ):
                    image_url = urljoin(anime_url, image_url)

                # Extract genres - more robust approach
                genre_elems = soup.find_all("a", href=re.compile(r"/genre/"))
                if not genre_elems:
                    # Try alternative approach
                    genre_container = soup.find("div", class_="genres") or soup.find(
                        "div", class_="categories"
                    )
                    if genre_container:
                        genre_elems = genre_container.find_all("a")

                genres = (
                    ", ".join([g.get_text(strip=True) for g in genre_elems])
                    if genre_elems
                    else None
                )

                # Extract year range from the specific HTML structure - UPDATED
                year = None
                start_date_elem = soup.find("span", {"itemprop": "startDate"})
                end_date_elem = soup.find("span", {"itemprop": "endDate"})

                if start_date_elem and end_date_elem:
                    start_year_link = start_date_elem.find("a")
                    end_year_link = end_date_elem.find("a")

                    if start_year_link and end_year_link:
                        start_text = start_year_link.get_text(strip=True)
                        end_text = end_year_link.get_text(strip=True)

                    if end_text.lower() in ["heute", "present"]:
                        year = f"{start_text} - Present"
                    else:
                        year = f"{start_text} - {end_text}"
                elif start_year_link:
                    year = start_year_link.get_text(strip=True)

                # Fallback to previous year extraction method
                if not year:
                    year_patterns = [
                        r"(\d{4})",  # Match 4-digit years
                        r"Jahr:\s*(\d{4})",
                        r"Year:\s*(\d{4})",
                        r"Erscheinungsjahr:\s*(\d{4})",
                    ]

                    for pattern in year_patterns:
                        year_match = re.search(pattern, response.text)
                        if year_match:
                            year = year_match.group(1)
                            break

                # Extract status - more robust approach
                status = "unknown"
                status_elem = soup.find("span", string=re.compile(r"Status"))
                if status_elem and status_elem.find_next_sibling("span"):
                    status = status_elem.find_next_sibling("span").get_text(strip=True)
                else:
                    # Try alternative approach
                    if re.search(r"abgeschlossen|completed", response.text, re.I):
                        status = "completed"
                    elif re.search(r"laufend|ongoing", response.text, re.I):
                        status = "ongoing"

                # Find seasons first
                seasons = self._extract_seasons(soup, anime_url)

                # Find episodes from all seasons
                episodes = self._extract_all_episodes(soup, anime_url, seasons)

                progress.update(task, completed=100)
                progress.stop()
                self.console.print("[green][+][/green] Details fetched!\n")
                time.sleep(0.5)
                if self.settings_manager.settings.get("clear_console", True):
                    clear()

                details = AnimeDetails(
                    title=title,
                    url=anime_url,
                    description=description,
                    episodes=episodes,
                    seasons=seasons,
                    genre=genres,
                    year=year,
                    status=status,
                    image_url=image_url,
                )
                return details

            except Exception as e:
                progress.update(task, description=f"[red]Failed: {str(e)}")
                self.console.print(f"[red]Error fetching details: {e}[/red]")
                return None

    def _extract_seasons(self, soup: BeautifulSoup, base_url: str) -> List[Season]:
        seasons = []

        # Look for season selector dropdown
        season_selector = soup.find("select", id="season")
        if season_selector:
            # Get all season options
            season_options = season_selector.find_all("option")

            for i, option in enumerate(season_options):
                try:
                    season_num = int(option.get("value", i + 1))
                    season_title = option.get_text(strip=True)

                    seasons.append(Season(number=season_num, title=season_title))
                except Exception as e:
                    continue
        else:

            # Look for season navigation links
            season_links = soup.find_all("a", href=re.compile(r"/staffel-(\d+)"))
            if season_links:
                season_numbers = set()
                for link in season_links:
                    match = re.search(r"/staffel-(\d+)", link.get("href", ""))
                    if match:
                        season_numbers.add(int(match.group(1)))

                # Sort and create seasons
                for season_num in sorted(season_numbers):
                    seasons.append(
                        Season(number=season_num, title=f"Staffel {season_num}")
                    )
            else:
                # Look for season indicators in episode URLs
                episode_links = soup.find_all(
                    "a", href=re.compile(r"/staffel-(\d+)/episode-")
                )
                if episode_links:
                    season_numbers = set()
                    for link in episode_links:
                        match = re.search(r"/staffel-(\d+)/", link.get("href", ""))
                        if match:
                            season_numbers.add(int(match.group(1)))

                    # Sort and create seasons
                    for season_num in sorted(season_numbers):
                        seasons.append(
                            Season(number=season_num, title=f"Staffel {season_num}")
                        )
                else:
                    # Last resort - check page text for season mentions
                    page_text = soup.get_text()
                    staffel_matches = re.findall(r"Staffel (\d+)", page_text)
                    if staffel_matches:
                        unique_seasons = sorted(set(int(s) for s in staffel_matches))

                        for season_num in unique_seasons:
                            seasons.append(
                                Season(number=season_num, title=f"Staffel {season_num}")
                            )
                    else:
                        seasons.append(Season(number=1, title="Staffel 1"))

        return seasons

    def _extract_all_episodes(
        self, soup: BeautifulSoup, base_url: str, seasons: List[Season]
    ) -> List[Episode]:
        """Extract episodes from all seasons"""
        all_episodes = []

        if not seasons:
            # Fallback to original episode extraction if no seasons found
            return self._extract_episodes(soup, base_url)

        for season in seasons:

            # Construct season URL
            parsed_url = urlparse(base_url)
            base_path = parsed_url.path

            # Replace or add season number in URL
            if "/staffel-" in base_path:
                season_url = re.sub(
                    r"/staffel-\d+", f"/staffel-{season.number}", base_url
                )
            else:
                # Add season to URL
                season_url = base_url.rstrip("/") + f"/staffel-{season.number}"

            try:
                # Fetch season page
                timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                response = self.session.get(season_url, timeout=timeout)
                response.raise_for_status()

                season_soup = BeautifulSoup(response.text, "html.parser")

                # Extract episodes from this season
                season_episodes = self._extract_episodes_from_season(
                    season_soup, season_url, season.number
                )

                all_episodes.extend(season_episodes)

            except Exception as e:
                # If season page fails, try to extract from main page
                if season.number == 1:
                    fallback_episodes = self._extract_episodes(soup, base_url)
                    all_episodes.extend(fallback_episodes)
                continue

        # Sort all episodes by season and episode number
        all_episodes.sort(key=lambda x: (getattr(x, "season", 1), x.number))

        return all_episodes

    def _extract_episodes_from_season(
        self, soup: BeautifulSoup, base_url: str, season_number: int
    ) -> List[Episode]:
        episodes = []

        # First try: Look for episode tables with season-specific classes
        episode_tds = soup.find_all(
            "td", class_=re.compile(rf"season{season_number}EpisodeID")
        )

        if not episode_tds:
            # Second try: Look for any episode TDs and filter by season
            all_episode_tds = soup.find_all(
                "td", class_=re.compile(r"season\d+EpisodeID")
            )
            episode_tds = [
                td
                for td in all_episode_tds
                if f"season{season_number}" in " ".join(td.get("class", []))
            ]

        for i, td in enumerate(episode_tds):
            try:
                # Find the episode link within the td
                episode_link = td.find(
                    "a",
                    href=re.compile(
                        rf"/anime/stream/.+/staffel-{season_number}/episode-\d+"
                    ),
                )
                if not episode_link:
                    # Try broader search
                    episode_link = td.find("a", href=re.compile(r"/episode-\d+"))

                if not episode_link:
                    continue

                href = episode_link.get("href")

                if not href.startswith("http"):
                    href = urljoin(base_url, href)

                # Extract episode number from the meta tag or URL
                episode_num = None
                meta_tag = td.find("meta", {"itemprop": "episodeNumber"})
                if meta_tag:
                    episode_num = int(meta_tag.get("content", 0))
                else:
                    # Extract from URL as fallback
                    ep_match = re.search(r"/episode-(\d+)", href)
                    episode_num = (
                        int(ep_match.group(1)) if ep_match else len(episodes) + 1
                    )

                # Get episode title from link text
                title = episode_link.get_text(strip=True)

                # Detect language from available language images/flags
                language = self._detect_episode_language(td)

                episode = Episode(
                    title=title, number=episode_num, url=href, language=language
                )
                episode.season = season_number  # Add season info
                episodes.append(episode)

            except Exception as e:
                continue

        # If no episodes found with TD method, try alternative approach
        if not episodes:
            episode_links = soup.find_all(
                "a",
                href=re.compile(
                    rf"/anime/stream/.+/staffel-{season_number}/episode-\d+"
                ),
            )

            for i, link in enumerate(episode_links):
                try:
                    href = link.get("href")
                    if not href.startswith("http"):
                        href = urljoin(base_url, href)

                    ep_match = re.search(r"/episode-(\d+)", href)
                    episode_num = int(ep_match.group(1)) if ep_match else i + 1

                    title = link.get_text(strip=True)
                    language = self._detect_episode_language(
                        link.parent if link.parent else link
                    )

                    episode = Episode(
                        title=title, number=episode_num, url=href, language=language
                    )
                    episode.season = season_number
                    episodes.append(episode)

                except Exception as e:
                    continue

        sorted_episodes = sorted(episodes, key=lambda x: x.number)
        return sorted_episodes

    def _detect_episode_language(self, container) -> List[str]:
        available_languages = []

        try:
            # look for all imgs in container
            lang_imgs = container.find_all(
                "img",
                src=re.compile(r"/(german|japanese-german|japanese-english)\.svg"),
            )

            for img in lang_imgs:
                src = img.get("src", "")
                data_lang_key = img.get("data-lang-key", "")
                title = img.get("title", "").lower()
                lang = None

                # get lang based on attr
                if "german.svg" in src and "japanese-german.svg" not in src:
                    lang = "Ger Dub"
                elif "japanese-german.svg" in src:
                    lang = "Ger Sub"
                elif "japanese-english.svg" in src:
                    lang = "Eng Sub"
                else:
                    # Fallback to data-lang-key
                    if data_lang_key == "1":
                        lang = "Ger Dub"
                    elif data_lang_key == "2":
                        lang = "Eng Sub"
                    elif data_lang_key == "3":
                        lang = "Ger Sub"
                    else:
                        # Fallback to title attributes
                        if "deutsch" in title and "untertitel" not in title:
                            lang = "Ger Dub"
                        elif "untertitel deutsch" in title:
                            lang = "Ger Sub"
                        elif "untertitel englisch" in title:
                            lang = "Eng Sub"

                if lang and lang not in available_languages:
                    available_languages.append(lang)

        except Exception as e:
            return available_languages if available_languages else ["Ger Dub"]

        return available_languages if available_languages else ["Ger Dub"]

    def _get_currently_selected_language(self, container) -> str:
        """Detect the currently selected language by looking for selectedLanguage class"""
        try:
            # Look for img with selectedLanguage class
            selected_img = container.find("img", class_="selectedLanguage")

            if selected_img:
                src = selected_img.get("src", "")
                data_lang_key = selected_img.get("data-lang-key", "")

                # Determine language from src or data-lang-key
                if "german.svg" in src and "japanese-german.svg" not in src:
                    return "Ger Dub"
                elif "japanese-german.svg" in src:
                    return "Ger Sub"
                elif "japanese-english.svg" in src:
                    return "Eng Sub"
                elif data_lang_key == "1":
                    return "Ger Dub"
                elif data_lang_key == "2":
                    return "Eng Sub"
                elif data_lang_key == "3":
                    return "Ger Sub"

        except Exception as e:
            return "Ger Dub"  # fallback

    def _get_lang_key_for_language(self, language: str) -> str:
        """Get data-lang-key value for given language"""
        lang_key_map = {"Ger Dub": "1", "Eng Sub": "2", "Ger Sub": "3"}
        return lang_key_map.get(language, "1")

    def _switch_episode_language(self, episode_url: str, target_language: str) -> None:
        """Switch AniWorld language by setting lang cookie and clearing cache."""
        lang_cookie_map = {"Ger Dub": "1", "Eng Sub": "2", "Ger Sub": "3"}

        lang_id = lang_cookie_map.get(target_language, "1")

        try:
            # Set the language cookie
            self.session.cookies.set("lang", lang_id, domain="aniworld.to")

            if hasattr(self, "_host_cache"):
                self._host_cache.clear()

            self.console.print(
                f"[green]✓ Language switched to {target_language} via cookie (lang={lang_id})[/green]"
            )

            sleep(1.5)

        except Exception as e:
            self.console.print(f"[red]Error switching language: {e}[/red]")

    def select_language(self, available_languages: List[str]) -> str:
        if len(available_languages) == 1:
            self.console.print(
                f"[green]✓[/green] Using only available language: [bold]{available_languages[0]}[/bold]"
            )
            return available_languages[0]

        # Display as inline options instead of table
        self.console.print("\n[bold cyan]Available Languages:[/bold cyan]")
        options_str = " | ".join(
            [
                f"[bold green]{i}[/bold green]. {lang}"
                for i, lang in enumerate(available_languages, 1)
            ]
        )
        self.console.print(f"  {options_str}")

        try:
            choice = IntPrompt.ask(
                "[input_prompt]Select language[/input_prompt]",
                default=1,
                show_default=True,
                console=self.console,
            )

            if 1 <= choice <= len(available_languages):
                selected = available_languages[choice - 1]
                self.console.print(
                    f"[green]✓[/green] Selected: [bold]{selected}[/bold]"
                )
                return selected
            else:
                self.console.print("[red]Invalid selection! Using default.[/red]")
                return available_languages[0]
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Using default language[/yellow]")
            return available_languages[0]

    def _extract_movies(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract movies from page - FIXED VERSION"""
        movies = []

        try:
            # Find movie/filme link with the correct selector
            movies_link = soup.find(
                "a", {"class": "active", "href": re.compile(r"/anime/stream/.+/filme")}
            )
            if not movies_link:
                # Fallback: try any filme link
                movies_link = soup.find("a", href=re.compile(r"/anime/stream/.+/filme"))

            if not movies_link:
                return movies

            movies_url = urljoin(base_url, movies_link["href"])

            # Fetch movies page
            timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
            response = self.session.get(movies_url, timeout=timeout)
            response.raise_for_status()

            movies_soup = BeautifulSoup(response.text, "html.parser")

            # Extract movie entries from seasonEpisodeTitle cells (correct selector)
            movie_cells = movies_soup.find_all("td", class_="seasonEpisodeTitle")

            for i, cell in enumerate(movie_cells, 1):
                try:
                    # Find the movie link
                    movie_link = cell.find(
                        "a", href=re.compile(r"/anime/stream/.+/filme/film-\d+")
                    )
                    if not movie_link:
                        continue

                    # Extract title from strong tag (main title)
                    strong_tag = movie_link.find("strong")
                    if strong_tag:
                        title = strong_tag.get_text(strip=True)
                    else:
                        # Fallback to full link text
                        title = movie_link.get_text(strip=True)
                        # Clean up if it contains extra info
                        if " - " in title:
                            title = title.split(" - ")[0].strip()

                    # Clean up title (remove [Movie] suffix if present)
                    title = re.sub(r"\s*\[Movie\].*$", "", title).strip()

                    url = urljoin(base_url, movie_link["href"])

                    movies.append(
                        {"number": i, "title": title, "url": url, "type": "movie"}
                    )

                except Exception as e:
                    continue

        except Exception as e:
            return movies

        return movies

    def get_episode_hosts(
        self, episode_url: str, language: str = "Ger Dub"
    ) -> List[HostLink]:
        """
        Extract host links from the episode page for the selected language.
        Language switching is handled via the lang cookie, and the page is reloaded accordingly.
        """
        hosts = []

        lang_key_map = {"Ger Dub": "1", "Eng Sub": "2", "Ger Sub": "3"}

        # determine the correct language id for the AniWorld cookie
        target_lang_key = lang_key_map.get(language, "1")

        # cache key based on episode + language
        cache_key = f"{episode_url}::{language}"

        if not hasattr(self, "_host_cache"):
            self._host_cache = {}

        # clear stale host cache for this episode + language
        if cache_key in self._host_cache:
            del self._host_cache[cache_key]

        try:
            # set language cookie
            self.session.cookies.set("lang", target_lang_key, domain="aniworld.to")
            sleep(0.5)

            timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
            response = self.session.get(episode_url, timeout=timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # look for all episode link elements
            episode_li_tags = soup.find_all("li", class_=re.compile(r"^episodeLink\d+"))

            host_links = []
            for li in episode_li_tags:
                li_lang_key = li.get("data-lang-key", "")
                li_style = li.get("style", "")

                # Match language and ensure it's not hidden
                if li_lang_key == target_lang_key and "display: none" not in li_style:
                    a_tag = li.find("a", class_="watchEpisode")
                    if a_tag:
                        host_links.append(a_tag)

            seen_hosts = set()
            for i, link in enumerate(host_links):
                try:
                    url = link.get("href")
                    if not url:
                        continue

                    if not url.startswith("http"):
                        url = urljoin(episode_url, url)

                    # Extract host name
                    host_name = "Unknown"
                    h4 = link.find("h4")
                    if h4:
                        host_name = h4.text.strip()
                    else:
                        icon = link.find("i", class_="icon")
                        if icon:
                            host_name = icon.get("title", "").strip() or "Unknown"

                    # Avoid duplicates
                    host_key = f"{host_name.lower()}_{language.lower()}"
                    if host_key in seen_hosts:
                        continue
                    seen_hosts.add(host_key)

                    # Guess quality based on text or fallback to SD
                    quality = (
                        "HD" if re.search(r"1080|720|HD", host_name, re.I) else "SD"
                    )

                    host_obj = HostLink(name=host_name, url=url, quality=quality)
                    hosts.append(host_obj)

                except Exception as e:
                    continue

            # Cache the hosts for this episode-language pair
            self._host_cache[cache_key] = hosts

            return hosts

        except Exception as e:
            return hosts

    def select_host_for_download(self, hosts: List[HostLink]) -> Optional[str]:
        if not hosts:
            self.console.print("[red]No hosts available![/red]")
            return None

        if len(hosts) == 1:
            self.console.print(
                f"[green]Using only available host: {hosts[0].name}[/green]"
            )
            selected_host = hosts[0]
        else:
            # Display host selection table
            table = Table(
                title="Available Hosts", show_header=True, header_style="bold cyan"
            )
            table.add_column("#", width=3)
            table.add_column("Host", style="green")
            table.add_column("Quality", style="yellow")

            for i, host in enumerate(hosts, 1):
                table.add_row(str(i), host.name, host.quality)

            self.console.print(table)

            try:
                choice = IntPrompt.ask(
                    "Select host for download",
                    default=1,
                    show_default=True,
                    console=self.console,
                )

                if 1 <= choice <= len(hosts):
                    selected_host = hosts[choice - 1]
                else:
                    self.console.print("[red]Invalid selection![/red]")
                    return None

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Cancelled by user[/yellow]")
                return None

        # Get the actual download URL by following the redirect
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console,
            ) as progress:
                task = progress.add_task("[cyan]Getting download URL...", total=None)

                # Follow the redirect to get the actual video URL
                timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                response = self.session.get(
                    selected_host.url, allow_redirects=True, timeout=timeout
                )
                final_url = response.url

                progress.update(
                    task, completed=100, description="[green]Download URL obtained!"
                )

                # display the download information
                download_panel = Panel(
                    f"[bold green]Download Ready![/bold green]\n\n"
                    f"[yellow]Host:[/yellow] {selected_host.name}\n"
                    f"[yellow]Quality:[/yellow] {selected_host.quality}\n"
                    f"[yellow]URL:[/yellow] {final_url}\n\n",
                    title="Download Information",
                    border_style="green",
                )
                self.console.print(download_panel)

                return final_url

        except Exception as e:
            self.console.print(f"[red]Error getting download URL: {e}[/red]")
            return None

    def display_anime_details(self, details: AnimeDetails):
        """Display anime information in a compact, professional format"""

        # Get movies
        try:
            timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
            response = self.session.get(details.url, timeout=timeout)
            soup = BeautifulSoup(response.text, "html.parser")
            movies = self._extract_movies(soup, details.url)
        except Exception as e:
            movies = []

        movie_count = len(movies)
        titled_movies = [m["title"] for m in movies if m["title"].strip()]
        movie_line = f"{movie_count} total"
        if titled_movies:
            movie_line += f" ({len(titled_movies)} titled)"

        mal_info = self.mal_client.search_anime(details.title)

        # if we got extra MAL info, override/add fields
        mal_status = (
            mal_info["status"]
            if mal_info and "status" in mal_info
            else details.status.capitalize()
        )
        mal_aired = (
            mal_info["aired"]
            if mal_info and "aired" in mal_info
            else details.year or "N/A"
        )
        mal_rating = mal_info["rating"] if mal_info and "rating" in mal_info else "N/A"

        # Main info panel content
        info_lines = [
            f"[bold white]{details.title}[/bold white]",
            "",
            f"[dim]{details.description[:250]}{'...' if len(details.description) > 250 else ''}[/dim]",
            "",
            f"[INFO] Aired:    [cyan]{mal_aired}[/cyan]",
            f"[INFO] Status:   [cyan]{mal_status}[/cyan]",
            f"[INFO] Rating:   [cyan]{mal_rating}[/cyan]",
            f"[INFO] Genres:   [cyan]{details.genre or 'N/A'}[/cyan]",
            f"[DATA] Seasons:  [cyan]{len(details.seasons)}[/cyan]   Episodes: [cyan]{len(details.episodes)}[/cyan]   Movies: [cyan]{movie_line}[/cyan]",
        ]

        anime_panel = Panel(
            "\n".join(info_lines),
            title="[bold]Anime Overview[/bold]",
            border_style="blue",
        )
        self.console.print(anime_panel)

        # Episodes Preview Table
        if details.episodes:
            table = Table(
                title="Episodes (First 15)", show_header=True, header_style="bold cyan"
            )
            table.add_column("Season", width=6)
            table.add_column("Ep#", width=5)
            table.add_column("Title", style="white", no_wrap=True)
            table.add_column("Languages", style="yellow")

            display_episodes = details.episodes[:15]
            for ep in display_episodes:
                try:
                    timeout = self.settings_manager.settings.get(
                        "timeout", Config.TIMEOUT
                    )
                    ep_response = self.session.get(ep.url, timeout=timeout)
                    ep_soup = BeautifulSoup(ep_response.text, "html.parser")
                    langs = self._detect_episode_language(ep_soup)
                    langs_short = self._shorten_languages(langs)
                    table.add_row(
                        str(getattr(ep, "season", 1)),
                        str(ep.number),
                        ep.title,
                        langs_short,
                    )
                except Exception as e:
                    table.add_row(
                        str(getattr(ep, "season", 1)),
                        str(ep.number),
                        ep.title,
                        "Unknown",
                    )

            if len(details.episodes) > 15:
                table.add_row(
                    "...", "...", f"... +{len(details.episodes) - 15} more", "..."
                )

            self.console.print(table)

    def _shorten_languages(self, langs: List[str]) -> str:
        """Convert verbose language names into short codes"""
        mapping = {"Ger Dub": "DE", "Ger Sub": "GER SUB", "Eng Sub": "ENG SUB"}
        return ", ".join([mapping.get(lang, lang.upper()) for lang in langs])

    def run(self):
        """Unified run: anime or series"""
        if not self.auth_manager.login_flow():
            return

        self.display_banner()
        while True:
            try:
                scraper_type = Prompt.ask(
                    "[cyan]What do you want?[/cyan]",
                    choices=["anime", "series"],
                    default="anime",
                )
                query = Prompt.ask(
                    "[bold cyan]Search query (type 'set' for settings)[/bold cyan]",
                    console=self.console,
                ).strip()
                if not query:
                    continue
                if query.lower() == "set":
                    clear()
                    self.settings_manager.show_settings_menu()
                    continue

                if scraper_type == "anime":
                    results = self.search_anime(query)
                    if not results:
                        self.console.print("[red]No results found![/red]")
                        continue

                    selected = self.display_search_results(results)
                    if not selected:  # User cancelled or invalid selection
                        continue

                    details = self.get_anime_details(selected["url"])
                    if details:
                        self.display_anime_details(details)
                        if details.episodes:
                            self.download_episodes_batch(details)

                else:  # series
                    crawler = SeriesCrawler(console=self.console)
                    # gv settings manager to series crawler
                    crawler.settings_manager = self.settings_manager

                    results = crawler.search_series(query)
                    if not results:
                        self.console.print("[red]No results found![/red]")
                        continue

                    crawler.display_search_results(results)
                    choice = IntPrompt.ask("Select number", default=1)
                    if not (1 <= choice <= len(results)):
                        continue
                    selected = results[choice - 1]

                    details = crawler.get_series_details(selected["url"])
                    if not details:
                        continue

                    if not details["episodes"]:
                        self.console.print("[red]No episodes found![/red]")
                        continue

                    # First display basic series info without language selection
                    crawler.display_series_info(details)

                    # Then get available languages and let user select
                    lang = crawler.select_series_language(details)
                    if not lang:
                        continue

                    # Display detailed info with selected language
                    crawler.display_detailed_series_info(details, lang)

                    selected_eps = crawler.select_series_episodes(details)
                    if not selected_eps:
                        self.console.print("[red]No valid episodes selected.[/red]")
                        continue

                    # Get host info (returns dict with host info, not just name)
                    host_info = crawler.select_series_host(selected_eps[0], lang)
                    if not host_info:
                        continue

                    # download episodes with host info
                    crawler.download_series_episodes(
                        details, selected_eps, lang, host_info
                    )

                again = Prompt.ask("Search again?", choices=["y", "n"], default="y")
                clear()
                if again == "n":
                    clear()
                    break

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Thanks for using AniDL![/yellow]")
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                continue


class SeriesCrawler:
    """Scraper for s.to"""

    def __init__(self, console: Console):
        self.console = console
        self.base_url = Config.SERIES_URL
        self.session = cloudscraper.create_scraper()
        self.session.headers.update(Config.DEFAULT_HEADERS)
        self.settings_manager = None  # Will be set by parent

    def search_series(self, query: str) -> List[Dict[str, str]]:
        """ "Search series by scraping /search page"""
        url = f"{self.base_url}/ajax/search"
        headers = {
            "Referer": f"{self.base_url}/search?q={quote_plus(query)}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"keyword": query}
        self.console.print(f"[cyan]Searching series: {query}...[/cyan]")

        try:
            res = self.session.post(
                url, headers=headers, data=data, timeout=Config.TIMEOUT
            )
            res.raise_for_status()

            results = []
            json_data = res.json()
            for item in json_data:
                link = item.get("link", "")
                title_raw = item.get("title", "")
                desc = item.get("description", "")

                # only main series page
                if link.startswith("/serie/stream/"):
                    path = link[14:]  # after /serie/stream/
                    if "/" not in path:  # no extra /staffel-x/episode-x
                        title_clean = re.sub(r"<[^>]+>", "", title_raw).strip()
                        title_clean = html.unescape(title_clean)
                        full_url = urljoin(self.base_url, link)
                        results.append(
                            {
                                "title": title_clean,
                                "url": full_url,
                                "description": html.unescape(desc),
                            }
                        )
            return results
        except Exception as e:
            self.console.print(f"[red]Error searching series: {e}[/red]")
            return []

    def get_series_details(self, series_url: str) -> Dict:
        """Get full series details: title, years, genres, fsk, imdb, description, episodes"""
        res = self.session.get(series_url, timeout=Config.TIMEOUT)
        soup = BeautifulSoup(res.text, "html.parser")

        title = soup.find("div", class_="series-title")
        series_name = title.find("span").text.strip() if title else "Unknown"

        start = end = fsk = imdb = genres = desc = None
        if title:
            years = title.find_all("a")
            if len(years) >= 2:
                start = years[0].text.strip()
                end = years[1].text.strip()
            fsk_div = title.find("div", class_="fsk")
            fsk = fsk_div["data-fsk"] if fsk_div else None
            imdb_link = title.find("a", class_="imdb-link")
            imdb = imdb_link["href"] if imdb_link else None

        genres = ", ".join([a.text.strip() for a in soup.select(".genres a")])
        desc_tag = soup.find("p", class_="seri_des")
        desc = desc_tag.get("data-full-description", "") if desc_tag else ""

        # Get seasons/episodes with improved episode extraction
        episodes = []
        season_links = soup.select('a[href*="/staffel-"]')
        season_urls = set(urljoin(self.base_url, a["href"]) for a in season_links)

        if not season_urls:
            season_urls.add(series_url)  # fallback: single season

        for s_url in season_urls:
            eps = self._get_episodes_from_season(s_url)
            episodes.extend(eps)

        # Remove duplicates based on URL
        unique_episodes = []
        seen_urls = set()
        for ep in episodes:
            if ep["url"] not in seen_urls:
                unique_episodes.append(ep)
                seen_urls.add(ep["url"])

        return {
            "title": series_name,
            "start": start,
            "end": end,
            "fsk": fsk,
            "imdb": imdb,
            "genres": genres,
            "description": desc,
            "episodes": unique_episodes,
        }

    def _get_episodes_from_season(self, season_url: str):
        """
        Get all episode URLs from a season page - improved to get English titles
        """
        res = self.session.get(season_url, timeout=Config.TIMEOUT)
        soup = BeautifulSoup(res.text, "html.parser")
        episodes = []
        seen_episodes = set()

        # Find episode links using the active/episode selector pattern
        episode_links = soup.select(
            'a[href*="/staffel-"][href*="/episode-"][data-episode-id]'
        )

        if not episode_links:
            # Fallback: try the old method
            episode_links = soup.select('a[href*="/staffel-"][href*="/episode-"]')

        for a in episode_links:
            href = a["href"]
            episode_id = href

            if episode_id not in seen_episodes:
                seen_episodes.add(episode_id)
                full_url = urljoin(self.base_url, href)

                # Get the proper English episode title by visiting the episode page
                english_title = self._get_english_episode_title(full_url)

                # Extract episode and season numbers for better organization
                season_match = re.search(r"staffel-(\d+)", href)
                episode_match = re.search(r"episode-(\d+)", href)
                season_num = season_match.group(1) if season_match else "1"
                episode_num = episode_match.group(1) if episode_match else "0"

                # Create a formatted title if we got the English title
                if english_title:
                    formatted_title = f"S{season_num.zfill(2)}E{episode_num.zfill(2)} - {english_title}"
                else:
                    # Fallback to link text/title
                    fallback_title = a.get("title") or a.text.strip()
                    formatted_title = f"S{season_num.zfill(2)}E{episode_num.zfill(2)} - {fallback_title}"

                episodes.append(
                    {
                        "title": formatted_title,
                        "english_title": english_title or "Unknown",
                        "season": int(season_num),
                        "episode": int(episode_num),
                        "url": full_url,
                    }
                )

        # Sort episodes by season and episode number
        episodes.sort(key=lambda x: (x["season"], x["episode"]))
        return episodes

    def _get_english_episode_title(self, episode_url: str) -> str:
        """
        Extract English episode title from episode page
        """
        try:
            timeout = (
                self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                if self.settings_manager
                else Config.TIMEOUT
            )
            res = self.session.get(episode_url, timeout=timeout)
            soup = BeautifulSoup(res.text, "html.parser")

            # Look for the English episode title
            english_title_elem = soup.find("small", class_="episodeEnglishTitle")
            if english_title_elem:
                return english_title_elem.text.strip()

            # Fallback: look for the pattern in h2 tag
            h2_tag = soup.find("h2")
            if h2_tag:
                small_tag = h2_tag.find("small", class_="episodeEnglishTitle")
                if small_tag:
                    return small_tag.text.strip()

            return None

        except Exception as e:
            return None

    def get_episode_hosts(
        self, episode_url: str, language: str = "Ger Dub"
    ) -> List[HostLink]:
        """
        Extract host links from the episode page for the selected language.
        Language switching is handled via the lang cookie, and the page is reloaded accordingly.
        """
        hosts = []

        lang_key_map = {"Ger Dub": "1", "Eng Sub": "2", "Ger Sub": "3"}

        # Determine the correct language ID for the AniWorld cookie
        target_lang_key = lang_key_map.get(language, "1")

        # Cache key based on episode + language
        cache_key = f"{episode_url}::{language}"

        if not hasattr(self, "_host_cache"):
            self._host_cache = {}

        # Clear stale host cache for this episode + language
        if cache_key in self._host_cache:
            del self._host_cache[cache_key]

        try:
            # Set language cookie
            self.session.cookies.set("lang", target_lang_key, domain="aniworld.to")

            # Add a small delay to ensure cookie is processed
            sleep(0.5)

            timeout = self.settings_manager.settings.get("timeout", Config.TIMEOUT)
            response = self.session.get(episode_url, timeout=timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Look for all episode link elements
            episode_li_tags = soup.find_all("li", class_=re.compile(r"^episodeLink\d+"))

            host_links = []
            for li in episode_li_tags:
                li_lang_key = li.get("data-lang-key", "")
                li_style = li.get("style", "")

                # Match language and ensure it's not hidden
                if li_lang_key == target_lang_key and "display: none" not in li_style:
                    a_tag = li.find("a", class_="watchEpisode")
                    if a_tag:
                        host_links.append(a_tag)

            seen_hosts = set()
            for i, link in enumerate(host_links):
                try:
                    url = link.get("href")
                    if not url:
                        continue

                    if not url.startswith("http"):
                        url = urljoin(episode_url, url)

                    # Extract host name
                    host_name = "Unknown"
                    h4 = link.find("h4")
                    if h4:
                        host_name = h4.text.strip()
                    else:
                        icon = link.find("i", class_="icon")
                        if icon:
                            host_name = icon.get("title", "").strip() or "Unknown"

                    # Avoid duplicates
                    host_key = f"{host_name.lower()}_{language.lower()}"
                    if host_key in seen_hosts:
                        continue
                    seen_hosts.add(host_key)

                    # Guess quality based on text or fallback to SD
                    quality = (
                        "HD" if re.search(r"1080|720|HD", host_name, re.I) else "SD"
                    )

                    host_obj = HostLink(name=host_name, url=url, quality=quality)
                    hosts.append(host_obj)

                except Exception as e:
                    continue

            # Cache the hosts for this episode-language pair
            self._host_cache[cache_key] = hosts

            return hosts

        except Exception as e:
            return hosts

    def detect_series_languages(self, soup: BeautifulSoup) -> List[str]:
        """Detect available languages from episode page by checking data-lang-key attributes"""
        langs = []
        try:
            # Check for language keys in episode host list items
            lang_keys = set()
            for li in soup.select("li[data-lang-key]"):
                lang_key = li.get("data-lang-key")
                if lang_key:
                    lang_keys.add(lang_key)

            # Map language keys to display names
            lang_mapping = {"1": "Ger Dub", "2": "Eng Dub"}

            for key in sorted(lang_keys):
                if key in lang_mapping:
                    langs.append(lang_mapping[key])

        except Exception as e:
            return langs or ["Ger Dub"]  # Default fallback

    def switch_series_language_cookie(self, lang: str):
        """Set language cookie for s.to series: 1=German, 2=English"""
        lang_id = "1" if lang == "Ger Dub" else "2"
        try:
            self.session.cookies.set("lang", lang_id, domain="s.to")
            self.console.print(
                f"[green]✓[/green] Language set to [bold]{lang}[/bold] via cookie (lang={lang_id})"
            )
        except Exception as e:
            return False

    def display_series_info(self, details: dict):
        """Display basic series information without language selection"""
        info_lines = [
            f"[bold white]{details['title']}[/bold white]",
            "",
            f"[dim]{details['description'][:250]}{'...' if len(details['description']) > 250 else ''}[/dim]",
            "",
            f"[INFO] Years:    [cyan]{details['start']} - {details['end']}[/cyan]",
            f"[INFO] Genres:   [cyan]{details['genres'] or 'N/A'}[/cyan]",
            f"[INFO] FSK:      [cyan]{details['fsk'] or 'N/A'}[/cyan]",
            f"[INFO] IMDB:     [cyan]{details['imdb'] or 'N/A'}[/cyan]",
            f"[DATA] Episodes: [cyan]{len(details['episodes'])}[/cyan]",
        ]

        series_panel = Panel(
            "\n".join(info_lines),
            title="[bold]Series Overview[/bold]",
            border_style="blue",
        )
        self.console.print(series_panel)

    def select_series_language(self, details: dict) -> Optional[str]:
        """Select language before showing detailed episode info"""
        try:
            # Get available languages from first episode
            if not details["episodes"]:
                self.console.print("[red]No episodes found![/red]")
                return None

            timeout = (
                self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                if self.settings_manager
                else Config.TIMEOUT
            )
            first_ep_res = self.session.get(
                details["episodes"][0]["url"], timeout=timeout
            )
            first_soup = BeautifulSoup(first_ep_res.text, "html.parser")
            langs = self.detect_series_languages(first_soup)

            # Language selection
            if len(langs) == 1:
                selected_lang = langs[0]
                self.console.print(
                    f"[green]✓[/green] Using only available language: [bold]{selected_lang}[/bold]"
                )
            else:
                self.console.print("\n[bold cyan]Available Languages:[/bold cyan]")
                for idx, lang in enumerate(langs, 1):
                    self.console.print(f"[green]{idx}[/green]: {lang}")
                lang_choice = IntPrompt.ask("Select language", default=1)
                if not (1 <= lang_choice <= len(langs)):
                    return None
                selected_lang = langs[lang_choice - 1]

            # Set language cookie
            self.switch_series_language_cookie(selected_lang)
            return selected_lang

        except Exception as e:
            self.console.print(f"[red]Error selecting language: {e}[/red]")
            return "Ger Dub"

    def display_detailed_series_info(self, details: dict, selected_lang: str):
        """Display detailed episode information with selected language"""
        try:
            # Episodes Preview Table with English titles
            table = Table(
                title=f"Episodes (First 20) - {selected_lang}",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("Season", width=6)
            table.add_column("Ep#", width=5)
            table.add_column(
                "English Title", style="white", no_wrap=False, max_width=40
            )
            table.add_column("Status", style="yellow")

            display_episodes = details["episodes"][:20]  # Show more episodes
            timeout = (
                self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                if self.settings_manager
                else Config.TIMEOUT
            )

            for ep in display_episodes:
                try:
                    # Check if episode has hosts in selected language
                    hosts = self.get_episode_hosts(ep["url"], language=selected_lang)
                    status = f"✓ {len(hosts)} hosts" if hosts else "✗ No hosts"

                    table.add_row(
                        str(ep["season"]),
                        str(ep["episode"]),
                        ep["english_title"],
                        status,
                    )
                except Exception as e:
                    table.add_row(
                        str(ep.get("season", "?")),
                        str(ep.get("episode", "?")),
                        ep.get("english_title", "Error loading"),
                        "Unknown",
                    )

            if len(details["episodes"]) > 20:
                table.add_row(
                    "...",
                    "...",
                    f"... +{len(details['episodes']) - 20} more episodes",
                    "...",
                )

            self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]Error displaying detailed series info: {e}[/red]")

    def display_search_results(self, results):
        """Display search results in a table"""
        table = Table(title="🔍 Search Results", header_style="bold magenta")
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", style="cyan")
        table.add_column("Description", style="white", overflow="fold")

        for i, r in enumerate(results, 1):
            desc = (
                (r["description"][:60] + "...")
                if len(r["description"]) > 60
                else r["description"]
            )
            table.add_row(str(i), r["title"], desc)
        self.console.print(table)

    def select_series_episodes(self, details):
        """Let user select episodes to download"""
        self.console.print("\n[bold cyan]Available episodes:[/bold cyan]")
        self.console.print("[dim]Examples: 1 | 1-5 | 1,3,5 | 1-3,7-9 | all[/dim]")
        ep_input = Prompt.ask("Which episodes to download?", default="1").strip()
        episode_numbers = EpisodeSelector.parse_episode_selection(
            ep_input, len(details["episodes"])
        )
        return [
            details["episodes"][i - 1]
            for i in episode_numbers
            if 0 <= i - 1 < len(details["episodes"])
        ]

    def select_series_host(self, episode, lang):
        """Let user select host for downloading"""
        hosts = self.get_episode_hosts(episode["url"], language=lang)

        if not hosts:
            self.console.print("[red]No hosts found for this language![/red]")
            return None

        # Display hosts in a professional table
        table = Table(
            title="Available Hosts", show_header=True, header_style="bold green"
        )
        table.add_column("#", width=3)
        table.add_column("Host", style="cyan")
        table.add_column("Status", style="yellow")

        for i, h in enumerate(hosts, 1):
            table.add_row(str(i), h["host"], "Available")

        self.console.print(table)

        try:
            index = IntPrompt.ask("Select host", default=1)
            if not (1 <= index <= len(hosts)):
                self.console.print("[red]Invalid host selection[/red]")
                return None
            return hosts[index - 1]
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Cancelled by user[/yellow]")
            return None

    def download_series_episodes(self, details, selected_eps, lang, host_info):
        """Download selected episodes using the selected host"""
        for ep in selected_eps:
            try:
                # Get hosts for this specific episode
                hosts = self.get_episode_hosts(ep["url"], language=lang)

                # Find the matching host
                match = next(
                    (
                        h
                        for h in hosts
                        if h["host"].lower() == host_info["host"].lower()
                    ),
                    None,
                )
                if not match:
                    self.console.print(
                        f"[yellow]Skipping {ep['title']} - Host '{host_info['host']}' not found[/yellow]"
                    )
                    continue

                # Get the actual download URL
                timeout = (
                    self.settings_manager.settings.get("timeout", Config.TIMEOUT)
                    if self.settings_manager
                    else Config.TIMEOUT
                )
                response = self.session.get(
                    match["url"], allow_redirects=True, timeout=timeout
                )
                download_url = response.url

                # Create safe filename using English title
                safe_title = "".join(
                    c for c in details["title"] if c.isalnum() or c in (" ", "-", "_")
                ).strip()
                safe_english_title = "".join(
                    c
                    for c in ep["english_title"]
                    if c.isalnum() or c in (" ", "-", "_")
                ).strip()

                filename = f"{safe_title}_S{str(ep['season']).zfill(2)}E{str(ep['episode']).zfill(2)}_{safe_english_title}_{lang.replace(' ', '_')}.mp4"

                # Use settings manager for download directory
                if hasattr(self, "settings_manager") and self.settings_manager:
                    downloads_dir = self.settings_manager.settings.get(
                        "download_folder", "downloads"
                    )
                else:
                    downloads_dir = "downloads"

                os.makedirs(downloads_dir, exist_ok=True)
                old_dir = os.getcwd()
                os.chdir(downloads_dir)

                # download the episode
                self.console.print(f"[cyan]Downloading {filename}...[/cyan]")
                dl.download(download_url)

                os.chdir(old_dir)
                self.console.print(f"[green]✓ Downloaded {filename}[/green]")

            except Exception as e:
                self.console.print(f"[red]Failed to download {ep['title']}: {e}[/red]")


if __name__ == "__main__":
    downloader = AniDL()
    downloader.run()
