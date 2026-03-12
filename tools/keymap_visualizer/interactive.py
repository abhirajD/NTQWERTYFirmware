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
from rich.prompt import Prompt, Confirm
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


# ──────────────────────────────────────────
# Visual helpers
# ──────────────────────────────────────────

def bar_graph(value, lo, hi, width=20):
    """Render a proportional bar: ████░░░░░░ for a value in [lo, hi]."""
    pct = max(0, min(1, (value - lo) / (hi - lo))) if hi > lo else 0
    filled = round(pct * width)
    return f"{'█' * filled}{'░' * (width - filled)}"


def key_diagram():
    """Show a mini key diagram explaining what center/corner means."""
    return (
        "  ┌──────────────────┐\n"
        "  │ [blue]F5[/]          [yellow]![/]   │  ← corner layers\n"
        "  │                  │\n"
        "  │     [bold white]T[/]            │  ← [bold]center[/] (main key)\n"
        "  │                  │\n"
        "  │ [green]7[/]     [dim]hold:⌘[/]    │  ← corner + behavior\n"
        "  └──────────────────┘"
    )


# ──────────────────────────────────────────
# Display
# ──────────────────────────────────────────

def show_dashboard(config):
    """Compact dashboard of all current settings."""
    c = config.get("center_font_ratio", 0.18)
    k = config.get("corner_font_ratio", 0.085)
    sc = config.get("scale", 3.0)
    fs = config.get("font_scale", 1.0)
    colors = config.get("colors", {})

    console.print()
    table = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 2))
    table.add_column("", style="bold", width=22)
    table.add_column("", width=10, justify="right", style="green")
    table.add_column("", width=24, style="dim")

    table.add_row("Center text", f"{c:.0%}", bar_graph(c, 0.05, 0.30))
    table.add_row("Corner text", f"{k:.0%}", bar_graph(k, 0.03, 0.18))
    table.add_row("All text (global)", f"×{fs}", bar_graph(fs, 0.5, 3.0))
    table.add_row("Image size", f"{sc}", bar_graph(sc, 1, 10))
    table.add_row("", "", "")
    table.add_row("Key gap", f"{config.get('key_gap', 5)}px", "")
    table.add_row("Key roundness", f"{config.get('corner_radius', 10)}px", "")
    table.add_row("Padding", f"{config.get('padding', 80)}px", "")
    table.add_row("Title", config.get("title", "(none)"), "")
    table.add_row("", "", "")
    for ck, label in [("background", "Background"), ("key_fill", "Key fill"),
                       ("key_border", "Key border")]:
        cv = colors.get(ck, "#0d1117")
        table.add_row(label, Text(f"██ {cv}", style=cv), "")

    console.print(table)


def show_profiles(config):
    """Display available profiles."""
    profiles = config.get("profiles", {})
    default = config.get("default_profile", "mac")

    table = Table(
        title="Profiles", box=box.ROUNDED, show_header=True,
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


# ──────────────────────────────────────────
# Render
# ──────────────────────────────────────────

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

    if all_layers:
        target = out_dir
    else:
        target = out_file

    if Confirm.ask(f"\nOpen [cyan]{target}[/]?", default=True):
        subprocess.run(["open", target], check=False)

    return target


# ──────────────────────────────────────────
# Settings editors
# ──────────────────────────────────────────

def _prompt_float(label, current, hint, lo=None, hi=None):
    """Prompt for a float with validation. Returns the new value."""
    range_str = ""
    if lo is not None and hi is not None:
        range_str = f", range {lo}–{hi}"
    val = Prompt.ask(
        f"  {label} [dim](now: {current}{range_str})[/]",
        default=str(current),
    )
    try:
        v = float(val)
        if lo is not None and v < lo:
            v = lo
        if hi is not None and v > hi:
            v = hi
        return v
    except ValueError:
        console.print(f"  [red]Invalid number, keeping {current}[/]")
        return current


def _prompt_int(label, current, hint=""):
    val = Prompt.ask(
        f"  {label} [dim](now: {current}{', ' + hint if hint else ''})[/]",
        default=str(current),
    )
    try:
        return int(val)
    except ValueError:
        console.print(f"  [red]Invalid number, keeping {current}[/]")
        return current


def edit_text_sizes(config):
    """Edit center/corner text proportions — the main thing users want to tweak."""
    c = config.get("center_font_ratio", 0.18)
    k = config.get("corner_font_ratio", 0.085)
    fs = config.get("font_scale", 1.0)

    console.print("\n[bold]Text Sizes[/]\n")
    console.print(key_diagram())
    console.print()
    console.print(f"  Center text  [green]{c:.0%}[/] of key  {bar_graph(c, 0.05, 0.30)}")
    console.print(f"  Corner text  [green]{k:.0%}[/] of key  {bar_graph(k, 0.03, 0.18)}")
    console.print(f"  All text     [green]×{fs}[/]          {bar_graph(fs, 0.5, 3.0)}")
    console.print()
    console.print("[dim]  Ratios control text size as a % of key size.[/]")
    console.print("[dim]  Bigger center = bigger main label. Bigger corner = bigger layer overlays.[/]")
    console.print("[dim]  'All text' is a global multiplier on top of both.[/]")
    console.print()

    c = _prompt_float(
        "Center text (% of key, e.g. 15 = 15%)", c * 100,
        "smaller=10, default=18, larger=25", lo=5, hi=35
    ) / 100
    config["center_font_ratio"] = round(c, 3)

    k = _prompt_float(
        "Corner text (% of key, e.g. 10 = 10%)", k * 100,
        "smaller=6, default=8.5, larger=14", lo=3, hi=18
    ) / 100
    config["corner_font_ratio"] = round(k, 3)

    fs = _prompt_float(
        "All text multiplier", fs,
        "0.5=half, 1.0=normal, 2.0=double", lo=0.3, hi=5.0
    )
    config["font_scale"] = round(fs, 2)

    save_config(config)
    console.print("\n[green]✓ Text sizes saved[/]")
    console.print(f"  Center: [green]{config['center_font_ratio']:.0%}[/] of key")
    console.print(f"  Corner: [green]{config['corner_font_ratio']:.0%}[/] of key")
    console.print(f"  Global: [green]×{config['font_scale']}[/]")


def edit_layout(config):
    """Edit image size, spacing, padding."""
    console.print("\n[bold]Image & Layout[/] (Enter to keep current)\n")

    config["scale"] = _prompt_float(
        "Image size (1=small, 3=medium, 5=large, 10=poster)",
        config.get("scale", 3.0), "", lo=1.0, hi=15.0
    )
    config["key_gap"] = _prompt_int(
        "Gap between keys (px)", config.get("key_gap", 5), "0=touching, 5=default"
    )
    config["corner_radius"] = _prompt_int(
        "Key corner roundness (px)", config.get("corner_radius", 10), "0=square, 20=very round"
    )
    config["padding"] = _prompt_int(
        "Padding around keyboard (px)", config.get("padding", 80)
    )

    val = Prompt.ask(
        f"  Title [dim](now: {config.get('title', '')})[/]",
        default=config.get("title", ""),
    )
    config["title"] = val

    save_config(config)
    console.print("[green]✓ Layout saved[/]")


def edit_colors(config):
    """Interactive color editor."""
    colors = config.setdefault("colors", {})
    console.print("\n[bold]Colors[/] (hex like #1a2b3c, Enter to keep)\n")

    color_keys = [
        ("background", "Background"),
        ("key_fill", "Key fill"),
        ("key_border", "Key border"),
        ("encoder_fill", "Encoder fill"),
        ("encoder_border", "Encoder border"),
        ("title", "Title text"),
        ("legend_text", "Legend text"),
    ]

    for key, label in color_keys:
        current = colors.get(key, "#000000")
        val = Prompt.ask(
            f"  {label} [dim](now: [{current}]██[/] {current})[/]",
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

    pos_labels = {"center": "center", "tl": "↖ top-left", "tr": "↗ top-right",
                  "bl": "↙ bottom-left", "br": "↘ bottom-right"}

    table = Table(title=f"Layers in '{profile_name}'", box=box.SIMPLE)
    table.add_column("#", width=3)
    table.add_column("Name")
    table.add_column("Position")
    table.add_column("Color")

    for i, lc in enumerate(layers):
        table.add_row(
            str(i),
            lc["name"],
            pos_labels.get(lc["position"], lc["position"]),
            Text(f"██ {lc['color']}", style=lc["color"]),
        )
    console.print(table)

    idx = Prompt.ask("Edit layer # (or 'b' to go back)", default="b")
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

    val = Prompt.ask(
        f"  Layer Index [dim]({lc['index']})[/]", default=str(lc["index"])
    )
    lc["index"] = int(val)

    val = Prompt.ask(
        f"  Position [dim]({lc['position']})[/]",
        choices=["center", "tl", "tr", "bl", "br"],
        default=lc["position"],
    )
    lc["position"] = val

    val = Prompt.ask(f"  Color [dim]({lc['color']})[/]", default=lc["color"])
    lc["color"] = val

    save_config(config)
    console.print("[green]✓ Profile updated[/]")


# ──────────────────────────────────────────
# Quick presets
# ──────────────────────────────────────────

PRESETS = {
    "balanced": {"center_font_ratio": 0.15, "corner_font_ratio": 0.10, "font_scale": 1.0,
                 "desc": "Center and corners are similar size — balanced look"},
    "center-heavy": {"center_font_ratio": 0.22, "corner_font_ratio": 0.075, "font_scale": 1.0,
                     "desc": "Big center labels, small corners — main layer stands out"},
    "corner-heavy": {"center_font_ratio": 0.13, "corner_font_ratio": 0.11, "font_scale": 1.0,
                     "desc": "Smaller center, bigger corners — all layers easy to read"},
    "compact": {"center_font_ratio": 0.12, "corner_font_ratio": 0.08, "font_scale": 1.0,
                "desc": "Small text everywhere — fits more info per key"},
    "large": {"center_font_ratio": 0.20, "corner_font_ratio": 0.10, "font_scale": 1.3,
              "desc": "Everything bigger — good for presentations / posters"},
}


def apply_preset(config):
    """Choose from predefined text size presets."""
    console.print("\n[bold]Text Size Presets[/]\n")

    for key, p in PRESETS.items():
        c = p["center_font_ratio"]
        k = p["corner_font_ratio"]
        console.print(
            f"  [cyan]{key:15s}[/] center={c:.0%}  corner={k:.0%}  "
            f"[dim]— {p['desc']}[/]"
        )

    console.print()
    choice = Prompt.ask(
        "  Pick a preset (or 'b' to go back)",
        choices=list(PRESETS.keys()) + ["b"],
        default="b",
    )
    if choice == "b":
        return

    p = PRESETS[choice]
    config["center_font_ratio"] = p["center_font_ratio"]
    config["corner_font_ratio"] = p["corner_font_ratio"]
    config["font_scale"] = p["font_scale"]
    save_config(config)
    console.print(f"[green]✓ Applied '{choice}' preset[/]")


# ──────────────────────────────────────────
# Main menu
# ──────────────────────────────────────────

def main_menu():
    config = load_config()
    default_profile = config.get("default_profile", "mac")

    console.print(
        Panel(
            "[bold cyan]NTQWERTY Keymap Visualizer[/]\n"
            "[dim]Rolio 46-key split keyboard[/]",
            box=box.DOUBLE,
        )
    )

    # Auto-generate on first launch
    console.print(
        f"\n  Generating [bold]{default_profile}[/] layout...\n"
    )
    render_and_open(config, profile_name=default_profile)

    while True:
        profile_names = list(config.get("profiles", {}).keys())

        console.print("\n[bold]What next?[/]\n")
        console.print("  [cyan]g[/]  Generate image      [dim]— render a profile or all layers[/]")
        console.print("  [cyan]t[/]  Text sizes           [dim]— center vs corner text balance[/]")
        console.print("  [cyan]x[/]  Text presets          [dim]— quick balanced/center-heavy/etc.[/]")
        console.print("  [cyan]l[/]  Layout               [dim]— image size, spacing, padding[/]")
        console.print("  [cyan]c[/]  Colors               [dim]— background, key fills, borders[/]")
        console.print("  [cyan]p[/]  Profiles             [dim]— which layers appear where[/]")
        console.print("  [cyan]d[/]  Dashboard            [dim]— view all current settings[/]")
        console.print("  [cyan]q[/]  Quit")

        choice = Prompt.ask(
            "\nChoice", choices=["g", "t", "x", "l", "c", "p", "d", "q"], default="g"
        )

        if choice == "q":
            console.print("[dim]Bye![/]")
            break

        elif choice == "g":
            console.print("\n  [cyan]1[/]  Render a profile (layers overlaid on one image)")
            console.print("  [cyan]2[/]  Render all layers (one image per layer)")
            sub = Prompt.ask("  Choice", choices=["1", "2"], default="1")
            if sub == "1":
                name = Prompt.ask(
                    "  Which profile?",
                    choices=profile_names,
                    default=default_profile,
                )
                render_and_open(config, profile_name=name)
            else:
                render_and_open(config, all_layers=True)

        elif choice == "t":
            edit_text_sizes(config)
            config = load_config()

        elif choice == "x":
            apply_preset(config)
            config = load_config()

        elif choice == "l":
            edit_layout(config)
            config = load_config()

        elif choice == "c":
            edit_colors(config)
            config = load_config()

        elif choice == "p":
            show_profiles(config)
            name = Prompt.ask("  Which profile?", choices=profile_names)
            edit_profile_layers(config, name)
            config = load_config()

        elif choice == "d":
            show_dashboard(config)
            show_profiles(config)


if __name__ == "__main__":
    main_menu()
