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
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

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
HOMING_POSITIONS = {16, 19}  # S and H keys — index finger homing bumps

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
    # Navigation — Unicode arrows (keep: universally recognized)
    'UP': '\u2191', 'DOWN': '\u2193', 'LEFT': '\u2190', 'RIGHT': '\u2192',
    'PG_UP': '\u21DE', 'PG_DN': '\u21DF', 'HOME': '\u21F1', 'END': '\u21F2',
    # Modifiers — Apple symbols (keep: standard Mac convention)
    'LSHIFT': '\u21E7', 'RSHIFT': '\u21E7',      # ⇧
    'LCTRL': '\u2303', 'RCTRL': '\u2303',         # ⌃
    'LALT': '\u2325', 'RALT': '\u2325',           # ⌥
    'LGUI': '\u2318', 'RGUI': '\u2318',           # ⌘
    # Special keys — Unicode symbols (keep: standard keyboard symbols)
    'TAB': '\u21E5', 'ENTER': '\u21B5', 'SPACE': '\u2423', 'RET': '\u21B5',
    'BSPC': '\u232B', 'DEL': '\u2326', 'ESC': '\u238B', 'ESCAPE': '\u238B',
    'CAPS': '\uf023',                               # Nerd:  lock
    # Function keys
    'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4', 'F5': 'F5',
    'F6': 'F6', 'F7': 'F7', 'F8': 'F8', 'F9': 'F9', 'F10': 'F10',
    'F11': 'F11', 'F12': 'F12', 'F13': 'F13',
    # Media — Nerd Font speaker icons (self-descriptive, no +/- needed)
    'C_VOL_UP': '\uf028', 'C_VOL_DN': '\uf027', 'C_MUTE': '\uf026',
    'C_PREV': '\uf04a', 'C_PP': '\uf04b', 'C_NEXT': '\uf04e',
    'C_BRI_UP': '\uf185+', 'C_BRI_DN': '\uf185\u2212',
    # Misc
    'K_APP': '\u2261', 'KP_DOT': '.', 'KP_DIVIDE': '\u00F7',
    'KP_MULTIPLY': '\u00D7', 'PSCRN': '\uf030', 'GLOBE': '\uf0ac',
    # Encoder placeholder keys
    'F16': '\u25CE', 'F17': '\u25CE',
}

LAYER_ABBREVS = {
    'GRAPHITE': 'GR', 'MACOS': 'Mac', 'WINDOWS': 'Win',
    'M_SYMBOLS': 'Sym', 'W_SYMBOLS': 'Sym', 'NUMPAD': 'Num',
    'M_FKEYS': 'FK', 'W_FKEYS': 'FK', 'KB_CONFIG': '\uf013',  # Nerd:  gear
}

MOD_SYMBOLS = {
    'LA': '\u2325', 'RA': '\u2325',   # ⌥
    'LC': '\u2303', 'RC': '\u2303',   # ⌃
    'LG': '\u2318', 'RG': '\u2318',   # ⌘
    'LS': '\u21E7', 'RS': '\u21E7',   # ⇧
}

# Semantic shortcuts — replace verbose modifier chains with concise symbols
SEMANTIC_SHORTCUTS = {
    # Mac screenshot variants → Nerd:  camera
    'LG(LS(N3))': '\uf030',           # ⌘⇧3 full screenshot
    'LG(LS(N4))': '\uf030',           # ⌘⇧4 area screenshot
    'LG(LS(N5))': '\uf030',           # ⌘⇧5 screenshot options
    'LG(LS(S))': '\uf030',            # ⌘⇧S screenshot variant
    'LA(PSCRN)': '\uf030',            # Alt+PrtSc window screenshot
    # Mac navigation — ⌘Arrow = Home/End semantically
    'LG(LEFT)': '\u21E4_',            # ⌘← → ⇤_ line start
    'LG(RIGHT)': '_\u21E5',           # ⌘→ → _⇥ line end
    'LG(UP)': '\u21DE',               # ⌘↑ → ⇞ document top
    'LG(DOWN)': '\u21DF',             # ⌘↓ → ⇟ document bottom
    # Tab variants
    'LS(TAB)': '\u21E4',              # Shift+Tab → ⇤ backtab
    # Emoji picker
    'LC(LG(SPACE))': '\u263A',        # Ctrl+Cmd+Space → ☺ emoji
}


def keycode_label(code):
    """Convert a ZMK keycode like 'GRAVE' or 'LA(BSPC)' to readable text."""
    if not code:
        return '?'

    # Semantic shortcuts — concise symbols for known multi-modifier combos
    if code in SEMANTIC_SHORTCUTS:
        return SEMANTIC_SHORTCUTS[code]

    # Handle nested modifier wrapping: LA(BSPC), LG(LS(N4)), etc.
    mod_match = re.match(r'^([LR][ACGS])\((.+)\)$', code)
    if mod_match:
        # Check the full expression first (catches LG(LS(N4)) etc.)
        inner_full = mod_match.group(2)
        if f"{mod_match.group(1)}({inner_full})" in SEMANTIC_SHORTCUTS:
            return SEMANTIC_SHORTCUTS[f"{mod_match.group(1)}({inner_full})"]
        prefix = MOD_SYMBOLS.get(mod_match.group(1), '')
        inner = keycode_label(inner_full)
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
        return f"{key}\n{layer}"

    # Mod-tap: hold=modifier, tap=key
    if behavior == '&mt':
        mod = keycode_label(args[0]) if args else ''
        key = keycode_label(args[1]) if len(args) > 1 else '?'
        return f"{key}\n{mod}"

    # Momentary layer
    if behavior == '&mo':
        layer = layer_abbrev(args[0]) if args else '?'
        return layer

    # Toggle layer — pin icon conveys "stick to this layer"
    if behavior == '&tog':
        layer = layer_abbrev(args[0]) if args else '?'
        return f"\uf08d{layer}"

    # To layer — arrow conveys "go to"
    if behavior == '&to':
        layer = layer_abbrev(args[0]) if args else '?'
        return f"\u2192{layer}"

    # Custom backspace hold-tap
    if behavior == '&backspace_word':
        return '\u232B\n\u232BW'

    # Custom forward-delete hold-tap (symmetric to backspace_word)
    if behavior == '&delete_word':
        return '\u2326\n\u2326W'

    # Shift/capsword hold-tap
    if behavior == '&scw':
        return '\u21E7\nCW'

    # Soft off — Nerd:  power
    if behavior == '&soft_off':
        return '\uf011'

    # Bluetooth key-press (hold=BT select, tap=key)
    if behavior == '&btkp':
        profile = args[0] if args else '?'
        key = keycode_label(args[1]) if len(args) > 1 else '?'
        return f"{key}\n\uf293{profile}"

    # USB/Output toggle with escape
    if behavior == '&usb_tog':
        key = keycode_label(args[1]) if len(args) > 1 else 'USB'
        return f"{key}\nUSB"

    # BT clear key-press
    if behavior == '&btclr_kp':
        return '\uf293\n\u2717'

    # Backlight — Nerd:  toggle,  sun for brightness
    if behavior == '&bl':
        cmd = args[0] if args else ''
        bl_labels = {
            'BL_TOG': '\uf0eb', 'BL_INC': '\uf0eb+', 'BL_DEC': '\uf0eb\u2212',
            'BL_ON': '\uf0eb', 'BL_OFF': '\uf0eb',
        }
        if cmd == 'BL_SET':
            val = args[1] if len(args) > 1 else '?'
            return f'\uf0eb{val}'
        return bl_labels.get(cmd, f'BL {cmd}')

    # Output toggle — Nerd Font: USB / BT
    if behavior == '&out':
        return '\uf287/\uf293'

    # Mouse key press — Nerd:  mouse cursor
    if behavior == '&mkp':
        key = args[0] if args else '?'
        labels = {'LCLK': '\uf245', 'RCLK': 'R\uf245', 'MCLK': 'M\uf245'}
        return labels.get(key, key)

    # Tap-dances: Symbols/Numpad dual-function
    # td1: tap=Symbols (momentary), double-tap=pin Numpad
    if behavior in ('&td1', '&td2'):
        return 'Sym\n\uf08dNum'

    # Custom macros — Nerd Font icons for OS-specific defaults
    macro_labels = {
        '&mac_talk': '\uf130',        # Nerd:  microphone
        '&mac_cap_app': '\uf2d0',     # Nerd:  window (app switcher)
        '&df_graphite': '\uf11c\nGR', # Nerd:  keyboard + layout name
        '&df_mac': '\uf179',          # Nerd:  Apple logo
        '&df_win': '\uf17a',          # Nerd:  Windows logo
        '&kpss': 'KP',
        '&btsel': '\uf293',           # Nerd:  BT
    }
    if behavior in macro_labels:
        return macro_labels[behavior]

    # BT commands — use BT icon for consistency
    if behavior == '&bt':
        cmd = args[0] if args else ''
        if cmd == 'BT_CLR':
            return '\uf293\u2717'
        if cmd == 'BT_SEL':
            return f'\uf293{args[1]}' if len(args) > 1 else '\uf293'
        return f'BT {cmd}'

    # Fallback: show behavior name cleaned up
    name = behavior.lstrip('&')
    if args:
        return f"{name}\n{' '.join(args[:2])}"
    return name


# ─── Keymap Parser ───

# Labels for custom sensor-rotate behaviors (0-cell: no args in sensor-bindings)
SENSOR_BEHAVIOR_LABELS = {
    '&bri_adjust': '\uf0eb\u00b1',       # 💡± keyboard backlight
    '&scroll_up_down': '\uf245\u2195',    # 🖱↕ mouse scroll
    '&mac_vol': '\uf028\u00b1',           # 🔊± volume (fine)
}


def sensor_binding_label(tokens):
    """Convert a sensor binding (list of tokens) to a rotation label.

    For &inc_dec_kp, uses the CW/CCW keycodes.
    For custom behaviors (0-cell), uses SENSOR_BEHAVIOR_LABELS lookup.
    """
    if not tokens:
        return ''
    behavior = tokens[0]
    if behavior == '&inc_dec_kp' and len(tokens) >= 3:
        cw_label = keycode_label(tokens[1])
        ccw_label = keycode_label(tokens[2])
        # If CW/CCW are a natural pair, show compact form
        return f'{cw_label}\n{ccw_label}'
    return SENSOR_BEHAVIOR_LABELS.get(behavior, behavior.lstrip('&'))


def parse_sensor_bindings(raw):
    """Parse the content inside <...> of a sensor-bindings property.

    Returns a list of sensor binding groups, one per encoder.
    Each group is a list of tokens (behavior + args).

    Formats:
        <&inc_dec_kp UP DOWN &inc_dec_kp LEFT RIGHT>  → 2 groups (2-cell each)
        <&mac_vol &scroll_up_down>                      → 2 groups (0-cell each)
        <&bri_adjust &inc_dec_kp C_BRI_UP C_BRI_DN>    → 2 groups (mixed)
    """
    tokens = raw.split()
    groups = []
    current = []
    for tok in tokens:
        if tok.startswith('&') and current:
            groups.append(current)
            current = [tok]
        else:
            current.append(tok)
    if current:
        groups.append(current)
    return groups


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

        # Extract sensor-bindings (encoder rotation)
        sensor_match = re.search(
            r'sensor-bindings\s*=\s*<(.*?)>', block, re.DOTALL)
        sensor_bindings = []
        if sensor_match:
            sensor_bindings = parse_sensor_bindings(sensor_match.group(1))

        bindings = parse_bindings_block(bindings_match.group(1))
        layers.append({
            'name': node_name,
            'display_name': display_name,
            'bindings': bindings,
            'sensor_bindings': sensor_bindings,
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
        # Tap-dances: td1 activates M_SYMBOLS, td2 activates W_SYMBOLS
        elif behavior == '&td1':
            target_layer = layer_defines.get('M_SYMBOLS')
        elif behavior == '&td2':
            target_layer = layer_defines.get('W_SYMBOLS')
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

class FontChain:
    """Multi-font fallback chain with per-character font selection.

    Loads fonts in priority order and can render mixed-font labels
    (e.g., regular text + Nerd Font icons in one string).

    Font priority: NotoSansMono (text) → NotoSansSymbols (tech) →
                   NotoSansSymbols2 (media/modifiers) → Nerd Font Symbols
                   (BT, USB, dev icons) → Menlo (system fallback)
    """

    _tofu_cache = {}  # (font_path, size, char) → bool

    # Codepoint ranges that must use Nerd Font Symbols (Private Use Area)
    _NERD_RANGES = [range(0xE000, 0xF900), range(0xF0000, 0x100000)]

    def __init__(self, size):
        self.size = size
        self.fonts = []  # [(font_obj, path_str), ...]
        self._nerd_font = None  # direct ref for fast PUA lookups
        self._load_fonts(size)

    def _load_fonts(self, size):
        script_dir = Path(__file__).parent
        font_dir = script_dir / 'fonts'

        nerd_path = font_dir / 'SymbolsNerdFontMono-Regular.ttf'

        # Priority order: bundled Noto family, Nerd Fonts, then system fonts
        candidates = [
            font_dir / 'NotoSansMono.ttf',
            font_dir / 'NotoSansSymbols.ttf',
            font_dir / 'NotoSansSymbols2-Regular.ttf',
            nerd_path,
            Path('/System/Library/Fonts/Menlo.ttc'),
            Path('/System/Library/Fonts/SFNS.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'),
        ]
        for fp in candidates:
            try:
                font = ImageFont.truetype(str(fp), size)
                self.fonts.append((font, str(fp)))
                if fp == nerd_path:
                    self._nerd_font = font
            except (IOError, OSError):
                continue
        if not self.fonts:
            self.fonts.append((ImageFont.load_default(), 'default'))

    def _is_tofu(self, font, font_path, char):
        """Check if a character renders as tofu (missing glyph box)."""
        cache_key = (font_path, self.size, char)
        if cache_key in FontChain._tofu_cache:
            return FontChain._tofu_cache[cache_key]

        img1 = Image.new('L', (50, 50), 0)
        ImageDraw.Draw(img1).text((5, 5), char, fill=255, font=font)
        px1 = sum(img1.tobytes())

        img2 = Image.new('L', (50, 50), 0)
        ImageDraw.Draw(img2).text((5, 5), '\uffff', fill=255, font=font)
        px2 = sum(img2.tobytes())

        is_tofu = abs(px1 - px2) <= 50
        FontChain._tofu_cache[cache_key] = is_tofu
        return is_tofu

    def _best_font_for_char(self, char):
        """Return the best font for a single character."""
        cp = ord(char)
        # Fast path: PUA codepoints → Nerd Font
        if self._nerd_font and any(cp in r for r in self._NERD_RANGES):
            return self._nerd_font
        # Normal chain lookup
        for font, fpath in self.fonts:
            if not self._is_tofu(font, fpath, char):
                return font
        return self.fonts[0][0]

    def select(self, text):
        """Return the best single font for the given label text.

        Picks the first font that can render ALL characters without tofu.
        Falls back to font with best character coverage.
        """
        chars = [ch for ch in text if ch not in (' ', '\n')]
        if not chars:
            return self.fonts[0][0]

        best_font, best_count = self.fonts[0][0], 0
        for font, fpath in self.fonts:
            count = sum(1 for ch in chars
                        if not self._is_tofu(font, fpath, ch))
            if count == len(chars):
                return font  # Perfect match
            if count > best_count:
                best_count = count
                best_font = font
        return best_font

    def render(self, draw, pos, text, fill, anchor='mm'):
        """Draw text with per-character font fallback.

        Groups consecutive characters by their best font and draws each
        group sequentially. Handles all PIL anchor types (mm, la, ra, etc.).
        """
        visible = [ch for ch in text if ch not in (' ', '\n')]
        if not visible:
            return

        # Fast path: single font covers everything
        single = self.select(text)
        single_path = next(
            (p for f, p in self.fonts if f is single), '')
        all_ok = all(
            not self._is_tofu(single, single_path, ch) for ch in visible
        )
        if all_ok:
            draw.text(pos, text, fill=fill, font=single, anchor=anchor)
            return

        # Slow path: group by font, draw per-group
        groups = []  # [(substring, font), ...]
        cur_chars, cur_font = [], None
        for ch in text:
            if ch in (' ', '\n'):
                cur_chars.append(ch)
                continue
            best = self._best_font_for_char(ch)
            if best is not cur_font and cur_chars:
                groups.append((''.join(cur_chars), cur_font or best))
                cur_chars = []
            cur_font = best
            cur_chars.append(ch)
        if cur_chars:
            groups.append((''.join(cur_chars), cur_font or self.fonts[0][0]))

        # Calculate total width
        total_w = sum(f.getlength(s) for s, f in groups)

        # Resolve anchor to starting x
        x, y = pos
        h_anchor = anchor[0]  # l, m, r
        v_anchor = anchor[1] if len(anchor) > 1 else 'm'  # a, m, d
        if h_anchor == 'm':
            cur_x = x - total_w / 2
        elif h_anchor == 'r':
            cur_x = x - total_w
        else:
            cur_x = x

        for substring, font in groups:
            draw.text((cur_x, y), substring, fill=fill, font=font,
                      anchor=f'l{v_anchor}')
            cur_x += font.getlength(substring)

    @property
    def primary(self):
        """Return the primary (first) font for simple text."""
        return self.fonts[0][0]


def load_font(size):
    """Legacy wrapper — returns a FontChain for the given size."""
    return FontChain(size)


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
    title_chain = load_font(int(32 * font_scale))
    draw.text((img_w // 2, padding // 2 + 10), title_text,
              fill=title_color, font=title_chain.select(title_text), anchor='mm')

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

    # ─── Calculate key bounding boxes ───
    key_bboxes = []
    for i, (lx, ly) in enumerate(PHYSICAL_KEYS):
        x0 = int(lx * scale) + padding + key_gap
        y0 = int(ly * scale) + padding + title_height + key_gap
        x1 = int((lx + KEY_SIZE) * scale) + padding - key_gap
        y1 = int((ly + KEY_SIZE) * scale) + padding + title_height - key_gap
        key_bboxes.append((x0, y0, x1, y1))

    # ─── Draw glow behind layer trigger keys ───
    glow_base = max(2, int(scale * 1.2))
    for i, bbox in enumerate(key_bboxes):
        if i not in trigger_tints:
            continue
        x0, y0, x1, y1 = bbox
        glow_color = trigger_tints[i]
        for g_mult, g_alpha in [(4, 0.10), (3, 0.18), (2, 0.28), (1, 0.38)]:
            g = glow_base * g_mult
            g_rgb = dim_color(glow_color, bg_color, alpha=g_alpha)
            draw_rounded_rect(draw, (x0 - g, y0 - g, x1 + g, y1 + g),
                              corner_radius + g, fill=g_rgb)

    # ─── Draw key caps ───
    for i, bbox in enumerate(key_bboxes):
        is_encoder = i in ENCODER_POSITIONS

        if i in trigger_tints:
            fill = dim_color(trigger_tints[i], bg_color, alpha=0.15)
            border = dim_color(trigger_tints[i], bg_color, alpha=0.55)
        elif is_encoder:
            fill = enc_fill
            border = enc_border
        else:
            fill = key_fill
            border = key_border

        draw_rounded_rect(draw, bbox, corner_radius,
                          fill=fill, outline=border, width=2)

    # ─── Accent stripe at bottom of layer trigger keys ───
    for i, bbox in enumerate(key_bboxes):
        if i not in trigger_tints:
            continue
        x0, y0, x1, y1 = bbox
        stripe_h = max(3, int(scale * 0.6))
        stripe_inset = max(4, int(scale * 1.5))
        stripe_color = dim_color(trigger_tints[i], bg_color, alpha=0.65)
        draw.rounded_rectangle(
            (x0 + stripe_inset, y1 - stripe_h - stripe_inset // 2,
             x1 - stripe_inset, y1 - stripe_inset // 2),
            radius=max(1, stripe_h // 2), fill=stripe_color
        )

    # ─── Draw homing dots on index-finger keys ───
    for i, bbox in enumerate(key_bboxes):
        if i not in HOMING_POSITIONS:
            continue
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) // 2
        dot_y = y1 - int(scale * 5.5)
        dot_r = max(5, int(scale * 4.0))
        dot_color = '#ffffff'
        draw.ellipse((cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r),
                     fill=dot_color)

    # ─── Draw layer labels on keys ───
    # Two-pass for center labels: 1) blurred glow layer, 2) crisp text on top
    center_glow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    center_glow_draw = ImageDraw.Draw(center_glow_layer)

    for lc in layer_configs:
        layer_idx = lc['index']
        position = lc['position']
        color = hex_to_rgb(lc['color'])

        # Ratio-based font sizing: relative to key pixel size
        # Hierarchy: per-layer font_ratio > global center/corner ratio > hardcoded defaults
        center_ratio = config.get('center_font_ratio', 0.18)
        corner_ratio = config.get('corner_font_ratio', 0.085)
        if 'font_ratio' in lc:
            font_size = max(10, int(key_px * lc['font_ratio'] * font_scale))
        elif 'font_size' in lc:
            font_size = int(lc['font_size'] * font_scale)
        elif position == 'center':
            font_size = max(10, int(key_px * center_ratio * font_scale))
        else:
            font_size = max(10, int(key_px * corner_ratio * font_scale))

        font_chain = load_font(font_size)

        if layer_idx >= len(all_layers):
            print(f"Warning: layer index {layer_idx} out of range", file=sys.stderr)
            continue

        layer_bindings = all_layers[layer_idx]['bindings']
        sensor_bins = all_layers[layer_idx].get('sensor_bindings', [])

        # Build encoder rotation labels: pos 30 = left encoder, pos 31 = right
        encoder_labels = {}
        encoder_sensor_map = {30: 0, 31: 1}  # position → sensor index
        for enc_pos, sens_idx in encoder_sensor_map.items():
            if sens_idx < len(sensor_bins):
                encoder_labels[enc_pos] = sensor_binding_label(sensor_bins[sens_idx])

        for key_idx, bbox in enumerate(key_bboxes):
            if key_idx >= len(layer_bindings):
                continue

            # For encoder positions, prefer rotation label over click binding
            if key_idx in encoder_labels:
                label = encoder_labels[key_idx]
            else:
                label = binding_to_label(layer_bindings[key_idx])
            if not label:
                continue

            # Center position with multi-line: split primary/secondary
            if position == 'center' and '\n' in label:
                lines = label.split('\n', 1)
                primary_label = lines[0]
                secondary_label = lines[1]

                bx0, by0, bx1, by1 = bbox
                kh = by1 - by0
                cx = bx0 + (bx1 - bx0) // 2

                # Primary: shifted up, full size, full color with soft glow
                primary_y = by0 + int(kh * 0.38)
                glow_alpha = (*color[:3], 160)
                font_chain.render(center_glow_draw, (cx, primary_y), primary_label,
                                  fill=glow_alpha, anchor='mm')
                font_chain.render(draw, (cx, primary_y), primary_label,
                                  fill=color, anchor='mm')

                # Secondary: shifted down, ~55% size, in pill badge
                sec_size = max(10, int(font_size * 0.55))
                sec_chain = load_font(sec_size)
                sec_font = sec_chain.select(secondary_label)
                sec_color = dim_color(color, bg_color, alpha=0.55)
                sec_y = by0 + int(kh * 0.72)

                # Draw pill background behind secondary text
                tw = int(sec_font.getlength(secondary_label))
                pill_pad = max(4, sec_size // 3)
                pill_h = sec_size + pill_pad
                pill_w = tw + pill_pad * 2
                pill_color = dim_color(color, bg_color, alpha=0.10)
                draw.rounded_rectangle(
                    (int(cx - pill_w / 2), int(sec_y - pill_h / 2),
                     int(cx + pill_w / 2), int(sec_y + pill_h / 2)),
                    radius=min(pill_h // 2, pill_pad),
                    fill=pill_color
                )

                sec_chain.render(draw, (cx, sec_y), secondary_label,
                                 fill=sec_color, anchor='mm')
                continue

            # For multi-line labels in corner positions, take only first line
            if position != 'center' and '\n' in label:
                label = label.split('\n')[0]

            # Truncate long labels for corner positions
            if position != 'center' and len(label) > 8:
                label = label[:7] + '..'

            font = font_chain.select(label)
            x, y, anchor = text_anchor_pos(draw, label, font, position, bbox)

            # Draw onto glow layer for center labels
            if position == 'center':
                glow_alpha = (*color[:3], 160)
                font_chain.render(center_glow_draw, (x, y), label,
                                  fill=glow_alpha, anchor=anchor)

            font_chain.render(draw, (x, y), label, fill=color, anchor=anchor)

    # ─── Composite blurred glow under crisp text ───
    # Extract alpha channel as grayscale mask, blur it, then apply as white glow
    glow_mask = center_glow_layer.split()[3]
    glow_radius = max(8, int(scale * 5))
    blurred_mask = glow_mask.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    # Create white glow image with blurred alpha
    white_glow = Image.new('RGBA', img.size, (255, 255, 255, 0))
    white_glow.putalpha(blurred_mask)
    img_rgba = img.convert('RGBA')
    img = Image.alpha_composite(img_rgba, white_glow).convert('RGB')
    draw = ImageDraw.Draw(img)

    # Re-draw crisp center text on top of glow
    for lc in layer_configs:
        if lc['position'] != 'center':
            continue
        layer_idx = lc['index']
        color = hex_to_rgb(lc['color'])
        center_ratio = config.get('center_font_ratio', 0.18)
        if 'font_ratio' in lc:
            font_size = max(10, int(key_px * lc['font_ratio'] * font_scale))
        elif 'font_size' in lc:
            font_size = int(lc['font_size'] * font_scale)
        else:
            font_size = max(10, int(key_px * center_ratio * font_scale))
        font_chain = load_font(font_size)
        if layer_idx >= len(all_layers):
            continue
        layer_bindings = all_layers[layer_idx]['bindings']
        sensor_bins = all_layers[layer_idx].get('sensor_bindings', [])
        encoder_labels = {}
        for enc_pos, sens_idx in {30: 0, 31: 1}.items():
            if sens_idx < len(sensor_bins):
                encoder_labels[enc_pos] = sensor_binding_label(sensor_bins[sens_idx])
        for key_idx, bbox in enumerate(key_bboxes):
            if key_idx >= len(layer_bindings):
                continue
            if key_idx in encoder_labels:
                label = encoder_labels[key_idx]
            else:
                label = binding_to_label(layer_bindings[key_idx])
            if not label:
                continue
            if '\n' in label:
                lines = label.split('\n', 1)
                bx0, by0, bx1, by1 = bbox
                kh = by1 - by0
                cx = bx0 + (bx1 - bx0) // 2
                primary_y = by0 + int(kh * 0.38)
                font_chain.render(draw, (cx, primary_y), lines[0],
                                  fill=color, anchor='mm')
            else:
                font = font_chain.select(label)
                x, y, anchor = text_anchor_pos(draw, label, font, 'center', bbox)
                font_chain.render(draw, (x, y), label, fill=color, anchor=anchor)

    # ─── Legend ───
    POSITION_HINTS = {
        'center': '', 'tl': '\u2196', 'tr': '\u2197',
        'bl': '\u2199', 'br': '\u2198',
    }
    legend_chain = load_font(int(18 * font_scale))
    legend_y = img_h - legend_height + 24
    legend_x = padding

    for lc in layer_configs:
        color = hex_to_rgb(lc['color'])
        hint = POSITION_HINTS.get(lc['position'], '')
        name = f"{lc['name']} {hint}" if hint else lc['name']

        # Draw colored dot
        dot_r = 7
        draw.ellipse((legend_x, legend_y - dot_r, legend_x + 2 * dot_r,
                       legend_y + dot_r), fill=color)

        # Draw label
        legend_font = legend_chain.select(name)
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
        'font_ratio': 0.18,
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
