import json
import os
import platform
import sys
import shutil
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm, IntPrompt, FloatPrompt
from rich.panel import Panel
from rich.columns import Columns
from rich.align import Align
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.layout import Layout
from rich.tree import Tree
import time

DEFAULT_SETTINGS = {
    "download_folder": "downloads",
    "default_language": None,
    "default_host": None,
    "auto_login": True,
    "clear_console": True,
    "download_quality": "HD",
    "verbose_logging": False,
    "theme": "dark",
    "check_updates": True,
    "timeout": 30,
    "proxy": None,
    "max_concurrent_downloads": 3,
    "auto_retry": True,
    "retry_attempts": 3,
    "notification_sounds": True,
    "auto_organize": False,
    "compression_level": "medium",
    "download_speed_limit": None,  # KB/s, None for unlimited
    "ui_animation_speed": "normal",
    "quality": "816p",  # default video quality
    "license_telemetry": True  # send basic login info to license-abuse webhook, if configured
}

# Define valid values for each setting
VALID_VALUES = {
    "default_language": ["Ger Sub", "Ger Dub", "Eng Sub", "Jpn Sub", "Eng Dub", None],
    "download_quality": ["4K", "HD", "SD", "Auto"],
    "theme": ["dark", "light", "auto"],
    "auto_login": [True, False],
    "clear_console": [True, False],
    "verbose_logging": [True, False],
    "check_updates": [True, False],
    "auto_retry": [True, False],
    "notification_sounds": [True, False],
    "auto_organize": [True, False],
    "compression_level": ["low", "medium", "high"],
    "ui_animation_speed": ["slow", "normal", "fast", "disabled"],
    "quality": ["480p", "720p", "816p"],
    "license_telemetry": [True, False]
}

# Setting descriptions for better UX
SETTING_DESCRIPTIONS = {
    "download_folder": "Where downloaded files will be saved",
    "default_language": "Preferred language for downloads",
    "default_host": "Default server/host to connect to",
    "auto_login": "Automatically login on startup",
    "clear_console": "Clear screen between operations",
    "download_quality": "Default video quality preference",
    "verbose_logging": "Show detailed operation logs",
    "theme": "Application color scheme",
    "check_updates": "Check for updates on startup",
    "timeout": "Network timeout in seconds",
    "proxy": "Proxy server (format: host:port)",
    "max_concurrent_downloads": "Maximum simultaneous downloads",
    "auto_retry": "Retry failed downloads automatically",
    "retry_attempts": "Number of retry attempts",
    "notification_sounds": "Play sounds for notifications",
    "auto_organize": "Organize downloads by category",
    "compression_level": "File compression level",
    "download_speed_limit": "Speed limit in KB/s (None = unlimited)",
    "ui_animation_speed": "Interface animation speed",
    "quality": "Preferred video quality for downloads",
    "license_telemetry": "Send basic login info (username, hostname, OS, timestamp) to the configured webhook for license-abuse monitoring. No effect if no webhook is configured."
}

# Setting categories for better organization
SETTING_CATEGORIES = {
    "Download": ["download_folder", "download_quality", "max_concurrent_downloads", 
                "auto_retry", "retry_attempts", "download_speed_limit", "compression_level"],
    "Network": ["default_host", "timeout", "proxy", "check_updates"],
    "Interface": ["theme", "clear_console", "verbose_logging", "notification_sounds", 
                 "ui_animation_speed"],
    "Language": ["default_language"],
    "Automation": ["auto_login", "auto_organize"],
    "Privacy": ["license_telemetry"]
}

def cls():
    if platform.system() == 'Windows':
        os.system('cls & title AniDL - made by halid2ud')
    elif platform.system() == 'Linux':
        os.system('clear')
        sys.stdout.write("\033]0;AniDL - made by halid2ud\007")
        sys.stdout.flush() 
    elif platform.system() == 'Darwin':
        os.system("clear && printf '\033[3J'")
        os.system('echo -n -e "\033]0;AniDL - made by halid2ud\007"')

class SettingsManager:
    def __init__(self, settings_file='settings.json', console=None):
        self.settings_file = settings_file
        self.console = console or Console()
        self.settings = {}
        self.load_settings()

    def load_settings(self):
        """Load settings with error handling and validation"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                
                # Merge with defaults to ensure all settings exist
                self.settings = DEFAULT_SETTINGS.copy()
                self.settings.update(loaded_settings)
                
                # Remove any obsolete settings
                self.settings = {k: v for k, v in self.settings.items() if k in DEFAULT_SETTINGS}
                
            except (json.JSONDecodeError, Exception) as e:
                self.console.print(f"[red]Error loading settings: {e}[/red]")
                self.console.print("[yellow]Using default settings...[/yellow]")
                self.settings = DEFAULT_SETTINGS.copy()
        else:
            self.settings = DEFAULT_SETTINGS.copy()
            self.save_settings()

    def save_settings(self):
        """Save settings"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            self.console.print(f"[red]Error saving settings: {e}[/red]")

    def reset_to_defaults(self):
        """Reset to defaults with confirmation"""
        self.settings = DEFAULT_SETTINGS.copy()
        self.save_settings()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Resetting settings...", total=1)
            time.sleep(1)  # Simulate reset time
            progress.update(task, completed=1)
        
        self.console.print("[green][+] Settings have been reset to defaults.[/green]")

    def validate_folder_path(self, folder_path):
        """Enhanced folder validation"""
        if not folder_path or folder_path.strip() == "":
            return False, "Folder path cannot be empty"
        
        folder_path = Path(folder_path.strip()).expanduser()
        
        try:
            if folder_path.exists():
                if folder_path.is_dir():
                    # Check if writable
                    test_file = folder_path / ".write_test"
                    try:
                        test_file.touch()
                        test_file.unlink()
                        return True, f"Folder exists and is writable"
                    except:
                        return False, "Folder exists but is not writable"
                else:
                    return False, "Path exists but is not a folder"
            else:
                folder_path.mkdir(parents=True, exist_ok=True)
                return True, f"Created folder: {folder_path}"
        except Exception as e:
            return False, f"Cannot create folder: {e}"

    def validate_proxy(self, proxy_string):
        """Validate proxy format"""
        if not proxy_string or proxy_string.strip().lower() in ['none', '']:
            return True, "No proxy configured"
        
        proxy = proxy_string.strip()
        
        # Basic format validation (host:port)
        if ':' in proxy:
            try:
                host, port = proxy.rsplit(':', 1)
                port_num = int(port)
                if 1 <= port_num <= 65535:
                    return True, f"Valid proxy format: {proxy}"
                else:
                    return False, "Port must be between 1 and 65535"
            except ValueError:
                return False, "Invalid port number"
        else:
            return False, "Proxy format should be host:port"

    def get_disk_space(self, path):
        """Get available disk space for download folder"""
        try:
            if os.path.exists(path):
                total, used, free = shutil.disk_usage(path)
                return free // (1024**3)  # Return GB
        except:
            pass
        return None

    def validate_settings(self):
        """Comprehensive settings validation"""
        errors = []
        warnings = []
        
        # Validate download folder
        folder = self.settings.get("download_folder")
        if folder:
            valid, message = self.validate_folder_path(folder)
            if not valid:
                errors.append(f"Download folder: {message}")
            else:
                if "Created folder" in message:
                    warnings.append(message)
                
                # Check disk space
                free_space = self.get_disk_space(folder)
                if free_space is not None and free_space < 1:
                    warnings.append(f"Low disk space: {free_space}GB remaining")
        
        # Validate timeout
        timeout = self.settings.get("timeout")
        if isinstance(timeout, (int, float)) and timeout <= 0:
            errors.append("Timeout must be greater than 0")
        elif isinstance(timeout, (int, float)) and timeout > 300:
            warnings.append("Timeout is very high (>5 minutes)")
        
        # Validate proxy
        proxy = self.settings.get("proxy")
        if proxy:
            valid, message = self.validate_proxy(proxy)
            if not valid:
                errors.append(f"Proxy: {message}")
        
        # Validate download limits
        max_downloads = self.settings.get("max_concurrent_downloads", 3)
        if max_downloads > 10:
            warnings.append("High concurrent downloads may impact performance")
        
        speed_limit = self.settings.get("download_speed_limit")
        if speed_limit and speed_limit < 10:
            warnings.append("Very low speed limit may cause timeouts")
        
        # Validate retry attempts
        retry_attempts = self.settings.get("retry_attempts", 3)
        if retry_attempts > 10:
            warnings.append("High retry attempts may cause long delays")
        
        # Validate all restricted settings
        for key, valid_options in VALID_VALUES.items():
            current_value = self.settings.get(key)
            if current_value is not None and current_value not in valid_options:
                errors.append(f"{key.replace('_', ' ').title()}: invalid value '{current_value}'")
        
        # Display results
        if errors:
            self.console.print("\n[red][!] Validation Errors:[/red]")
            for error in errors:
                self.console.print(f"  [red]* {error}[/red]")
        
        if warnings:
            self.console.print("\n[yellow][!] Warnings:[/yellow]")
            for warning in warnings:
                self.console.print(f"  [yellow]* {warning}[/yellow]")
        
        if not errors and not warnings:
            self.console.print("[green][+] All settings validated successfully![/green]")
        elif not errors:
            self.console.print("[green][+] Settings are valid (with warnings)[/green]")
        
        return len(errors) == 0

    def show_settings_tree(self):
        """Display settings organized by category"""
        tree = Tree("Settings Configuration", style="bold cyan")
        
        for category, setting_keys in SETTING_CATEGORIES.items():
            category_node = tree.add(f"[+] {category}", style="bold")
            
            for key in setting_keys:
                if key in self.settings:
                    value = self.settings[key]
                    display_value = "None" if value is None else str(value)
                    
                    # Add visual indicators
                    if isinstance(value, bool):
                        icon = "[Y]" if value else "[N]"
                        display_value = f"{icon} {display_value}"
                    elif key == "download_folder" and value:
                        free_space = self.get_disk_space(value)
                        if free_space:
                            display_value += f" ({free_space}GB free)"
                    
                    setting_text = f"{key.replace('_', ' ').title()}: [green]{display_value}[/green]"
                    category_node.add(setting_text)
        
        return tree

    def show_settings_menu(self):
        """Enhanced settings menu with categories and search"""
        while True:
            if self.settings.get("clear_console", True):
                os.system('cls' if os.name == 'nt' else 'clear')
            
            # Header
            header = Panel(
                Align.center(
                    "[bold cyan] Settings Manager[/bold cyan]\n"
                ),
                title="Settings", 
                border_style="cyan",
                padding=(1, 2)
            )
            self.console.print(header)
            
            # Show settings tree
            tree = self.show_settings_tree()
            self.console.print(tree)
            
            # Menu options
            menu_panel = Panel(
                "[bold]Commands:[/bold]\n"
                "* Type [cyan]setting name[/cyan] to modify\n"
                "* [cyan]category[/cyan] - Show category settings\n"
                "* [cyan]search <term>[/cyan] - Search settings\n"
                "* [cyan]export[/cyan] - Export settings\n"
                "* [cyan]import[/cyan] - Import settings\n"
                "* [cyan]reset[/cyan] - Reset to defaults\n"
                "* [cyan]validate[/cyan] - Validate configuration\n"
                "* [cyan]back[/cyan] - Return to main menu",
                title="Menu",
                border_style="blue"
            )
            self.console.print(menu_panel)

            choice = Prompt.ask("[cyan]Enter command[/cyan]", default="back").strip()
            
            if choice.lower() == "back":
                cls()
                break
            elif choice.lower() == "reset":
                if Confirm.ask("[?] Reset all settings to defaults?"):
                    self.reset_to_defaults()
            elif choice.lower() == "validate":
                self.validate_settings()
                Prompt.ask("[dim]Press Enter to continue...[/dim]")
            elif choice.lower() == "export":
                self.export_settings()
            elif choice.lower() == "import":
                self.import_settings()
            elif choice.lower().startswith("search "):
                search_term = choice[7:].strip()
                self.search_settings(search_term)
            elif choice.lower() in [cat.lower() for cat in SETTING_CATEGORIES.keys()]:
                self.show_category_settings(choice.lower())
            else:
                self.update_setting(choice)

    def search_settings(self, search_term):
        """Search for settings by name or description"""
        matches = []
        search_term = search_term.lower()
        
        for key, value in self.settings.items():
            key_name = key.replace('_', ' ')
            description = SETTING_DESCRIPTIONS.get(key, "")
            
            if (search_term in key_name.lower() or 
                search_term in description.lower() or 
                search_term in str(value).lower()):
                matches.append((key, value, description))
        
        if matches:
            table = Table(title=f"[>] Search Results for '{search_term}'")
            table.add_column("Setting", style="bold")
            table.add_column("Value", style="green")
            table.add_column("Description", style="dim")
            
            for key, value, desc in matches:
                display_value = "None" if value is None else str(value)
                table.add_row(key.replace('_', ' ').title(), display_value, desc)
            
            self.console.print(table)
        else:
            self.console.print(f"[yellow]No settings found matching '{search_term}'[/yellow]")
        
        Prompt.ask("[dim]Press Enter to continue...[/dim]")

    def show_category_settings(self, category):
        """Show settings for a specific category"""
        category_title = category.title()
        if category_title in SETTING_CATEGORIES:
            setting_keys = SETTING_CATEGORIES[category_title]
            
            table = Table(title=f"[+] {category_title} Settings")
            table.add_column("Setting", style="bold")
            table.add_column("Value", style="green")
            table.add_column("Description", style="dim")
            
            for key in setting_keys:
                if key in self.settings:
                    value = self.settings[key]
                    display_value = "None" if value is None else str(value)
                    description = SETTING_DESCRIPTIONS.get(key, "")
                    table.add_row(key.replace('_', ' ').title(), display_value, description)
            
            self.console.print(table)
            
            if Confirm.ask("Modify a setting from this category?"):
                setting_name = Prompt.ask("Enter setting name")
                self.update_setting(setting_name)
        else:
            self.console.print(f"[red]Category '{category}' not found[/red]")
            Prompt.ask("[dim]Press Enter to continue...[/dim]")

    def export_settings(self):
        """Export settings to a file"""
        try:
            export_file = Prompt.ask("Export file name", default="exported_settings.json")
            if not export_file.endswith('.json'):
                export_file += '.json'
            
            export_data = {
                "exported_at": datetime.now().isoformat(),
                "version": "1.0",
                "settings": self.settings
            }
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
            
            self.console.print(f"[green][+] Settings exported to {export_file}[/green]")
        except Exception as e:
            self.console.print(f"[red]Export failed: {e}[/red]")
        
        Prompt.ask("[dim]Press Enter to continue...[/dim]")

    def import_settings(self):
        """Import settings from a file"""
        try:
            import_file = Prompt.ask("Import file name")
            
            if not os.path.exists(import_file):
                self.console.print(f"[red]File '{import_file}' not found[/red]")
                return
            
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Handle different import formats
            if "settings" in import_data:
                imported_settings = import_data["settings"]
            else:
                imported_settings = import_data
            
            # Validate imported settings
            valid_settings = {}
            for key, value in imported_settings.items():
                if key in DEFAULT_SETTINGS:
                    valid_settings[key] = value
            
            if valid_settings:
                self.console.print(f"[yellow]Found {len(valid_settings)} valid settings to import[/yellow]")
                
                if Confirm.ask("Import these settings?"):
                    # Import settings
                    self.settings.update(valid_settings)
                    self.save_settings()
                    
                    self.console.print("[green][+] Settings imported successfully[/green]")
                    
                    # Validate after import
                    if not self.validate_settings():
                        self.console.print("[yellow]Settings validation failed. Please review.[/yellow]")
            else:
                self.console.print("[red]No valid settings found in import file[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Import failed: {e}[/red]")
        
        Prompt.ask("[dim]Press Enter to continue...[/dim]")

    def update_setting(self, key_name):
        """Enhanced setting update with better UX"""
        key = key_name.lower().replace(' ', '_')
        if key not in self.settings:
            # Try to find similar settings
            similar = [k for k in self.settings.keys() if key in k.lower()]
            if similar:
                self.console.print(f"[yellow]'{key_name}' not found. Did you mean:[/yellow]")
                for s in similar[:3]:
                    self.console.print(f"  * {s.replace('_', ' ').title()}")
            else:
                self.console.print(f"[red]Unknown setting: {key_name}[/red]")
            Prompt.ask("[dim]Press Enter to continue...[/dim]")
            return
        
        current_value = self.settings[key]
        description = SETTING_DESCRIPTIONS.get(key, "")
        
        # Show setting info
        info_panel = Panel(
            f"[bold]{key_name.replace('_', ' ').title()}[/bold]\n"
            f"[dim]{description}[/dim]\n"
            f"Current value: [green]{current_value if current_value is not None else 'None'}[/green]",
            title="Setting Info",
            border_style="blue"
        )
        self.console.print(info_panel)
        
        # Handle different setting types
        if key in VALID_VALUES:
            new_value = self._handle_choice_setting(key, current_value)
        elif key == "download_folder":
            new_value = self._handle_folder_setting(key, current_value)
        elif key == "timeout":
            new_value = self._handle_numeric_setting(key, current_value, int, 1, 300)
        elif key == "max_concurrent_downloads":
            new_value = self._handle_numeric_setting(key, current_value, int, 1, 20)
        elif key == "retry_attempts":
            new_value = self._handle_numeric_setting(key, current_value, int, 0, 20)
        elif key == "download_speed_limit":
            new_value = self._handle_speed_limit_setting(key, current_value)
        elif key == "proxy":
            new_value = self._handle_proxy_setting(key, current_value)
        else:
            new_value = self._handle_text_setting(key, current_value)
        
        if new_value != "CANCELLED":
            self.settings[key] = new_value
            self.save_settings()
            self.console.print(f"[green][+] Updated {key_name.replace('_', ' ').title()} to '{new_value}'[/green]")
        
        Prompt.ask("[dim]Press Enter to continue...[/dim]")

    def _handle_choice_setting(self, key, current_value):
        """Handle settings with predefined choices"""
        valid_options = VALID_VALUES[key]
        
        table = Table(title="Options")
        table.add_column("Option", style="bold")
        table.add_column("Value")
        table.add_column("Status")
        
        for i, option in enumerate(valid_options, 1):
            display_opt = "None" if option is None else str(option)
            status = "[*] Current" if option == current_value else ""
            table.add_row(str(i), display_opt, status)
        
        self.console.print(table)
        
        try:
            choice = IntPrompt.ask(f"Select option (1-{len(valid_options)})", 
                                 choices=[str(i) for i in range(1, len(valid_options) + 1)])
            return valid_options[choice - 1]
        except KeyboardInterrupt:
            return "CANCELLED"

    def _handle_folder_setting(self, key, current_value):
        """Handle folder path settings"""
        while True:
            new_value = Prompt.ask(f"Enter folder path", default=current_value or "downloads")
            
            if new_value.strip().lower() == 'none':
                return None
            
            valid, message = self.validate_folder_path(new_value)
            if valid:
                self.console.print(f"[green][+] {message}[/green]")
                return new_value
            else:
                self.console.print(f"[red][-] {message}[/red]")
                if not Confirm.ask("Try again?"):
                    return "CANCELLED"

    def _handle_numeric_setting(self, key, current_value, value_type, min_val, max_val):
        """Handle numeric settings with validation"""
        while True:
            try:
                prompt_class = IntPrompt if value_type == int else FloatPrompt
                new_value = prompt_class.ask(f"Enter value ({min_val}-{max_val})", default=current_value)
                
                if min_val <= new_value <= max_val:
                    return new_value
                else:
                    self.console.print(f"[red]Value must be between {min_val} and {max_val}[/red]")
                    if not Confirm.ask("Try again?"):
                        return "CANCELLED"
            except KeyboardInterrupt:
                return "CANCELLED"

    def _handle_speed_limit_setting(self, key, current_value):
        """Handle download speed limit setting"""
        self.console.print("[dim]Enter speed limit in KB/s (0 or 'none' for unlimited)[/dim]")
        
        try:
            value = Prompt.ask("Speed limit", default=str(current_value) if current_value else "none")
            
            if value.lower() in ['none', '0', '']:
                return None
            
            speed = int(value)
            if speed > 0:
                return speed
            else:
                self.console.print("[red]Speed limit must be positive[/red]")
                return "CANCELLED"
        except (ValueError, KeyboardInterrupt):
            return "CANCELLED"

    def _handle_proxy_setting(self, key, current_value):
        """Handle proxy setting with validation"""
        new_value = Prompt.ask("Enter proxy (host:port) or 'none'", 
                             default=current_value or "none")
        
        if new_value.strip().lower() in ['none', '']:
            return None
        
        valid, message = self.validate_proxy(new_value)
        if valid:
            return new_value
        else:
            self.console.print(f"[red]{message}[/red]")
            return "CANCELLED"

    def _handle_text_setting(self, key, current_value):
        """Handle free text settings"""
        new_value = Prompt.ask(f"Enter new value", default=current_value or "")
        
        if new_value.strip().lower() in ['none', '']:
            return None
        
        return new_value

    def get_setting(self, key, default=None):
        """Get a setting value with optional default"""
        return self.settings.get(key, default)

    def update_setting_direct(self, key, value):
        """Update a setting programmatically"""
        if key in self.settings:
            self.settings[key] = value
            self.save_settings()
            return True
        return False

if __name__ == "__main__":
    console = Console()
    settings_manager = SettingsManager(console=console)
    
    settings_manager.show_settings_menu()