#!/usr/bin/env python3
"""
Interactive keymap visualizer CLI using Rich.

Run: uv run interactive.py
"""

import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, FloatPrompt, Confirm
from rich.table import Table
from rich.text import Text
from rich import box

import yaml

console = Console()
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
VISUALIZE_SCRIPT = SCRIPT_DIR / "visualize.py"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def color_swatch(hex_color):
    """Return a Rich Text colored square."""
    return Text("██", style=hex_color)


def show_current_config(config):
    """Display current configuration in a pretty table."""
    table = Table(
        title="Current Configuration",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Setting", style="bold")
    table.add_column("Value", style="green")
    table.add_column("Info", style="dim")

    table.add_row("Image Size", str(config.get("scale", 3.0)),
                   "1=tiny, 3=medium, 5=large, 10=poster")
    table.add_row("Font Size", str(config.get("font_scale", 1.0)),
                   "Multiplier for all text (1.0=normal)")
    table.add_row("Key Spacing", str(config.get("key_gap", 5)),
                   "Gap between keys in px")
    table.add_row("Key Roundness", str(config.get("corner_radius", 10)),
                   "Corner radius in px (0=square)")
    table.add_row("Edge Padding", str(config.get("padding", 80)),
                   "Border around keyboard in px")
    table.add_row("Title", config.get("title", ""), "")

    colors = config.get("colors", {})
    table.add_row("Background", colors.get("background", "#0d1117"), "Hex color")
    table.add_row("Key Fill", colors.get("key_fill", "#161b22"), "Hex color")
    table.add_row("Key Border", colors.get("key_border", "#30363d"), "Hex color")

    console.print(table)


def show_profiles(config):
    """Display available profiles."""
    profiles = config.get("profiles", {})
    default = config.get("default_profile", "mac")

    table = Table(
        title="Profiles",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Layers")
    table.add_column("Default", justify="center")

    for i, (name, profile) in enumerate(profiles.items(), 1):
        layers_desc = ", ".join(
            f"[{lc['color']}]{lc['name']}[/]" for lc in profile["layers"]
        )
        is_default = "✓" if name == default else ""
        table.add_row(
            str(i), name, profile.get("description", ""), layers_desc, is_default
        )

    console.print(table)
    return list(profiles.keys())


def render_and_open(config, profile_name=None, all_layers=False, output=None):
    """Run the visualizer and open the result."""
    cmd = [sys.executable, str(VISUALIZE_SCRIPT)]

    if all_layers:
        out_dir = output or str(SCRIPT_DIR / "layers")
        cmd.extend(["--all-layers", "-o", out_dir])
    else:
        profile_name = profile_name or config.get("default_profile", "mac")
        out_file = output or str(SCRIPT_DIR / f"keymap_{profile_name}.png")
        cmd.extend(["--profile", profile_name, "-o", out_file])

    console.print(f"\n[dim]Running: {' '.join(cmd)}[/]")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]Error:[/] {result.stderr}")
        return None

    console.print(result.stdout.strip())

    # Open the generated file
    if all_layers:
        target = out_dir
    else:
        target = out_file

    if Confirm.ask(f"\nOpen [cyan]{target}[/]?", default=True):
        subprocess.run(["open", target], check=False)

    return target


def edit_global_settings(config):
    """Interactive editor for global settings."""
    console.print("\n[bold]Global Settings[/] (press Enter to keep current)\n")

    val = Prompt.ask(
        f"  Image Size [dim](1=tiny, 3=medium, 5=large, 10=poster · current: {config.get('scale', 3.0)})[/]",
        default=str(config.get("scale", 3.0)),
    )
    config["scale"] = float(val)

    val = Prompt.ask(
        f"  Font Size [dim](multiplier: 0.5=smaller, 1.0=normal, 2.0=double · current: {config.get('font_scale', 1.0)})[/]",
        default=str(config.get("font_scale", 1.0)),
    )
    config["font_scale"] = float(val)

    val = Prompt.ask(
        f"  Key Spacing [dim](gap between keys in px · current: {config.get('key_gap', 5)})[/]",
        default=str(config.get("key_gap", 5)),
    )
    config["key_gap"] = int(val)

    val = Prompt.ask(
        f"  Key Roundness [dim](corner radius in px, 0=square · current: {config.get('corner_radius', 10)})[/]",
        default=str(config.get("corner_radius", 10)),
    )
    config["corner_radius"] = int(val)

    val = Prompt.ask(
        f"  Edge Padding [dim](border around keyboard in px · current: {config.get('padding', 80)})[/]",
        default=str(config.get("padding", 80)),
    )
    config["padding"] = int(val)

    val = Prompt.ask(
        f"  Title [dim](text at top of image · current: {config.get('title', '')})[/]",
        default=config.get("title", ""),
    )
    config["title"] = val

    save_config(config)
    console.print("[green]✓ Config saved[/]")


def edit_colors(config):
    """Interactive color editor."""
    colors = config.setdefault("colors", {})
    console.print("\n[bold]Colors[/] (enter hex like #1a2b3c, Enter to keep)\n")

    color_keys = [
        ("background", "Background"),
        ("key_fill", "Key Fill"),
        ("key_border", "Key Border"),
        ("encoder_fill", "Encoder Fill"),
        ("encoder_border", "Encoder Border"),
        ("title", "Title Text"),
        ("legend_text", "Legend Text"),
    ]

    for key, label in color_keys:
        current = colors.get(key, "#000000")
        val = Prompt.ask(
            f"  {label} [dim](current: [{current}]██[/] {current})[/]",
            default=current,
        )
        colors[key] = val

    config["colors"] = colors
    save_config(config)
    console.print("[green]✓ Colors saved[/]")


def edit_profile_layers(config, profile_name):
    """Edit layers within a profile."""
    profile = config["profiles"][profile_name]
    layers = profile["layers"]

    table = Table(title=f"Layers in '{profile_name}'", box=box.SIMPLE)
    table.add_column("#", width=3)
    table.add_column("Name")
    table.add_column("Index")
    table.add_column("Position")
    table.add_column("Color")
    table.add_column("Font Size")

    for i, lc in enumerate(layers):
        table.add_row(
            str(i),
            lc["name"],
            str(lc["index"]),
            lc["position"],
            Text(f"██ {lc['color']}", style=lc["color"]),
            str(lc.get("font_size", "auto")),
        )
    console.print(table)

    idx = Prompt.ask(
        "Edit layer # (or 'b' to go back)", default="b"
    )
    if idx == "b":
        return

    try:
        lc = layers[int(idx)]
    except (ValueError, IndexError):
        console.print("[red]Invalid layer number[/]")
        return

    console.print(f"\nEditing [bold]{lc['name']}[/]:")

    val = Prompt.ask(f"  Name [dim]({lc['name']})[/]", default=lc["name"])
    lc["name"] = val

    val = Prompt.ask(f"  Layer Index [dim]({lc['index']})[/]", default=str(lc["index"]))
    lc["index"] = int(val)

    val = Prompt.ask(
        f"  Position [dim]({lc['position']})[/]",
        choices=["center", "tl", "tr", "bl", "br"],
        default=lc["position"],
    )
    lc["position"] = val

    val = Prompt.ask(f"  Color [dim]({lc['color']})[/]", default=lc["color"])
    lc["color"] = val

    current_fs = lc.get("font_size", "auto")
    val = Prompt.ask(
        f"  Font Size [dim]({current_fs}, 'auto' for ratio-based)[/]",
        default=str(current_fs),
    )
    if val == "auto":
        lc.pop("font_size", None)
    else:
        lc["font_size"] = int(val)

    save_config(config)
    console.print("[green]✓ Profile updated[/]")


def main_menu():
    config = load_config()

    console.print(
        Panel(
            "[bold cyan]NTQWERTY Keymap Visualizer[/]\n"
            "[dim]Interactive configuration & rendering[/]",
            box=box.DOUBLE,
        )
    )

    while True:
        console.print()
        show_current_config(config)
        profile_names = show_profiles(config)

        console.print("\n[bold]Actions:[/]")
        console.print("  [cyan]1[/]  Render profile")
        console.print("  [cyan]2[/]  Render all layers (separate images)")
        console.print("  [cyan]3[/]  Edit global settings (scale, fonts, padding)")
        console.print("  [cyan]4[/]  Edit colors")
        console.print("  [cyan]5[/]  Edit profile layers")
        console.print("  [cyan]6[/]  Set default profile")
        console.print("  [cyan]q[/]  Quit")

        choice = Prompt.ask("\nChoice", choices=["1", "2", "3", "4", "5", "6", "q"])

        if choice == "q":
            console.print("[dim]Bye![/]")
            break

        elif choice == "1":
            name = Prompt.ask(
                "Profile",
                choices=profile_names,
                default=config.get("default_profile", profile_names[0]),
            )
            render_and_open(config, profile_name=name)

        elif choice == "2":
            render_and_open(config, all_layers=True)

        elif choice == "3":
            edit_global_settings(config)
            config = load_config()

        elif choice == "4":
            edit_colors(config)
            config = load_config()

        elif choice == "5":
            name = Prompt.ask("Which profile?", choices=profile_names)
            edit_profile_layers(config, name)
            config = load_config()

        elif choice == "6":
            name = Prompt.ask(
                "Default profile",
                choices=profile_names,
                default=config.get("default_profile", profile_names[0]),
            )
            config["default_profile"] = name
            save_config(config)
            console.print(f"[green]✓ Default set to '{name}'[/]")


if __name__ == "__main__":
    main_menu()
