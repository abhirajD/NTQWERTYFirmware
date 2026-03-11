#!/usr/bin/env python3
"""
ZMK Keymap Visualizer for Rolio 46-key Split Keyboard

Generates a single PNG showing multiple layers overlaid on one keyboard image.
Each layer occupies a different position within each key cap (center, corners).

Usage:
    python3 visualize.py [--keymap PATH] [--profile NAME] [--output PATH]
    python3 visualize.py --all-layers  # Render each layer as a separate image

Examples:
    python3 visualize.py                                    # Default: mac profile
    python3 visualize.py --profile win                      # Windows profile
    python3 visualize.py --all-layers --output layers/      # All layers to folder
"""

import re
import sys
import argparse
import yaml
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ─── Physical Layout from rolio46-layout.dtsi ───
# 48 positions: (x, y) in layout units (100 = 1 key width)
PHYSICAL_KEYS = [
    # Row 0 — Number/top row (positions 0–11)
    (0, 24), (100, 12), (200, 0), (300, 0), (400, 12), (500, 24),
    (900, 24), (1000, 12), (1100, 0), (1200, 0), (1300, 12), (1400, 24),
    # Row 1 — Home row (positions 12–23)
    (0, 124), (100, 112), (200, 100), (300, 100), (400, 112), (500, 124),
    (900, 124), (1000, 112), (1100, 100), (1200, 100), (1300, 112), (1400, 124),
    # Row 2 — Bottom alpha + encoders (positions 24–37)
    (0, 223), (100, 212), (200, 200), (300, 200), (400, 212), (500, 224),
    (624, 200), (776, 200),  # Encoders
    (900, 224), (1000, 212), (1100, 200), (1200, 200), (1300, 212), (1400, 224),
    # Row 3 — Thumb cluster + encoder positions (positions 38–47)
    (200, 300), (300, 300), (400, 312), (500, 324),
    (624, 312), (776, 312),  # Encoder thumb positions
    (900, 324), (1000, 312), (1100, 300), (1200, 300),
]

KEY_SIZE = 100  # layout units per key
ENCODER_POSITIONS = {30, 31, 42, 43}

# ─── ZMK Keycode → Human-Readable Label ───
KEYCODE_LABELS = {
    # Numbers
    'N0': '0', 'N1': '1', 'N2': '2', 'N3': '3', 'N4': '4',
    'N5': '5', 'N6': '6', 'N7': '7', 'N8': '8', 'N9': '9',
    # Punctuation & symbols
    'GRAVE': '`', 'MINUS': '-', 'EQUAL': '=',
    'LBKT': '[', 'RBKT': ']', 'BACKSLASH': '\\',
    'SEMI': ';', 'SQT': "'", 'COMMA': ',', 'DOT': '.', 'FSLH': '/',
    'UNDER': '_', 'PLUS': '+',
    'LEFT_BRACE': '{', 'RIGHT_BRACE': '}', 'PIPE': '|',
    'EXCL': '!', 'AT': '@', 'HASH': '#', 'DLLR': '$', 'PRCNT': '%',
    'CARET': '^', 'AMPERSAND': '&', 'STAR': '*', 'LPAR': '(', 'RPAR': ')',
    # Navigation — Unicode arrows
    'UP': '\u2191', 'DOWN': '\u2193', 'LEFT': '\u2190', 'RIGHT': '\u2192',
    'PG_UP': '\u21DE', 'PG_DN': '\u21DF', 'HOME': '\u2912', 'END': '\u2913',
    # Modifiers — Apple/Unicode symbols
    'LSHIFT': '\u21E7', 'RSHIFT': '\u21E7',      # ⇧
    'LCTRL': '\u2303', 'RCTRL': '\u2303',         # ⌃
    'LALT': '\u2325', 'RALT': '\u2325',           # ⌥
    'LGUI': '\u2318', 'RGUI': '\u2318',           # ⌘
    # Special keys — Unicode symbols
    'TAB': '\u21E5', 'ENTER': '\u21B5', 'SPACE': '\u2423', 'RET': '\u21B5',
    'BSPC': '\u232B', 'DEL': '\u2326', 'ESC': '\u238B', 'ESCAPE': '\u238B',
    'CAPS': '\u21EA',                               # ⇪
    # Function keys
    'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4', 'F5': 'F5',
    'F6': 'F6', 'F7': 'F7', 'F8': 'F8', 'F9': 'F9', 'F10': 'F10',
    'F11': 'F11', 'F12': 'F12', 'F13': 'F13',
    # Media — Unicode symbols (avoiding emoji for font compatibility)
    'C_VOL_UP': '\u266B+', 'C_VOL_DN': '\u266B-', 'C_MUTE': '\u266B\u00D7',
    'C_PREV': '\u23EE', 'C_PP': '\u23EF', 'C_NEXT': '\u23ED',
    'C_BRI_UP': '\u2600+', 'C_BRI_DN': '\u2600-',
    # Misc
    'K_APP': '\u2630', 'KP_DOT': '.', 'KP_DIVIDE': '\u00F7',
    'KP_MULTIPLY': '\u00D7', 'PSCRN': '\u2399', 'GLOBE': '\u2609',
    # Encoder placeholder keys — use simple text instead of Unicode
    'F16': 'Enc', 'F17': 'Enc',
}

LAYER_ABBREVS = {
    'GRAPHITE': 'GR', 'MACOS': 'Mac', 'WINDOWS': 'Win',
    'M_SYMBOLS': 'Sym', 'W_SYMBOLS': 'Sym', 'NUMPAD': 'Num',
    'M_FKEYS': 'FK', 'W_FKEYS': 'FK', 'KB_CONFIG': '\u2699',
}

MOD_SYMBOLS = {
    'LA': '\u2325', 'RA': '\u2325',   # ⌥
    'LC': '\u2303', 'RC': '\u2303',   # ⌃
    'LG': '\u2318', 'RG': '\u2318',   # ⌘
    'LS': '\u21E7', 'RS': '\u21E7',   # ⇧
}


def keycode_label(code):
    """Convert a ZMK keycode like 'GRAVE' or 'LA(BSPC)' to readable text."""
    if not code:
        return '?'

    # Handle nested modifier wrapping: LA(BSPC), LG(LS(N4)), etc.
    mod_match = re.match(r'^([LR][ACGS])\((.+)\)$', code)
    if mod_match:
        prefix = MOD_SYMBOLS.get(mod_match.group(1), '')
        inner = keycode_label(mod_match.group(2))
        return f"{prefix}{inner}"

    # Single letter keys (A-Z) are just themselves
    if len(code) == 1 and code.isalpha():
        return code

    return KEYCODE_LABELS.get(code, code)


def layer_abbrev(layer_name):
    """Short abbreviation for layer names."""
    return LAYER_ABBREVS.get(layer_name, layer_name[:3])


def binding_to_label(binding):
    """Convert a raw ZMK binding string to a human-readable label.

    Returns a string, possibly with \\n for multi-line display.
    """
    parts = binding.strip().split()
    if not parts:
        return ''

    behavior = parts[0]
    args = parts[1:]

    # Transparent
    if behavior in ('&trans', '___'):
        return ''

    # None
    if behavior == '&none':
        return '\u2715'

    # Simple key press
    if behavior == '&kp':
        return keycode_label(args[0]) if args else '?'

    # Layer-tap: hold=layer, tap=key
    if behavior == '&lt':
        layer = layer_abbrev(args[0]) if args else '?'
        key = keycode_label(args[1]) if len(args) > 1 else '?'
        return f"{key}\n({layer})"

    # Mod-tap: hold=modifier, tap=key
    if behavior == '&mt':
        mod = keycode_label(args[0]) if args else ''
        key = keycode_label(args[1]) if len(args) > 1 else '?'
        return f"{key}\n({mod})"

    # Momentary layer
    if behavior == '&mo':
        layer = layer_abbrev(args[0]) if args else '?'
        return f"({layer})"

    # Toggle layer
    if behavior == '&tog':
        layer = layer_abbrev(args[0]) if args else '?'
        return f"Tog\n{layer}"

    # To layer
    if behavior == '&to':
        layer = layer_abbrev(args[0]) if args else '?'
        return f"To\n{layer}"

    # Custom backspace hold-tap
    if behavior == '&backspace_word':
        return '\u232B\n(\u232BW)'

    # Custom forward-delete hold-tap (symmetric to backspace_word)
    if behavior == '&delete_word':
        return '\u2326\n(\u2326W)'

    # Shift/capsword hold-tap
    if behavior == '&scw':
        return '\u21E7\n(CW)'

    # Soft off (power)
    if behavior == '&soft_off':
        return '\u23FB'

    # Bluetooth key-press (hold=BT select, tap=key)
    if behavior == '&btkp':
        profile = args[0] if args else '?'
        key = keycode_label(args[1]) if len(args) > 1 else '?'
        return f"{key}\n(BT{profile})"

    # USB/Output toggle with escape
    if behavior == '&usb_tog':
        key = keycode_label(args[1]) if len(args) > 1 else 'USB'
        return f"{key}\n(USB)"

    # BT clear key-press
    if behavior == '&btclr_kp':
        return 'BT\nClear'

    # Backlight
    if behavior == '&bl':
        cmd = args[0] if args else ''
        bl_labels = {
            'BL_TOG': 'BL Tog', 'BL_INC': 'BL+', 'BL_DEC': 'BL-',
            'BL_ON': 'BL On', 'BL_OFF': 'BL Off',
        }
        if cmd == 'BL_SET':
            val = args[1] if len(args) > 1 else '?'
            return f'BL={val}'
        return bl_labels.get(cmd, f'BL {cmd}')

    # Output toggle
    if behavior == '&out':
        return 'Out Tog'

    # Mouse key press
    if behavior == '&mkp':
        key = args[0] if args else '?'
        labels = {'LCLK': 'Click', 'RCLK': 'RClick', 'MCLK': 'MClick'}
        return labels.get(key, key)

    # Tap-dances (custom, no args)
    if behavior in ('&td1', '&td2'):
        num = behavior[-1]
        return f'TD{num}'

    # Custom macros
    macro_labels = {
        '&mac_talk': 'Dictn',
        '&mac_cap_app': 'Cap\nApp',
        '&df_graphite': 'Set\nGR',
        '&df_mac': 'Set\nMac',
        '&df_win': 'Set\nWin',
        '&kpss': 'KP',
        '&btsel': 'BT Sel',
    }
    if behavior in macro_labels:
        return macro_labels[behavior]

    # BT commands
    if behavior == '&bt':
        cmd = args[0] if args else ''
        if cmd == 'BT_CLR':
            return 'BT Clr'
        if cmd == 'BT_SEL':
            return f'BT{args[1]}' if len(args) > 1 else 'BT Sel'
        return f'BT {cmd}'

    # Fallback: show behavior name cleaned up
    name = behavior.lstrip('&')
    if args:
        return f"{name}\n{' '.join(args[:2])}"
    return name


# ─── Keymap Parser ───

def find_matching_brace(text, start):
    """Find the closing brace matching the opening brace at 'start'."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_keymap(keymap_path):
    """Parse a ZMK .keymap file and return layers and layer define mappings.

    Returns: (layers, layer_defines) where:
        layers: list of dicts with keys: name, display_name, bindings
        layer_defines: dict mapping define name → layer index (e.g., {'M_FKEYS': 6})
    """
    text = Path(keymap_path).read_text()

    # Extract #define layer mappings (e.g., #define M_FKEYS 6)
    layer_defines = {}
    for m in re.finditer(r'#define\s+(\w+)\s+(\d+)', text):
        layer_defines[m.group(1)] = int(m.group(2))

    # Find the keymap block using brace counting
    km_match = re.search(r'\bkeymap\s*\{', text)
    if not km_match:
        print("Error: Could not find keymap block", file=sys.stderr)
        sys.exit(1)

    km_open = km_match.end() - 1  # position of the {
    km_close = find_matching_brace(text, km_open)
    if km_close < 0:
        print("Error: Unmatched keymap brace", file=sys.stderr)
        sys.exit(1)

    keymap_body = text[km_open + 1:km_close]

    # Find each layer block within the keymap body
    layers = []
    pos = 0
    while pos < len(keymap_body):
        # Look for a layer node: name { ... }
        layer_match = re.search(r'(\w+)\s*\{', keymap_body[pos:])
        if not layer_match:
            break

        node_name = layer_match.group(1)
        # Find the actual { position
        brace_start = pos + layer_match.end() - 1
        brace_end = find_matching_brace(keymap_body, brace_start)
        if brace_end < 0:
            break

        block = keymap_body[brace_start + 1:brace_end]
        pos = brace_end + 1

        # Skip non-layer nodes (e.g., "compatible" is not a layer)
        bindings_match = re.search(r'(?<![-\w])bindings\s*=\s*<(.*?)>', block, re.DOTALL)
        if not bindings_match:
            continue

        # Extract display name
        dn_match = re.search(r'display-name\s*=\s*"([^"]*)"', block)
        display_name = dn_match.group(1) if dn_match else node_name

        bindings = parse_bindings_block(bindings_match.group(1))
        layers.append({
            'name': node_name,
            'display_name': display_name,
            'bindings': bindings,
        })

    return layers, layer_defines


def get_layer_trigger_map(bindings, layer_defines):
    """For each key position, check if it activates a layer.

    Returns: dict mapping key_index → target_layer_index (or None)
    """
    triggers = {}
    for i, binding in enumerate(bindings):
        parts = binding.strip().split()
        if not parts:
            continue
        behavior = parts[0]
        args = parts[1:]

        target_layer = None
        if behavior in ('&lt', '&mo', '&tog', '&to', '&sl'):
            if args:
                layer_name = args[0]
                target_layer = layer_defines.get(layer_name)
        # Macros that switch layers
        elif behavior == '&df_graphite':
            target_layer = layer_defines.get('GRAPHITE')
        elif behavior == '&df_mac':
            target_layer = layer_defines.get('MACOS')
        elif behavior == '&df_win':
            target_layer = layer_defines.get('WINDOWS')

        if target_layer is not None:
            triggers[i] = target_layer

    return triggers


def parse_bindings_block(text):
    """Parse a bindings block (content between < and >) into individual binding strings."""
    # Remove block comments
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.DOTALL)
    # Remove line comments
    text = re.sub(r'//.*$', ' ', text, flags=re.MULTILINE)
    # Replace ___ macro with &trans
    text = text.replace('___', '&trans')
    # Normalize whitespace
    text = ' '.join(text.split())

    # Split on & to get individual bindings
    parts = text.split('&')
    bindings = []
    for part in parts:
        part = part.strip()
        if part:
            bindings.append('&' + part)

    return bindings


# ─── Renderer ───

def load_font(size):
    """Try to load a font with good Unicode coverage, falling back gracefully."""
    font_paths = [
        # Menlo has excellent Unicode symbol coverage (media, arrows, etc.)
        '/System/Library/Fonts/Menlo.ttc',
        '/System/Library/Fonts/SFNS.ttf',
        '/System/Library/Fonts/Supplemental/Apple Symbols.ttf',
        '/System/Library/Fonts/SFNSMono.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (IOError, OSError):
            continue
    # Fallback to default
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size)
    except (IOError, OSError):
        return ImageFont.load_default()


def hex_to_rgb(hex_color):
    """Convert '#RRGGBB' to (R, G, B) tuple."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """Draw a rounded rectangle."""
    x0, y0, x1, y1 = xy
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def text_anchor_pos(draw, text, font, position, key_bbox, padding=8):
    """Calculate text position within a key based on position name.

    Returns (x, y, anchor) for ImageDraw.text().
    """
    x0, y0, x1, y1 = key_bbox
    kw = x1 - x0
    kh = y1 - y0

    positions = {
        'center': (x0 + kw // 2, y0 + kh // 2, 'mm'),
        'tl': (x0 + padding, y0 + padding, 'la'),
        'tr': (x1 - padding, y0 + padding, 'ra'),
        'bl': (x0 + padding, y1 - padding, 'ld'),
        'br': (x1 - padding, y1 - padding, 'rd'),
    }

    x, y, anchor = positions.get(position, positions['center'])
    return x, y, anchor


def dim_color(color_rgb, bg_rgb, alpha=0.2):
    """Blend a color toward the background at the given alpha (0-1)."""
    return tuple(int(bg + alpha * (fg - bg)) for fg, bg in zip(color_rgb, bg_rgb))


def render_keyboard(all_layers, layer_configs, config, output_path,
                    layer_defines=None):
    """Render the keyboard with overlaid layers to a PNG file."""
    scale = config.get('scale', 3.0)
    padding = config.get('padding', 80)
    key_gap = config.get('key_gap', 5)
    corner_radius = config.get('corner_radius', 10)
    font_scale = config.get('font_scale', 1.0)
    colors = config.get('colors', {})

    bg_color = hex_to_rgb(colors.get('background', '#0d1117'))
    key_fill = hex_to_rgb(colors.get('key_fill', '#161b22'))
    key_border = hex_to_rgb(colors.get('key_border', '#30363d'))
    enc_fill = hex_to_rgb(colors.get('encoder_fill', '#1c2333'))
    enc_border = hex_to_rgb(colors.get('encoder_border', '#3d5a80'))
    title_color = hex_to_rgb(colors.get('title', '#e6edf3'))
    legend_color = hex_to_rgb(colors.get('legend_text', '#8b949e'))

    # Key pixel size (used for ratio-based font sizing)
    key_px = int(KEY_SIZE * scale)

    # Calculate image dimensions
    max_x = max(x for x, y in PHYSICAL_KEYS) + KEY_SIZE
    max_y = max(y for x, y in PHYSICAL_KEYS) + KEY_SIZE

    title_height = 70
    legend_height = 70
    img_w = int(max_x * scale) + 2 * padding
    img_h = int(max_y * scale) + 2 * padding + title_height + legend_height

    img = Image.new('RGB', (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    # ─── Title ───
    title_text = config.get('title', 'ZMK Keymap')
    title_font = load_font(int(32 * font_scale))
    draw.text((img_w // 2, padding // 2 + 10), title_text,
              fill=title_color, font=title_font, anchor='mm')

    # ─── Build layer trigger map for the center layer ───
    # Find keys that activate layers displayed in this profile
    layer_color_map = {}  # layer_index → color_rgb
    for lc in layer_configs:
        layer_color_map[lc['index']] = hex_to_rgb(lc['color'])

    # Get trigger map from center layer (the primary visible layer)
    trigger_tints = {}  # key_index → tint_color_rgb
    center_layers = [lc for lc in layer_configs if lc['position'] == 'center']
    if center_layers and layer_defines:
        center_idx = center_layers[0]['index']
        if center_idx < len(all_layers):
            triggers = get_layer_trigger_map(
                all_layers[center_idx]['bindings'], layer_defines)
            for key_idx, target_layer in triggers.items():
                if target_layer in layer_color_map:
                    trigger_tints[key_idx] = layer_color_map[target_layer]

    # ─── Draw key caps ───
    key_bboxes = []
    for i, (lx, ly) in enumerate(PHYSICAL_KEYS):
        x0 = int(lx * scale) + padding + key_gap
        y0 = int(ly * scale) + padding + title_height + key_gap
        x1 = int((lx + KEY_SIZE) * scale) + padding - key_gap
        y1 = int((ly + KEY_SIZE) * scale) + padding + title_height - key_gap

        is_encoder = i in ENCODER_POSITIONS

        # Determine key fill color (tinted if it's a layer trigger)
        if i in trigger_tints:
            fill = dim_color(trigger_tints[i], bg_color, alpha=0.25)
            border = dim_color(trigger_tints[i], bg_color, alpha=0.5)
        elif is_encoder:
            fill = enc_fill
            border = enc_border
        else:
            fill = key_fill
            border = key_border

        draw_rounded_rect(draw, (x0, y0, x1, y1), corner_radius,
                          fill=fill, outline=border, width=2)
        key_bboxes.append((x0, y0, x1, y1))

    # ─── Draw layer labels on keys ───
    for lc in layer_configs:
        layer_idx = lc['index']
        position = lc['position']
        color = hex_to_rgb(lc['color'])

        # Ratio-based font sizing: relative to key pixel size
        # Default ratios: center=0.18, corner=0.085
        if 'font_ratio' in lc:
            font_size = max(10, int(key_px * lc['font_ratio'] * font_scale))
        elif 'font_size' in lc:
            font_size = int(lc['font_size'] * font_scale)
        elif position == 'center':
            font_size = max(10, int(key_px * 0.18 * font_scale))
        else:
            font_size = max(10, int(key_px * 0.085 * font_scale))

        font = load_font(font_size)

        if layer_idx >= len(all_layers):
            print(f"Warning: layer index {layer_idx} out of range", file=sys.stderr)
            continue

        layer_bindings = all_layers[layer_idx]['bindings']

        for key_idx, bbox in enumerate(key_bboxes):
            if key_idx >= len(layer_bindings):
                continue

            label = binding_to_label(layer_bindings[key_idx])
            if not label:
                continue

            # For multi-line labels in corner positions, take only first line
            if position != 'center' and '\n' in label:
                label = label.split('\n')[0]

            # Truncate long labels for corner positions
            if position != 'center' and len(label) > 8:
                label = label[:7] + '..'

            x, y, anchor = text_anchor_pos(draw, label, font, position, bbox)
            draw.text((x, y), label, fill=color, font=font, anchor=anchor)

    # ─── Legend ───
    legend_font = load_font(int(18 * font_scale))
    legend_y = img_h - legend_height + 24
    legend_x = padding

    for lc in layer_configs:
        color = hex_to_rgb(lc['color'])
        name = lc['name']

        # Draw colored dot
        dot_r = 7
        draw.ellipse((legend_x, legend_y - dot_r, legend_x + 2 * dot_r,
                       legend_y + dot_r), fill=color)

        # Draw label
        draw.text((legend_x + 2 * dot_r + 8, legend_y), name,
                  fill=legend_color, font=legend_font, anchor='lm')

        # Advance x
        text_bbox = legend_font.getbbox(name)
        text_w = text_bbox[2] - text_bbox[0] if text_bbox else len(name) * 8
        legend_x += 2 * dot_r + 8 + text_w + 30

    # Save
    img.save(str(output_path), 'PNG')
    return output_path


def render_single_layer(all_layers, layer_idx, layer_name, config, output_path,
                        layer_defines=None):
    """Render a single layer as a standalone image."""
    lc = {
        'name': layer_name,
        'index': layer_idx,
        'position': 'center',
        'color': '#e6edf3',
        'font_size': 14,
    }
    single_config = dict(config)
    single_config['title'] = f"{config.get('title', 'Keymap')} — {layer_name}"
    render_keyboard(all_layers, [lc], single_config, output_path,
                    layer_defines=layer_defines)


def main():
    parser = argparse.ArgumentParser(
        description='ZMK Keymap Visualizer for Rolio 46-key keyboard')
    parser.add_argument('--keymap', default=None,
                        help='Path to .keymap file (default: auto-detect)')
    parser.add_argument('--config', default=None,
                        help='Path to config.yaml (default: ./config.yaml)')
    parser.add_argument('--profile', default=None,
                        help='Profile name from config (default: from config)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output path (file or directory for --all-layers)')
    parser.add_argument('--all-layers', action='store_true',
                        help='Render each layer as a separate image')
    parser.add_argument('--font-scale', type=float, default=None,
                        help='Multiply all font sizes by this factor')
    args = parser.parse_args()

    # Find config
    script_dir = Path(__file__).parent
    config_path = Path(args.config) if args.config else script_dir / 'config.yaml'
    if not config_path.exists():
        print(f"Error: Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # CLI overrides
    if args.font_scale:
        config['font_scale'] = args.font_scale

    # Find keymap
    if args.keymap:
        keymap_path = Path(args.keymap)
    else:
        # Auto-detect: look for rolio.keymap relative to repo root
        repo_root = script_dir.parent.parent
        keymap_path = repo_root / 'boards' / 'shields' / 'rolio' / 'rolio.keymap'

    if not keymap_path.exists():
        print(f"Error: Keymap not found: {keymap_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing keymap: {keymap_path}")
    all_layers, layer_defines = parse_keymap(keymap_path)
    print(f"Found {len(all_layers)} layers: {', '.join(l['display_name'] for l in all_layers)}")

    if args.all_layers:
        # Render each layer separately
        out_dir = Path(args.output) if args.output else script_dir / 'output'
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, layer in enumerate(all_layers):
            out_file = out_dir / f"layer_{i}_{layer['name']}.png"
            render_single_layer(all_layers, i, layer['display_name'], config,
                                out_file, layer_defines=layer_defines)
            print(f"  Rendered: {out_file}")

        print(f"\nAll {len(all_layers)} layers saved to {out_dir}/")

    else:
        # Render overlaid profile
        profile_name = args.profile or config.get('default_profile', 'mac')
        profiles = config.get('profiles', {})

        if profile_name not in profiles:
            print(f"Error: Profile '{profile_name}' not found. "
                  f"Available: {', '.join(profiles.keys())}", file=sys.stderr)
            sys.exit(1)

        profile = profiles[profile_name]
        layer_configs = profile['layers']

        out_file = Path(args.output) if args.output else \
            script_dir / f"keymap_{profile_name}.png"

        print(f"Rendering profile: {profile_name} ({profile.get('description', '')})")
        render_keyboard(all_layers, layer_configs, config, out_file,
                        layer_defines=layer_defines)
        print(f"Saved: {out_file}")


if __name__ == '__main__':
    main()
