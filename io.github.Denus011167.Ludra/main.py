#!/usr/bin/env python3
import json
import hashlib
import os
import re
import shutil
import shlex
import subprocess
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib

APP_ID = "io.github.Denus011167.Ludra"
APP_VERSION = "1.0.0-rc4"

NON_GAME_NAMES = {
    "proton", "proton experimental", "proton hotfix",
    "proton 9.0 (beta)", "proton 11.0",
    "steam linux runtime", "steam linux runtime 1.0",
    "steam linux runtime 2.0", "steam linux runtime 3.0",
    "steam linux runtime sniper", "steam linux runtime soldier",
    "steam linux runtime heavy", "steamworks common redistributables",
    "steamworks shared", "steam client", "steam controller configs",
    "steam", "steam big picture", "steam big picture mode",
    "legacy steam runtime",
}
NON_GAME_TERMS = ("proton ", "proton experimental", "proton hotfix", "steam linux runtime", "legacy steam runtime", "steamworks common redistributable", "steamworks shared")
NON_GAME_PATH_TERMS = ("compatibilitytools.d", "steamlinuxruntime", "/proton")


def app_data_dir():
    p = Path(GLib.get_user_data_dir()) / "Ludra"
    p.mkdir(parents=True, exist_ok=True)
    (p / "covers").mkdir(exist_ok=True)
    return p


def settings_path():
    return app_data_dir() / "settings.json"


def custom_games_path():
    return app_data_dir() / "games.json"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def vdf_unescape(value):
    return value.replace(r"\\", "\x00").replace(r'\"', '"').replace("\x00", "\\")


def parse_vdf(text):
    token_re = re.compile(r'"((?:\\.|[^"\\])*)"|(\{)|(\})')
    tokens = []
    for m in token_re.finditer(text):
        if m.group(1) is not None:
            tokens.append(("str", vdf_unescape(m.group(1))))
        elif m.group(2):
            tokens.append(("open", "{"))
        else:
            tokens.append(("close", "}"))

    def parse_obj(i):
        out = {}
        while i < len(tokens):
            kind, val = tokens[i]
            if kind == "close":
                return out, i + 1
            if kind != "str":
                i += 1
                continue
            key = val
            i += 1
            if i >= len(tokens):
                break
            k2, v2 = tokens[i]
            if k2 == "open":
                child, i = parse_obj(i + 1)
                out[key] = child
            elif k2 == "str":
                out[key] = v2
                i += 1
            else:
                i += 1
        return out, i
    return parse_obj(0)[0]


def steam_roots():
    home = Path.home()
    candidates = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".steam/root",
        home / ".var/app/com.valvesoftware.Steam/data/.local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/.steam/steam",
    ]
    roots = []
    for p in candidates:
        try:
            p = p.resolve()
        except Exception:
            pass
        if p.exists() and p not in roots:
            roots.append(p)
    return roots


def is_real_game(game):
    name = game["name"].strip().lower()
    install_path = game.get("install_path", "").lower()
    if name in NON_GAME_NAMES or any(x in name for x in NON_GAME_TERMS):
        return False
    if any(x in install_path for x in NON_GAME_PATH_TERMS):
        return False
    return True


def read_installed_games():
    games = {}
    for root in steam_roots():
        steamapps = root / "steamapps"
        libraries = [steamapps]
        lf = steamapps / "libraryfolders.vdf"
        if lf.exists():
            try:
                data = parse_vdf(lf.read_text(encoding="utf-8", errors="replace"))
                for val in data.get("libraryfolders", {}).values():
                    if isinstance(val, dict) and val.get("path"):
                        libraries.append(Path(val["path"]) / "steamapps")
            except Exception:
                pass
        for lib in libraries:
            if not lib.exists():
                continue
            for manifest in lib.glob("appmanifest_*.acf"):
                try:
                    data = parse_vdf(manifest.read_text(encoding="utf-8", errors="replace"))
                    app = data.get("AppState", data)
                    appid = str(app.get("appid", "")).strip()
                    name = str(app.get("name", "")).strip()
                    installdir = str(app.get("installdir", "")).strip()
                    if not appid or not name:
                        continue
                    game = {"kind": "steam", "appid": appid, "name": name,
                            "install_path": str(lib / "common" / installdir),
                            "key": "steam:" + appid}
                    games[game["key"]] = game
                except Exception:
                    continue
    return list(games.values())


def _image_info(path_or_data):
    try:
        data = Path(path_or_data).read_bytes() if isinstance(path_or_data, (str, Path)) else path_or_data
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(data)
        loader.close()
        pix = loader.get_pixbuf()
        if pix:
            return data, pix.get_width(), pix.get_height()
    except Exception:
        pass
    return None


def remote_image(url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "Ludra/0.0.42"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        return _image_info(data)
    except Exception:
        return None


def steam_cache_cover(game):
    appid = game.get("appid")
    if not appid:
        return None
    wanted = {"library_600x900_2x.jpg", "library_600x900.jpg"}
    for root in steam_roots():
        cache = root / "appcache" / "librarycache" / appid
        if cache.exists():
            direct = [cache / x for x in wanted]
            for p in direct:
                if p.is_file():
                    result = _image_info(p)
                    if result and 0.60 <= result[1] / result[2] <= 0.75:
                        return result[0]
            try:
                for p in cache.rglob("library_600x900*"):
                    if p.is_file() and p.name in wanted:
                        result = _image_info(p)
                        if result and 0.60 <= result[1] / result[2] <= 0.75:
                            return result[0]
            except Exception:
                pass
        legacy = root / "appcache" / "librarycache"
        for p in (legacy / f"{appid}_library_600x900_2x.jpg", legacy / f"{appid}_library_600x900.jpg"):
            if p.is_file():
                result = _image_info(p)
                if result and 0.60 <= result[1] / result[2] <= 0.75:
                    return result[0]
    return None


def steam_cdn_cover(appid):
    urls = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg",
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
    ]
    for url in urls:
        result = remote_image(url)
        if result and 0.60 <= result[1] / result[2] <= 0.75:
            return result[0]
    return None


def custom_cover_path(game):
    return app_data_dir() / "covers" / (re.sub(r"[^A-Za-z0-9_.-]+", "_", game["key"]) + ".jpg")


def sgdb_key(settings):
    return str(settings.get("steamgriddb_api_key", "")).strip()


def sgdb_request(path, key, params=None):
    base = "https://www.steamgriddb.com/api/v2"
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + key,
        "User-Agent": "Ludra/0.0.42",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def sgdb_search(name, settings, appid=None):
    key = sgdb_key(settings)
    if not key:
        return []
    try:
        if appid:
            grids = sgdb_request(f"/grids/steam/{appid}", key, {
                "dimensions": "600x900", "types": "static", "limit": 50, "page": 0
            }).get("data", [])
        else:
            games = sgdb_request("/search/autocomplete/" + urllib.parse.quote(name, safe=""), key).get("data", [])
            if not games:
                return []
            gid = games[0].get("id")
            grids = sgdb_request(f"/grids/game/{gid}", key, {
                "dimensions": "600x900", "types": "static", "limit": 50, "page": 0
            }).get("data", [])
        out = []
        for g in grids:
            url = g.get("url")
            if url:
                out.append({"id": str(g.get("id", "")), "url": url, "thumb": g.get("thumb", url),
                            "score": g.get("score", 0), "style": g.get("style", "")})
        return out
    except Exception:
        return []


def load_cover(game, settings):
    custom = custom_cover_path(game)
    if custom.exists():
        result = _image_info(custom)
        if result:
            return result[0]
    source = settings.get("artwork_source", "SteamGridDB")
    if source in ("SteamGridDB", "SteamGridDB → Steam"):
        if sgdb_key(settings):
            results = sgdb_search(game["name"], settings, game.get("appid"))
            if results:
                result = remote_image(results[0]["url"])
                if result:
                    try: custom.write_bytes(result[0])
                    except Exception: pass
                    return result[0]
        if source == "SteamGridDB":
            return None
    if source in ("Steam", "SteamGridDB → Steam"):
        data = steam_cache_cover(game)
        if not data and game.get("appid"):
            data = steam_cdn_cover(game["appid"])
        if data:
            return data
    return None


def launch_steam(appid):
    Gio.AppInfo.launch_default_for_uri(f"steam://rungameid/{appid}", None)


def _xdg_open_uri(uri):
    """Open a URI using xdg-open.

    This deliberately mirrors the launch form verified on Computer B:
        xdg-open steam://rungameid/...
    """
    Gio.Subprocess.new(
        ["xdg-open", uri],
        Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
    )


def launch_custom(game):
    # A manually added game may use a normal executable, a full command,
    # or a Steam URI such as steam://rungameid/16987727714603499520.
    command = str(game.get("launch_command", "")).strip()
    executable = str(game.get("executable", "")).strip()

    if command:
        parts = shlex.split(command)

        # Keep the Ludra entry clean: a bare Steam URI is internally launched
        # using the exact xdg-open route verified on Computer B.
        if len(parts) == 1 and "://" in parts[0]:
            _xdg_open_uri(parts[0])
            return

        # If a user explicitly stored "xdg-open <URI>", run that route too.
        if len(parts) == 2 and parts[0] == "xdg-open" and "://" in parts[1]:
            _xdg_open_uri(parts[1])
            return

        if executable:
            p = Path(executable)
            if not p.exists():
                raise FileNotFoundError(str(p))
            Gio.Subprocess.new([str(p), *parts], Gio.SubprocessFlags.NONE)
        else:
            Gio.Subprocess.new(parts, Gio.SubprocessFlags.NONE)
        return

    if not executable:
        raise ValueError("No executable or launch command has been configured.")
    p = Path(executable)
    if not p.exists():
        raise FileNotFoundError(str(p))
    if os.access(p, os.X_OK) and not p.suffix.lower() == ".exe":
        Gio.Subprocess.new([str(p)], Gio.SubprocessFlags.NONE)
    else:
        Gio.AppInfo.launch_default_for_uri(p.as_uri(), None)


def normalize_cover_pixbuf(pix, width, height):
    """Crop/scale any artwork into the same 2:3 frame Ludra uses."""
    if pix is None:
        return None
    src_w = pix.get_width(); src_h = pix.get_height()
    if src_w <= 0 or src_h <= 0:
        return None
    target_ratio = width / height
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        crop_w = max(1, int(round(src_h * target_ratio)))
        x = max(0, (src_w - crop_w) // 2)
        cropped = pix.new_subpixbuf(x, 0, crop_w, src_h)
    else:
        crop_h = max(1, int(round(src_w / target_ratio)))
        y = max(0, (src_h - crop_h) // 2)
        cropped = pix.new_subpixbuf(0, y, src_w, crop_h)
    return cropped.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)


def _trim_legacy_manual_matte(pix):
    """Trim only near-solid dark matte borders made by older Ludra builds."""
    if pix is None:
        return pix
    width = pix.get_width(); height = pix.get_height()
    if width < 40 or height < 40:
        return pix
    pixels = pix.get_pixels(); stride = pix.get_rowstride(); channels = pix.get_n_channels()

    def dark_pixel(x, y):
        i = y * stride + x * channels
        return pixels[i] < 28 and pixels[i + 1] < 28 and pixels[i + 2] < 28

    xstep = max(1, width // 80); ystep = max(1, height // 120)
    def dark_row(y):
        xs = range(0, width, xstep)
        vals = [dark_pixel(x, y) for x in xs]
        return vals and sum(vals) / len(vals) >= 0.94
    def dark_col(x):
        ys = range(0, height, ystep)
        vals = [dark_pixel(x, y) for y in ys]
        return vals and sum(vals) / len(vals) >= 0.94

    top = 0
    while top < height // 3 and dark_row(top): top += 1
    bottom = height - 1
    while bottom > (height * 2) // 3 and dark_row(bottom): bottom -= 1
    left = 0
    while left < width // 3 and dark_col(left): left += 1
    right = width - 1
    while right > (width * 2) // 3 and dark_col(right): right -= 1

    new_w = right - left + 1; new_h = bottom - top + 1
    removed = (top + (height - 1 - bottom) >= max(6, height // 30) or
               left + (width - 1 - right) >= max(6, width // 30))
    if removed and new_w >= 20 and new_h >= 20:
        return pix.new_subpixbuf(left, top, new_w, new_h)
    return pix


def normalize_manual_cover_pixbuf(pix, width=600, height=900):
    """Contain manual artwork over a soft artwork-derived 600x900 backdrop."""
    if pix is None:
        return None
    # 0.1.5/0.1.6 stored manual art on a dark 600x900 matte. Detect and
    # remove only those near-solid borders so existing covers gain the new
    # artwork-derived backdrop without making the user choose them again.
    pix = _trim_legacy_manual_matte(pix)
    src_w = pix.get_width(); src_h = pix.get_height()
    if src_w <= 0 or src_h <= 0:
        return None

    # Fill the complete portrait tile from the same artwork, then make that
    # fill deliberately soft.  The tiny intermediate scale gives us a strong
    # blur-like backdrop using only GdkPixbuf (no new runtime dependency).
    background_source = normalize_cover_pixbuf(pix, width, height)
    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height)
    canvas.fill(0x05080dff)
    if background_source is not None:
        tiny_w = max(12, width // 18)
        tiny_h = max(18, height // 18)
        tiny = background_source.scale_simple(tiny_w, tiny_h, GdkPixbuf.InterpType.BILINEAR)
        soft = tiny.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR) if tiny else None
        if soft is not None:
            soft.composite(
                canvas, 0, 0, width, height,
                0, 0, 1.0, 1.0,
                GdkPixbuf.InterpType.BILINEAR, 255
            )
            # Darken the backdrop so the sharp foreground remains the focus.
            shade = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height)
            shade.fill(0x05080dff)
            shade.composite(
                canvas, 0, 0, width, height,
                0, 0, 1.0, 1.0,
                GdkPixbuf.InterpType.NEAREST, 82
            )

    # Keep the complete original artwork sharp in the foreground.  Transparent
    # PNGs are composited correctly, while landscape artwork no longer needs
    # black letterbox bars.
    scale = min(width / src_w, height / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    scaled = pix.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
    x = (width - new_w) // 2
    y = (height - new_h) // 2
    scaled.composite(
        canvas, x, y, new_w, new_h,
        x, y, 1.0, 1.0,
        GdkPixbuf.InterpType.BILINEAR, 255
    )
    return canvas


class CoverDialog(Gtk.Window):
    def __init__(self, app, game):
        super().__init__(transient_for=app.window, modal=True)
        self.app = app
        self.game = game
        self.set_title("Choose Cover — " + game["name"])
        self.set_default_size(850, 650)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(16); root.set_margin_bottom(16); root.set_margin_start(16); root.set_margin_end(16)
        top = Gtk.Box(spacing=10)
        label = Gtk.Label(label="SteamGridDB covers (600×900)")
        label.set_halign(Gtk.Align.START); label.set_hexpand(True)
        top.append(label)
        choose = Gtk.Button(label="Choose Image…")
        choose.connect("clicked", lambda *_: app.choose_image(game, self))
        top.append(choose)
        root.append(top)
        self.status = Gtk.Label(label="Searching…")
        self.status.add_css_class("dim-label"); self.status.set_halign(Gtk.Align.START)
        root.append(self.status)
        scroll = Gtk.ScrolledWindow(); scroll.set_vexpand(True)
        self.flow = Gtk.FlowBox(); self.flow.set_selection_mode(Gtk.SelectionMode.NONE); self.flow.set_row_spacing(12); self.flow.set_column_spacing(12)
        scroll.set_child(self.flow); root.append(scroll)
        close = Gtk.Button(label="Close"); close.set_halign(Gtk.Align.END); close.connect("clicked", lambda *_: self.close()); root.append(close)
        self.set_child(root)
        self.present()
        threading.Thread(target=self.search, daemon=True).start()

    def search(self):
        results = sgdb_search(self.game["name"], self.app.settings, self.game.get("appid"))
        GLib.idle_add(self.populate, results)

    def populate(self, results):
        while child := self.flow.get_first_child(): self.flow.remove(child)
        if not results:
            self.status.set_text("No SteamGridDB 600×900 artwork found. You can choose an image manually.")
            return GLib.SOURCE_REMOVE
        self.status.set_text(f"{len(results)} cover(s) found")
        for item in results[:12]:
            btn = Gtk.Button(); btn.set_has_frame(False); btn.set_tooltip_text("Use this cover")
            pic = Gtk.Picture(); pic.set_size_request(120, 180); pic.set_content_fit(Gtk.ContentFit.COVER)
            btn.set_child(pic)
            btn.connect("clicked", lambda _b, it=item: self.select(it))
            self.flow.append(btn)
            threading.Thread(target=self.load_thumb, args=(pic, item), daemon=True).start()
        return GLib.SOURCE_REMOVE

    def load_thumb(self, pic, item):
        result = remote_image(item["thumb"])
        if result: GLib.idle_add(self.set_pic, pic, result[0])

    def set_pic(self, pic, data):
        try:
            info = _image_info(data)
            if info:
                loader = GdkPixbuf.PixbufLoader.new(); loader.write(data); loader.close()
                pix = loader.get_pixbuf(); pic.set_paintable(Gdk.Texture.new_for_pixbuf(pix))
        except Exception: pass
        return GLib.SOURCE_REMOVE

    def select(self, item):
        result = remote_image(item["url"])
        if result:
            try: self.app.save_normalized_custom_cover(self.game, result[0])
            except Exception: pass
            self.close(); self.app.populate()



def rounded_cover_pixbuf(pix, radius=31):
    """Apply antialiased alpha corners to a normalized 2:3 cover texture.

    Gtk.Overlay's rectangular overflow clip does not honor CSS border-radius
    on all GTK4 renderers, so the image itself must be transparent at corners.
    """
    w, h = pix.get_width(), pix.get_height()
    if not w or not h:
        return pix
    # Let GdkPixbuf's native code convert RGB to RGBA instead of running
    # a Python loop over all 540,000 pixels for every cover.
    rgba = pix if pix.get_has_alpha() else pix.add_alpha(False, 0, 0, 0)
    stride = rgba.get_rowstride()
    out = bytearray(rgba.get_pixels())
    r = min(radius, w // 2, h // 2)
    # Anti-alias one pixel around the circular corner boundary.
    for y in list(range(r)) + list(range(h-r, h)):
        cy = r - .5 if y < r else h - r - .5
        for x in list(range(r)) + list(range(w-r, w)):
            cx = r - .5 if x < r else w - r - .5
            distance = ((x-cx)**2 + (y-cy)**2)**.5
            coverage = min(1.0, max(0.0, r + .5 - distance))
            idx = y * stride + x * 4 + 3
            out[idx] = round(out[idx] * coverage)
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(out)), GdkPixbuf.Colorspace.RGB,
        True, 8, w, h, stride)


class GameCard(Gtk.Button):
    def __init__(self, app, game):
        super().__init__()
        self.app = app; self.game = game
        self.set_has_frame(False)
        # Hover/focus is a paint-only effect. Let the enlarged card paint outside
        # its allocation without asking the row layout for any extra space.
        self.set_overflow(Gtk.Overflow.VISIBLE)
        self.set_halign(Gtk.Align.START); self.set_valign(Gtk.Align.START)
        self.set_hexpand(False); self.set_vexpand(False)
        self.set_size_request(120, -1)
        self.set_tooltip_text(game["name"] + " — click to launch")
        self.add_css_class("game-button")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.add_css_class("game-card")
        card.set_halign(Gtk.Align.START); card.set_valign(Gtk.Align.START)
        card.set_hexpand(False); card.set_vexpand(False)
        card.set_overflow(Gtk.Overflow.VISIBLE)
        card.set_size_request(120, -1)

        # The AspectFrame is the actual cover tile.  Keeping it directly in
        # the card avoids an extra wrapper influencing its natural height.
        # It owns the 2:3 geometry while FlowBox owns the row placement.
        frame = Gtk.AspectFrame.new(0.5, 0.5, 2.0 / 3.0, False)
        frame.set_halign(Gtk.Align.START); frame.set_valign(Gtk.Align.START)
        frame.set_hexpand(False); frame.set_vexpand(False)
        frame.set_overflow(Gtk.Overflow.VISIBLE)
        frame.set_size_request(120, 180)
        frame.add_css_class("cover-frame")

        self.picture = Gtk.Picture()
        self.picture.set_halign(Gtk.Align.FILL); self.picture.set_valign(Gtk.Align.FILL)
        self.picture.set_hexpand(True); self.picture.set_vexpand(True)
        self.picture.set_size_request(120, 180)
        self.picture.set_can_shrink(True)
        # Every library tile is a 2:3 cover.  Manual artwork should behave
        # exactly like Steam/SteamGridDB artwork: scale up and crop to fill
        # the portrait frame instead of being letterboxed.
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.set_alternative_text(game["name"])
        # Even with no artwork, give Gtk.Picture a real portrait paintable.
        # The placeholder therefore participates in exactly the same tile
        # sizing/layout rules as every other cover.
        placeholder = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 600, 900)
        placeholder.fill(0x05080dff)
        self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(rounded_cover_pixbuf(placeholder)))
        # Overlay a very soft white veil on hover/focus. This brightens the
        # artwork itself without rebuilding or resizing the cover texture.
        cover_overlay = Gtk.Overlay()
        # Clip only the artwork stack to a modest rounded rectangle. The outer
        # AspectFrame stays overflow-visible so its existing hover shadow/lift
        # can still paint outside the tile without affecting layout.
        cover_overlay.set_overflow(Gtk.Overflow.HIDDEN)
        cover_overlay.add_css_class("cover-artwork")
        cover_overlay.set_child(self.picture)
        self.hover_glow = Gtk.Box()
        self.hover_glow.set_can_target(False)
        # Explicitly fill the overlay allocation. This matters for composed
        # manual artwork (blurred backdrop + contained original) as well as
        # ordinary Steam covers, so both receive the same hover luminosity.
        self.hover_glow.set_halign(Gtk.Align.FILL)
        self.hover_glow.set_valign(Gtk.Align.FILL)
        self.hover_glow.set_hexpand(True)
        self.hover_glow.set_vexpand(True)
        self.hover_glow.add_css_class("cover-hover-glow")
        cover_overlay.add_overlay(self.hover_glow)
        frame.set_child(cover_overlay)
        card.append(frame)

        title = Gtk.Label(label=game["name"])
        # Keep long game names from setting the minimum width of the whole
        # grid/window. The card owns the width; the title yields and ellipsizes.
        title.set_wrap(False)
        title.set_single_line_mode(True)
        title.set_ellipsize(3)  # Pango.EllipsizeMode.END
        title.set_width_chars(1)
        title.set_max_width_chars(18)
        title.set_halign(Gtk.Align.FILL); title.set_valign(Gtk.Align.START)
        title.set_hexpand(True)
        title.add_css_class("game-title")
        title.add_css_class("game-title-bg-" + self.app.resolve_title_background())
        title.set_visible(not bool(self.app.settings.get("hide_game_titles", True)))
        card.append(title)
        self.card = card
        self.shadow = frame  # kept as an alias for resize code compatibility
        self.frame = frame
        self.title = title

        # Gtk.FlowBox allocates its FlowBoxChild to the full slot width when
        # there is spare horizontal space. Keep the actual visual card inside
        # a non-expanding, start-aligned wrapper so the cover frame never
        # paints into that spare space.
        self.card_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.card_slot.set_halign(Gtk.Align.START)
        self.card_slot.set_valign(Gtk.Align.START)
        self.card_slot.set_hexpand(False)
        self.card_slot.set_vexpand(False)
        self.card_slot.set_overflow(Gtk.Overflow.VISIBLE)
        self.card_slot.set_size_request(120, -1)
        self.card_slot.append(card)
        self.set_child(self.card_slot)

        self.connect("clicked", lambda *_: app.launch_game(game))
        gesture = Gtk.GestureClick(button=3); gesture.connect("pressed", self.context_menu); self.add_controller(gesture)
        self._pointer_over = False
        self._keyboard_focus = False
        motion = Gtk.EventControllerMotion(); motion.connect("enter", self.hover_enter); motion.connect("leave", self.hover_leave); self.add_controller(motion)
        focus = Gtk.EventControllerFocus(); focus.connect("enter", self.focus_enter); focus.connect("leave", self.focus_leave); self.add_controller(focus)
        threading.Thread(target=self.load_cover, daemon=True).start()

    def _update_emphasis(self):
        active = self._pointer_over or self._keyboard_focus
        if active:
            self.add_css_class("hovered")
        else:
            self.remove_css_class("hovered")

    def hover_enter(self, *_):
        self._pointer_over = True
        self._update_emphasis()

    def hover_leave(self, *_):
        self._pointer_over = False
        self._update_emphasis()

    def focus_enter(self, *_):
        self._keyboard_focus = True
        self._update_emphasis()

    def focus_leave(self, *_):
        self._keyboard_focus = False
        self._update_emphasis()

    def load_cover(self):
        data = load_cover(self.game, self.app.settings)
        if data: GLib.idle_add(self.set_cover, data)

    def set_cover(self, data):
        try:
            loader = GdkPixbuf.PixbufLoader.new()
            loader.write(data); loader.close()
            pix = loader.get_pixbuf()
            if pix:
                # Normalize every source to the same physical 2:3 canvas.
                # Gtk.Picture then only has to scale this portrait texture to
                # the current card size; there is no natural-size mismatch
                # between Steam, SteamGridDB, and manually selected artwork.
                # A Ludra-owned custom cover is already the user's chosen
                # artwork path. Keep it contained; do not feed it back through
                # Steam's crop-to-fill normalizer a second time.
                if custom_cover_path(self.game).exists():
                    normalized = normalize_manual_cover_pixbuf(pix, 600, 900)
                else:
                    normalized = normalize_cover_pixbuf(pix, 600, 900)
                if normalized:
                    pix = normalized
                w, h = pix.get_width(), pix.get_height()
                dx, dy = int(w * 0.025), int(h * 0.025)
                if dx and dy:
                    cropped = pix.new_subpixbuf(dx, dy, w - 2*dx, h - 2*dy)
                    pix = cropped.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
                self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(rounded_cover_pixbuf(pix)))
        except Exception: pass
        return GLib.SOURCE_REMOVE

    def context_menu(self, gesture, _n, x, y):
        self.show_context_menu(x, y)

    def show_context_menu(self, x=None, y=None):
        pop = Gtk.Popover.new(); pop.set_parent(self); pop.set_has_arrow(True); pop.set_position(Gtk.PositionType.BOTTOM)
        pop.add_css_class("ludra-cover-menu")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); box.set_margin_top(6); box.set_margin_bottom(6); box.set_margin_start(6); box.set_margin_end(6)
        actions = [
            ("▶  Launch", lambda: self.app.launch_game(self.game)),
            ("🖼  Search SteamGridDB", lambda: self.app.open_cover_search(self.game)),
            ("📁  Choose Image…", lambda: self.app.choose_image(self.game)),
            ("↺  Use Steam Artwork", lambda: self.app.reset_cover(self.game)),
        ]
        final_action = None
        if self.game.get("kind") == "custom":
            actions.insert(1, ("✎  Edit game…", lambda: self.app.edit_game_dialog(self.game)))
            final_action = ("🗑  Remove from Ludra", lambda: self.app.remove_custom_game_dialog(self.game))
        elif self.game.get("kind") == "steam":
            actions.insert(1, ("✎  Edit launch command", lambda: self.app.edit_steam_launch_dialog(self.game)))
            final_action = ("🙈  Hide from library", lambda: self.app.hide_game(self.game))

        def append_action(text, cb):
            b = Gtk.Button(label=text)
            b.add_css_class("ludra-cover-menu-action")
            b.set_has_frame(False)
            b.set_halign(Gtk.Align.FILL)
            b.set_hexpand(True)
            label = b.get_child()
            if isinstance(label, Gtk.Label):
                label.set_xalign(0.0)
                label.set_halign(Gtk.Align.FILL)
                label.set_hexpand(True)
            b.connect("clicked", lambda _b, f=cb: (pop.popdown(), f()))
            box.append(b)

        for text, cb in actions:
            append_action(text, cb)
        if final_action is not None:
            box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
            append_action(*final_action)

        pop.set_child(box)
        if x is None or y is None:
            x = max(1, self.get_width() // 2); y = max(1, self.get_height() // 2)
        pop.set_pointing_to(Gdk.Rectangle(int(x), int(y), 1, 1)); pop.popup()


class Ludra(Gtk.Application):
    def resolve_title_background(self):
        return "light" if self.settings.get("title_background") == "Light" else "dark"

    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self.on_activate)
        self.settings = load_json(settings_path(), {})
        self.settings.setdefault("artwork_source", "SteamGridDB → Steam")
        # Test123: migrate retired built-in wallpapers while preserving Custom/None.
        legacy_backgrounds = {
            "Ocean": "Aurora Blue", "Purple Night": "Lavender Mist",
            "Warm Ember": "Rose Glow", "Forest": "Sage Light",
            "Amber": "Sage Light", "Burgundy": "Rose Glow",
            "Graphite": "Twilight Glass", "Teal": "Aurora Blue",
            "Rose": "Rose Glow", "Dark Plain": "Twilight Glass",
        }
        current_bg = self.settings.get("background")
        if current_bg in legacy_backgrounds:
            self.settings["background"] = legacy_backgrounds[current_bg]
            save_json(settings_path(), self.settings)
        self.settings.setdefault("background", "Ludra Dawn")
        self.settings.setdefault("background_brightness", 100)
        self.settings.setdefault("background_contrast", 100)
        self.settings.setdefault("hidden_games", [])
        self.settings.setdefault("steam_launch_overrides", {})
        # Migrate the former "hide" preference to the new close-on-launch behavior.
        self.settings.setdefault("close_on_launch", bool(self.settings.get("close_on_launch", False)))
        self.settings.setdefault("hide_game_titles", True)
        self.settings.setdefault("title_background", "Dark")
        self.settings.setdefault("grid_spacing", 16)
        self.settings.setdefault("shadow_intensity", 42)
        self.settings.setdefault("window_width", 1440)
        self.settings.setdefault("window_height", 900)
        self.settings.setdefault("window_maximized", False)
        # Keep the last normal allocation in memory. GTK/KWin can tear down a
        # window before a final close callback has useful geometry, so window
        # persistence must not depend on that one event alone.
        self._last_normal_window_size = (
            max(640, int(self.settings.get("window_width", 1440))),
            max(240, int(self.settings.get("window_height", 900))),
        )
        self._last_window_maximized = bool(self.settings.get("window_maximized", False))
        self.custom_games = load_json(custom_games_path(), [])
        self.games = []

    def on_activate(self, _app):
        # A second activation (for example from KDE launching the existing
        # application again) must reuse the one Ludra window.  Rebuilding the
        # entire UI here leaves multiple tick callbacks/windows alive and can
        # make the existing window appear stuck behind other applications.
        if getattr(self, "window", None) is not None:
            self.window.present()
            return
        self.show_library()

    def show_library(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Ludra")
        saved_width = max(640, int(self.settings.get("window_width", 1440)))
        saved_height = max(240, int(self.settings.get("window_height", 900)))
        self.window.set_default_size(saved_width, saved_height)
        # Test107: Test42's 430px hard minimum prevented vertical resizing when
        # the gallery is compact. Permit a short window without changing the
        # fixed header, responsive column layout, or horizontal constraints.
        self.window.set_size_request(-1, 240)
        self.window.connect("close-request", self._on_main_window_close_request)
        self.window.connect("destroy", self._on_main_window_destroyed)
        # Pretty Otter shell: Ludra now owns its compact header while KWin still
        # owns the actual window management (move, resize, snap, task switcher).
        # Keep the library/search/launching logic below untouched.
        root = Gtk.Overlay()

        # Test36: stop emulating the window frame.  Keep GTK client-side
        # decorations enabled and install our Ludra header as the real titlebar.
        # GTK/KWin therefore own the resize borders, corners, snapping and
        # compositor interaction again.

        self.bg_picture = Gtk.Picture.new_for_filename("/app/share/ludra/background-dawn.jpg")
        self.bg_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.bg_picture.add_css_class("background-image")
        root.set_child(self.bg_picture)
        self.apply_css()
        shade = Gtk.Box()
        shade.add_css_class("background-shade")
        root.add_overlay(shade)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(18); content.set_margin_end(18)
        content.set_margin_top(12); content.set_margin_bottom(12)
        root.add_overlay(content)

        # Test36: this is a genuine GTK client-side titlebar again.  Unlike the
        # Test33/34 undecorated experiments, GTK now creates the native resize
        # border that KWin/Wayland expects.  WindowHandle keeps the Ludra shell
        # draggable while remaining visually app-specific.
        self.window.set_decorated(True)
        # Test37: paint the selected wallpaper on the GtkWindow itself. GTK's
        # titlebar and normal child are siblings, so the window is the one CSS
        # node that genuinely spans both while retaining native CSD mechanics.
        self.window.add_css_class("ludra-main-window")

        window_handle = Gtk.WindowHandle()
        window_handle.add_css_class("ludra-window-handle")
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_row.set_hexpand(True)
        header_row.add_css_class("ludra-floating-header")

        # Test97: fixed-size left toolbar cluster; only Search receives spare width.
        fixed_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        fixed_header.set_hexpand(False)
        fixed_header.set_halign(Gtk.Align.START)
        header_row.append(fixed_header)

        # Test101: readable premium logo from the approved source artwork.
        # Keep this in the non-expanding fixed header cluster so separators
        # remain anchored on resize; Search retains its Test99 layout.
        identity = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        identity.add_css_class("ludra-identity")
        identity.set_margin_start(10)
        identity.set_halign(Gtk.Align.START)
        identity.set_hexpand(False)
        # Test105: Keep the logo below the standard titlebar control height.
        # The PNG is exactly 180x38 and the widget's request matches it;
        # all other header spacing and separator layout remain unchanged.
        brand_logo = Gtk.Picture.new_for_filename("/app/share/ludra/ludra-final-logo-header.png")
        brand_logo.set_content_fit(Gtk.ContentFit.CONTAIN)
        brand_logo.set_size_request(180, 38)
        brand_logo.set_halign(Gtk.Align.START)
        brand_logo.set_valign(Gtk.Align.CENTER)
        brand_logo.set_hexpand(False)
        brand_logo.set_can_shrink(True)
        identity.append(brand_logo)
        fixed_header.append(identity)
        sep_brand = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_brand.add_css_class("ludra-header-separator")
        sep_brand.set_hexpand(False)
        fixed_header.append(sep_brand)

        self.status = Gtk.Label(label="Scanning Steam library…")
        self.status.add_css_class("status-pill")
        fixed_header.append(self.status)

        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.add_css_class("ludra-refresh-button")
        self.refresh_button.set_tooltip_text("Refresh library")
        self.refresh_button.connect("clicked", lambda *_: self.refresh())
        fixed_header.append(self.refresh_button)
        sep_refresh = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_refresh.add_css_class("ludra-header-separator")
        sep_refresh.set_hexpand(False)
        fixed_header.append(sep_refresh)

        self.pref_button = Gtk.Button(label="⚙  Preferences")
        self.pref_button.add_css_class("ludra-toolbar-control")
        self.pref_button.add_css_class("ludra-main-pref-compact")
        self.pref_button.connect("clicked", lambda *_: self.preferences_window())
        fixed_header.append(self.pref_button)
        # Test97: Preferences and Search are distinct header groups.
        sep_search = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_search.add_css_class("ludra-header-separator")
        sep_search.set_hexpand(False)
        fixed_header.append(sep_search)

        self.search = Gtk.SearchEntry()
        self.search.add_css_class("ludra-search")
        self.search.set_placeholder_text("Search games…")
        # Test99: only this slot absorbs surplus horizontal space. The entry
        # remains at its preferred, compact width instead of stretching on 5K.
        search_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_slot.set_hexpand(True)
        search_slot.set_halign(Gtk.Align.FILL)
        self.search.set_hexpand(False)
        self.search.set_halign(Gtk.Align.START)
        self.search.set_width_chars(0)
        self.search.set_size_request(180, -1)
        # GTK uses max-width-chars for the *natural* entry width, not a
        # minimum; it may still shrink to its 180px minimum as required.
        if hasattr(self.search, "set_max_width_chars"):
            self.search.set_max_width_chars(38)
        self.search.set_search_delay(120)
        self.search.connect("search-changed", lambda *_: self.populate())
        search_slot.append(self.search)
        header_row.append(search_slot)

        # Real client-side window controls. They sit over Ludra's own background
        # rather than inside an opaque system titlebar.
        win_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        win_controls.add_css_class("ludra-window-controls")
        minimize = Gtk.Button.new_from_icon_name("window-minimize-symbolic")
        maximize = Gtk.Button.new_from_icon_name("window-maximize-symbolic")
        close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        for button in (minimize, maximize, close):
            button.add_css_class("ludra-window-button")
            # Test125: allocate a compact square, like Preferences' titlebar.
            button.set_size_request(30, 30)
            button.set_halign(Gtk.Align.CENTER)
            button.set_valign(Gtk.Align.CENTER)
        minimize.set_tooltip_text("Minimize")
        maximize.set_tooltip_text("Maximize / Restore")
        close.set_tooltip_text("Close")
        minimize.connect("clicked", lambda *_: self.window.minimize())
        def toggle_maximize(*_args):
            if self.window.is_maximized(): self.window.unmaximize()
            else: self.window.maximize()
        maximize.connect("clicked", toggle_maximize)
        close.connect("clicked", lambda *_: self.window.close())
        win_controls.append(minimize); win_controls.append(maximize); win_controls.append(close)
        header_row.append(win_controls)

        window_handle.set_child(header_row)
        self.window.set_titlebar(window_handle)
        self.scroll = Gtk.ScrolledWindow(); self.scroll.set_vexpand(True); self.scroll.set_hexpand(True); self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # Let GTK own the responsive layout. Gtk.FlowBox is specifically
        # designed to reflow children as its available width changes.
        # Use a compact Gtk.Grid for the gallery. FlowBox's automatic child
        # allocation can keep a wide content request after a resize; Grid lets
        # us explicitly choose columns while keeping the existing cards alive.
        # Fixed-size cards in a FlowBox: the cards keep a comfortable size,
        # while GTK wraps them naturally as the viewport becomes narrower.
        # Crucially, the gallery itself has no fixed width request, so it
        # cannot hold the window/search bar wider than the current viewport.
        # V36: responsive rows, deliberately avoiding Gtk.Grid/FlowBox
        # minimum-width negotiation. `flow` is now only a vertical host.
        self.flow = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.flow.set_halign(Gtk.Align.FILL)
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_hexpand(True)
        self.flow.set_vexpand(False)
        # Test119: keep the softly rounded drop shadows inside the viewport.
        # These are outer gallery gutters, not inter-cover spacing.
        self.flow.set_margin_start(18)
        self.flow.set_margin_end(18)
        self.flow.set_margin_top(12)
        self.flow.set_margin_bottom(22)
        self._flow_layout_timer = 0
        self._flow_columns = 0
        self._gallery_rows = []
        self._last_viewport_width = -1

        # Gtk.Widget allocation changes do not reliably emit notify::width.
        # Poll the actual allocation once per GTK frame and only reflow when
        # the visible viewport width has really changed.
        self.window.add_tick_callback(self._on_layout_tick)
        # Geometry tracking is deliberately separate from the sacred gallery
        # resize callback: it observes the top-level window only and never
        # changes card/layout allocation.
        self.window.add_tick_callback(self._on_window_geometry_tick)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.window.add_controller(key_controller)
        self.scroll.set_propagate_natural_width(False)
        self.scroll.set_min_content_width(1)
        # Test107: gallery can scroll instead of imposing its row height on the window.
        self.scroll.set_propagate_natural_height(False)
        self.scroll.set_min_content_height(1)
        self.scroll.set_child(self.flow)
        content.append(self.scroll)
        self._visible_cards = []
        self.window.set_child(root); self.window.present()
        if self._last_window_maximized:
            self.window.maximize()
        self.refresh()


    def _on_window_geometry_tick(self, window, _frame_clock):
        # Poll the actual top-level allocation. This is robust on KDE/Wayland
        # where notify::width/height is not a dependable resize signal. Keep
        # only normal-window dimensions; a maximized allocation must never
        # overwrite the user's preferred normal size.
        maximized = bool(window.is_maximized())
        self._last_window_maximized = maximized
        if not maximized:
            width = int(window.get_width())
            height = int(window.get_height())
            if width >= 640 and height >= 240:
                self._last_normal_window_size = (width, height)
        return True

    def _save_window_geometry(self):
        width, height = self._last_normal_window_size
        self.settings["window_width"] = int(width)
        self.settings["window_height"] = int(height)
        self.settings["window_maximized"] = bool(self._last_window_maximized)
        save_json(settings_path(), self.settings)

    def _on_main_window_close_request(self, window):
        # The frame tick has already captured the latest normal allocation.
        # Save that snapshot instead of relying on teardown-time dimensions.
        self._last_window_maximized = bool(window.is_maximized())
        self._save_window_geometry()
        return False

    def _on_main_window_destroyed(self, _window):
        # Also persist on destroy so session/window-manager shutdown paths do
        # not depend solely on close-request.
        self._save_window_geometry()
        self.window = None




    def preferences_window(self):
        """Test42: unified Preferences shell with sidebar navigation.

        Existing setting logic is reused; this test proves the new navigation
        model before Appearance controls are added.
        """
        existing = getattr(self, "_preferences_window", None)
        if existing is not None:
            existing.present(); return

        d = Gtk.Window(transient_for=self.window, modal=False)
        d.set_title("Preferences")
        d.set_default_size(860, 610)
        d.set_size_request(760, 520)
        # Test43: keep one Preferences window alive and hide it on close.
        # Re-presenting a closed Gtk.Window left us with a stale native surface
        # on the second open under KDE/Wayland.
        d.set_hide_on_close(True)
        d.add_css_class("ludra-preferences-window")
        self._preferences_window = d

        # Test113: retain GTK client-side window mechanics on Wayland but
        # render a Ludra-styled header in place of the dark default titlebar.
        d.set_decorated(True)
        pref_header = Gtk.HeaderBar()
        pref_header.add_css_class("ludra-preferences-titlebar")
        pref_header.set_show_title_buttons(True)
        # Test117: a modest gear next to the title; GTK keeps native
        # centered-title/headerbar mechanics on KDE Plasma Wayland.
        pref_title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        pref_title_row.set_halign(Gtk.Align.CENTER)
        pref_title_row.set_valign(Gtk.Align.CENTER)
        pref_gear = Gtk.Label(label="⚙")
        pref_gear.add_css_class("ludra-preferences-title-gear")
        pref_title_row.append(pref_gear)
        pref_title = Gtk.Label(label="Preferences")
        pref_title.add_css_class("ludra-preferences-title")
        pref_title_row.append(pref_title)
        pref_header.set_title_widget(pref_title_row)
        d.set_titlebar(pref_header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.add_css_class("ludra-preferences-content")

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0); body.set_vexpand(True)
        body.add_css_class("preferences-body")
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sidebar.set_size_request(205, -1); sidebar.set_margin_top(14); sidebar.set_margin_bottom(14); sidebar.set_margin_start(14); sidebar.set_margin_end(14)
        sidebar.add_css_class("preferences-sidebar")
        stack = Gtk.Stack(); stack.set_hexpand(True); stack.set_vexpand(True)
        stack.set_margin_top(14); stack.set_margin_bottom(14); stack.set_margin_start(8); stack.set_margin_end(14)
        stack.add_css_class("preferences-stack")
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.set_transition_duration(120)

        def page(title_text, subtitle=None):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(24); box.set_margin_bottom(24); box.set_margin_start(26); box.set_margin_end(26)
            h = Gtk.Label(label=title_text, xalign=0); h.add_css_class("title-2"); box.append(h)
            if subtitle:
                sub = Gtk.Label(label=subtitle, xalign=0); sub.set_wrap(True); sub.add_css_class("dim-label"); box.append(sub)
            return box

        # General -- existing close-on-launch setting, now directly in Preferences.
        general = page("General", "Basic Ludra behaviour.")
        close_launch = Gtk.CheckButton(label="Close Ludra when a game starts")
        close_launch.set_active(bool(self.settings.get("close_on_launch", False)))
        def set_close_launch(btn):
            self.settings["close_on_launch"] = btn.get_active(); save_json(settings_path(), self.settings)
        close_launch.connect("toggled", set_close_launch); general.append(close_launch)

        gallery_heading = Gtk.Label(label="Gallery", xalign=0); gallery_heading.set_margin_top(14); general.append(gallery_heading)
        hide_titles = Gtk.CheckButton(label="Hide game titles")
        hide_titles.set_active(bool(self.settings.get("hide_game_titles", True)))
        def set_hide_titles(btn):
            hidden = bool(btn.get_active())
            self.settings["hide_game_titles"] = hidden
            save_json(settings_path(), self.settings)
            for card in getattr(self, "_visible_cards", []):
                card.title.set_visible(not hidden)
            if hasattr(self, "flow"):
                self.flow.queue_resize()
        hide_titles.connect("toggled", set_hide_titles); general.append(hide_titles)

        # Test144: compact, accessible inline selectors; no ambiguous Auto mode.
        title_bg_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        title_bg_row.set_margin_top(10)
        title_bg_label = Gtk.Label(label="Title background", xalign=0)
        title_bg_label.set_size_request(155, -1)
        title_bg_row.append(title_bg_label)
        current_mode = self.settings.get("title_background", "Dark")
        if current_mode not in ("Dark", "Light"):
            current_mode = "Dark"  # Migrate old Auto/Off selections to Dark.
            self.settings["title_background"] = current_mode
            save_json(settings_path(), self.settings)
        first_title_bg = None
        title_bg_buttons = []
        for label_text in ("Dark", "Light"):
            rb = Gtk.CheckButton(label=label_text)
            if first_title_bg is None:
                first_title_bg = rb
            else:
                rb.set_group(first_title_bg)
            rb.set_active(current_mode == label_text)
            rb.set_sensitive(not hide_titles.get_active())
            def choose_title_bg(button, choice=label_text):
                if not button.get_active():
                    return
                self.settings["title_background"] = choice
                save_json(settings_path(), self.settings)
                for card in getattr(self, "_visible_cards", []):
                    for cls in ("game-title-bg-off", "game-title-bg-light", "game-title-bg-dark"):
                        card.title.remove_css_class(cls)
                    card.title.add_css_class("game-title-bg-" + self.resolve_title_background())
            rb.connect("toggled", choose_title_bg)
            title_bg_row.append(rb)
            title_bg_buttons.append(rb)
        hide_titles.connect("toggled", lambda btn: [rb.set_sensitive(not btn.get_active()) for rb in title_bg_buttons])
        general.append(title_bg_row)

        # Test65: cover size is no longer a user preference. Keep a simple
        # responsive baseline and let window size determine how much room the
        # gallery has. Grid spacing remains an explicit visual preference.
        # Test72: compact caption/value row, immediately above its slider.
        grid_spacing_caption_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        grid_spacing_caption_row.set_margin_top(24)
        grid_spacing_label = Gtk.Label(label="Grid spacing", xalign=0)
        grid_spacing_caption_row.append(grid_spacing_label)
        grid_spacing_caption_row.append(Gtk.Box(hexpand=True))
        grid_spacing_value_label = Gtk.Label(label=str(self.settings.get("grid_spacing", 16)))
        grid_spacing_value_label.add_css_class("dim-label")
        grid_spacing_caption_row.append(grid_spacing_value_label)
        # Same 75%-width grid as the track; the number aligns with its end.
        grid_spacing_caption_grid = Gtk.Grid()
        grid_spacing_caption_grid.set_column_homogeneous(True)
        grid_spacing_caption_grid.set_hexpand(True)
        grid_spacing_caption_grid.attach(grid_spacing_caption_row, 0, 0, 3, 1)
        grid_spacing_caption_grid.attach(Gtk.Box(), 3, 0, 1, 1)
        general.append(grid_spacing_caption_grid)
        grid_spacing_test = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 8.0, 32.0, 2.0)
        grid_spacing_test.set_value(float(self.settings.get("grid_spacing", 16)))
        grid_spacing_test.set_hexpand(True)
        grid_spacing_test.set_draw_value(False)
        def preview_grid_spacing(scale):
            spacing = int(round(scale.get_value()))
            grid_spacing_value_label.set_text(str(spacing))
            self.settings["grid_spacing"] = spacing
            save_json(settings_path(), self.settings)
            # Recalculate the exact column width and row positions together.
            if hasattr(self, "flow"):
                self._apply_flow_layout()
        grid_spacing_test.connect("value-changed", preview_grid_spacing)
        # Test67: four equal grid columns give this slider 75% of the
        # available content width, without touching gallery layout.
        grid_spacing_row = Gtk.Grid()
        grid_spacing_row.set_column_homogeneous(True)
        grid_spacing_row.set_hexpand(True)
        grid_spacing_row.attach(grid_spacing_test, 0, 0, 3, 1)
        grid_spacing_row.attach(Gtk.Box(), 3, 0, 1, 1)
        general.append(grid_spacing_row)

        # Shadow intensity is deliberately paint-only: no cover geometry,
        # reflow, row rebuilding, or reparenting. 0 means no shadow.
        # Test72: compact caption/value row, immediately above its slider.
        shadow_caption_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        shadow_caption_row.set_margin_top(24)
        shadow_label = Gtk.Label(label="Shadow intensity", xalign=0)
        shadow_caption_row.append(shadow_label)
        shadow_caption_row.append(Gtk.Box(hexpand=True))
        shadow_value_label = Gtk.Label(label=str(self.settings.get("shadow_intensity", 42)))
        shadow_value_label.add_css_class("dim-label")
        shadow_caption_row.append(shadow_value_label)
        # Same 75%-width grid as the track; the number aligns with its end.
        shadow_caption_grid = Gtk.Grid()
        shadow_caption_grid.set_column_homogeneous(True)
        shadow_caption_grid.set_hexpand(True)
        shadow_caption_grid.attach(shadow_caption_row, 0, 0, 3, 1)
        shadow_caption_grid.attach(Gtk.Box(), 3, 0, 1, 1)
        general.append(shadow_caption_grid)
        shadow_test = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 100.0, 5.0)
        shadow_test.set_value(float(self.settings.get("shadow_intensity", 42)))
        shadow_test.set_hexpand(True)
        shadow_test.set_draw_value(False)
        def preview_shadow_intensity(scale):
            shadow_value_label.set_text(str(int(round(scale.get_value()))))
            self.settings["shadow_intensity"] = int(round(scale.get_value()))
            save_json(settings_path(), self.settings)
            self._apply_shadow_setting_css()
        shadow_test.connect("value-changed", preview_shadow_intensity)
        preview_shadow_intensity(shadow_test)
        shadow_row = Gtk.Grid()
        shadow_row.set_column_homogeneous(True)
        shadow_row.set_hexpand(True)
        shadow_row.attach(shadow_test, 0, 0, 3, 1)
        shadow_row.attach(Gtk.Box(), 3, 0, 1, 1)
        general.append(shadow_row)

        # Test66: sorting changes only the order of the existing game list.
        # It deliberately does not alter gallery geometry or card sizing.
        sort_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        sort_row.set_margin_top(12)
        sort_label = Gtk.Label(label="Sort by", xalign=0)
        sort_label.set_size_request(155, -1)
        sort_row.append(sort_label)
        first_sort = None
        selected_sort = self.settings.get("sort_by", "last_played")
        for label_text, value in (("Last played", "last_played"), ("Name A–Z", "name")):
            rb = Gtk.CheckButton(label=label_text)
            if first_sort is None:
                first_sort = rb
            else:
                rb.set_group(first_sort)
            rb.set_active(selected_sort == value)
            def choose_sort(button, choice=value):
                if not button.get_active():
                    return
                self.settings["sort_by"] = choice
                save_json(settings_path(), self.settings)
                self.sort_games()
                self.populate()
            rb.connect("toggled", choose_sort)
            sort_row.append(rb)
        general.append(sort_row)
        stack.add_named(general, "general")

        # Test48: Library tools now live together on one Preferences page instead
        # of opening two loose sub-windows.  Keep the Test47 window lifecycle
        # and native-titlebar isolation untouched.
        library = page("Library", "Add non-Steam games and manage hidden items in one place.")

        add_heading = Gtk.Label(label="Add non-Steam game", xalign=0); library.append(add_heading)
        lib_name = Gtk.Entry(); lib_name.set_placeholder_text("Game name"); lib_name.add_css_class("preferences-entry"); library.append(lib_name)
        lib_path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lib_path = Gtk.Entry(); lib_path.set_hexpand(True); lib_path.set_placeholder_text("Executable (optional)"); lib_path.add_css_class("preferences-entry"); lib_path_row.append(lib_path)
        lib_browse = Gtk.Button(label="Browse…"); lib_browse.add_css_class("ludra-toolbar-control"); lib_browse.connect("clicked", lambda *_: self.pick_executable(lib_path)); lib_path_row.append(lib_browse); library.append(lib_path_row)
        lib_command = Gtk.Entry(); lib_command.set_hexpand(True); lib_command.set_placeholder_text("Launch command / Steam URI (optional)"); lib_command.add_css_class("preferences-entry"); library.append(lib_command)
        lib_hint = Gtk.Label(label="Use either an executable or a launch command such as a Steam URI.", xalign=0); lib_hint.set_wrap(True); lib_hint.add_css_class("dim-label"); library.append(lib_hint)
        lib_add = Gtk.Button(label="Add game"); lib_add.set_halign(Gtk.Align.START); lib_add.add_css_class("ludra-toolbar-control"); library.append(lib_add)
        # Keep the inline Library Add button disabled until the same required
        # fields used by add_inline_game are present.
        def update_inline_add_sensitivity(*_args):
            executable = lib_path.get_text().strip()
            command = lib_command.get_text().strip()
            name = lib_name.get_text().strip() or (Path(executable).stem if executable else "")
            lib_add.set_sensitive(bool(name and (executable or command)))
        for field in (lib_name, lib_path, lib_command):
            field.connect("changed", update_inline_add_sensitivity)
        update_inline_add_sensitivity()


        library.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        hidden_heading = Gtk.Label(label="Hidden games and tools", xalign=0); library.append(hidden_heading)
        # Test51: keep the Library page itself calm while allowing a long Steam
        # tools/hidden-games list to grow independently inside a bounded scroller.
        hidden_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        hidden_scroll = Gtk.ScrolledWindow()
        hidden_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        hidden_scroll.set_min_content_height(150)
        hidden_scroll.set_max_content_height(280)
        hidden_scroll.set_propagate_natural_height(True)
        hidden_scroll.set_child(hidden_box)
        library.append(hidden_scroll)

        def refresh_inline_hidden():
            child = hidden_box.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling(); hidden_box.remove(child); child = nxt
            hidden_keys = set(self.settings.get("hidden_games", []))
            forced_visible = set(self.settings.get("forced_visible", []))
            items = [g for g in self.games if g.get("key") in hidden_keys or (not is_real_game(g) and g.get("key") not in forced_visible)]
            if not items:
                empty = Gtk.Label(label="No hidden games or tools.", xalign=0); empty.add_css_class("dim-label"); hidden_box.append(empty); return
            for game in sorted(items, key=lambda g: g.get("name", "").lower()):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10); row.set_margin_end(10)
                name = Gtk.Label(label=game.get("name", "Unknown"), xalign=0); name.set_hexpand(True); row.append(name)
                show = Gtk.Button(label="Show"); show.add_css_class("ludra-toolbar-control"); show.set_margin_end(8)
                show.connect("clicked", lambda _b, k=game.get("key"): (self.restore_game(k), refresh_inline_hidden()))
                row.append(show); hidden_box.append(row)

        def add_inline_game(_button):
            path_text = lib_path.get_text().strip(); command_text = lib_command.get_text().strip()
            name_text = lib_name.get_text().strip() or (Path(path_text).stem if path_text else "")
            if not name_text or (not path_text and not command_text): return
            item = {"kind": "custom", "key": "custom:" + GLib.uuid_string_random(), "name": name_text, "executable": path_text, "launch_command": command_text, "last_played": 0}
            self.custom_games.append(item); save_json(custom_games_path(), self.custom_games)
            lib_name.set_text(""); lib_path.set_text(""); lib_command.set_text(""); self.refresh()
        lib_add.connect("clicked", add_inline_game)
        refresh_inline_hidden()

        library_scroll = Gtk.ScrolledWindow(); library_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); library_scroll.set_child(library)
        stack.add_named(library_scroll, "library")

        covers = page("Cover images", "Choose where Ludra gets cover artwork and manage your SteamGridDB key.")
        active = self.settings.get("artwork_source", "SteamGridDB → Steam")
        first = None
        for label_text, value in (("SteamGridDB → Steam", "SteamGridDB → Steam"), ("Steam only", "Steam"), ("SteamGridDB only", "SteamGridDB")):
            rb = Gtk.CheckButton(label=label_text)
            if first is None: first = rb
            else: rb.set_group(first)
            rb.set_active(active == value)
            rb.connect("toggled", lambda b, v=value: self.set_setting("artwork_source", v) if b.get_active() else None)
            covers.append(rb)
        api_label = Gtk.Label(label="SteamGridDB API key", xalign=0); api_label.set_margin_top(10); covers.append(api_label)
        keyrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.PasswordEntry(); entry.set_text(sgdb_key(self.settings)); entry.set_show_peek_icon(True); entry.set_hexpand(True); entry.add_css_class("preferences-entry"); keyrow.append(entry)
        save = Gtk.Button(label="Save API key"); save.add_css_class("ludra-toolbar-control")
        def save_key(_b): self.settings.__setitem__("steamgriddb_api_key", entry.get_text().strip()) or save_json(settings_path(), self.settings)
        save.connect("clicked", save_key); keyrow.append(save); covers.append(keyrow)
        get_key = Gtk.Button(label="Get key ↗")
        get_key.add_css_class("ludra-toolbar-control")
        get_key.set_halign(Gtk.Align.START)
        def open_steamgriddb_api_page(_button):
            try:
                Gio.AppInfo.launch_default_for_uri("https://www.steamgriddb.com/profile/preferences/api", None)
            except Exception as exc:
                print(f"Could not open SteamGridDB API page: {exc}")
        get_key.connect("clicked", open_steamgriddb_api_page)
        covers.append(get_key)
        stack.add_named(covers, "covers")

        # Test49: the last loose Preferences sub-window is gone.  Reuse the
        # proven background picker directly inside the unified Preferences page.
        backgrounds = page("Background", "Choose a background — changes are shown immediately.")
        bg_grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        bg_grid.set_halign(Gtk.Align.CENTER)
        bg_grid.set_margin_top(4); bg_grid.set_margin_bottom(4)
        bg_grid.set_margin_start(8); bg_grid.set_margin_end(8)
        bg_choices = [
            ("Ludra Dawn", "background-thumb-dawn.jpg"),
            ("Aurora Blue", "background-thumb-aurora-blue.jpg"),
            ("Lavender Mist", "background-thumb-lavender-mist.jpg"),
            ("Rose Glow", "background-thumb-rose-glow.jpg"),
            ("Sage Light", "background-thumb-sage-light.jpg"),
            ("Twilight Glass", "background-thumb-twilight-glass.jpg"),
        ]
        bg_buttons = {}

        def refresh_inline_background_selection():
            selected = self.settings.get("background", "Ludra Dawn")
            for name, button in bg_buttons.items():
                if name == selected:
                    button.add_css_class("background-choice-selected")
                else:
                    button.remove_css_class("background-choice-selected")

        def choose_inline_background(_button, name):
            self.settings["background"] = name
            save_json(settings_path(), dict(self.settings))
            self.apply_css()
            refresh_inline_background_selection()

        for index, (name, filename) in enumerate(bg_choices):
            button = Gtk.Button(); button.add_css_class("background-choice"); button.set_tooltip_text(name); button.set_vexpand(False); button.set_valign(Gtk.Align.START)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            picture = Gtk.Picture.new_for_filename("/app/share/ludra/" + filename)
            picture.set_content_fit(Gtk.ContentFit.COVER); picture.set_size_request(150, 84)
            label = Gtk.Label(label=name); label.set_ellipsize(3)
            card.append(picture); card.append(label); button.set_child(card)
            button.connect("clicked", choose_inline_background, name)
            bg_buttons[name] = button
            bg_grid.attach(button, index % 3, index // 3, 1, 1)

        custom = Gtk.Button(); custom.add_css_class("background-choice"); custom.set_vexpand(False); custom.set_valign(Gtk.Align.START)
        custom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        custom_path = self.settings.get("custom_background", "")
        if custom_path and Path(custom_path).is_file():
            custom_picture = Gtk.Picture.new_for_filename(custom_path)
            custom_picture.set_content_fit(Gtk.ContentFit.COVER); custom_picture.set_size_request(150, 84)
            custom_box.append(custom_picture)
        else:
            custom_preview = Gtk.Box(); custom_preview.set_size_request(150, 84); custom_preview.add_css_class("custom-background-preview")
            plus = Gtk.Label(label="+"); plus.set_halign(Gtk.Align.CENTER); plus.set_valign(Gtk.Align.CENTER); plus.set_hexpand(True); plus.set_vexpand(True); plus.add_css_class("custom-background-plus")
            custom_preview.append(plus); custom_box.append(custom_preview)
        custom_box.append(Gtk.Label(label="Custom…")); custom.set_child(custom_box)
        custom.connect("clicked", lambda *_: self.choose_background())
        bg_buttons["Custom"] = custom
        custom_index = len(bg_choices); bg_grid.attach(custom, custom_index % 3, custom_index // 3, 1, 1)

        none = Gtk.Button(); none.add_css_class("background-choice"); none.set_tooltip_text("None"); none.set_vexpand(False); none.set_valign(Gtk.Align.START)
        none_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        none_preview = Gtk.Box(); none_preview.set_size_request(150, 84); none_preview.add_css_class("no-background-preview")
        none_mark = Gtk.Label(label="∅"); none_mark.set_halign(Gtk.Align.CENTER); none_mark.set_valign(Gtk.Align.CENTER); none_mark.set_hexpand(True); none_mark.set_vexpand(True); none_mark.add_css_class("no-background-mark")
        none_preview.append(none_mark); none_box.append(none_preview); none_box.append(Gtk.Label(label="None")); none.set_child(none_box)
        none.connect("clicked", choose_inline_background, "None"); bg_buttons["None"] = none
        none_index = custom_index + 1; bg_grid.attach(none, none_index % 3, none_index // 3, 1, 1)

        # RC4: small, quiet controls occupy the spare third-row grid cell.
        bg_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        bg_controls.set_valign(Gtk.Align.CENTER)
        bg_controls.set_halign(Gtk.Align.FILL)
        bg_controls.set_hexpand(True)
        bg_controls.add_css_class("ludra-background-controls")
        adjustment_widgets = {}

        def update_background_adjustment(_scale, setting, number):
            value = int(round(_scale.get_value()))
            self.settings[setting] = value
            number.set_text(f"{value}%")
            save_json(settings_path(), self.settings)
            # Debounce continuous mouse movement to avoid expensive image work.
            if getattr(self, "_background_adjustment_timer", 0):
                GLib.source_remove(self._background_adjustment_timer)
            self._background_adjustment_timer = GLib.timeout_add(260, self._apply_background_adjustment)

        for label_text, key, low, high in (
            ("Brightness", "background_brightness", 50, 120),
            ("Contrast", "background_contrast", 75, 125),
        ):
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            title = Gtk.Label(label=label_text, xalign=0)
            title.set_hexpand(True)
            title.add_css_class("ludra-background-adjustment-label")
            number = Gtk.Label(label=f'{self.settings.get(key, 100)}%')
            number.add_css_class("ludra-background-adjustment-value")
            heading.append(title); heading.append(number)
            bg_controls.append(heading)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, 1)
            scale.set_draw_value(False)
            scale.set_hexpand(True)
            scale.set_size_request(105, -1)
            scale.set_value(max(low, min(high, int(self.settings.get(key, 100)))))
            scale.add_css_class("ludra-background-adjustment-scale")
            scale.connect("value-changed", update_background_adjustment, key, number)
            bg_controls.append(scale)
            adjustment_widgets[key] = (scale, number)

        reset_adjustments = Gtk.Button(label="Reset")
        reset_adjustments.set_halign(Gtk.Align.END)
        reset_adjustments.add_css_class("ludra-background-adjustment-reset")
        def reset_background_adjustments(_button):
            # Set both values before applying, so we only redraw once.
            for key, (scale, number) in adjustment_widgets.items():
                scale.set_value(100)
            if getattr(self, "_background_adjustment_timer", 0):
                GLib.source_remove(self._background_adjustment_timer)
                self._background_adjustment_timer = 0
            self.settings["background_brightness"] = 100
            self.settings["background_contrast"] = 100
            save_json(settings_path(), self.settings)
            self.apply_css()
        reset_adjustments.connect("clicked", reset_background_adjustments)
        bg_controls.append(reset_adjustments)
        bg_grid.attach(bg_controls, 2, 2, 1, 1)
        # Keep None genuinely disabled, not visually adjustable.
        old_refresh_selection = refresh_inline_background_selection
        def refresh_inline_background_selection():
            old_refresh_selection()
            bg_controls.set_sensitive(self.settings.get("background", "Ludra Dawn") != "None")

        refresh_inline_background_selection()
        # Let the asynchronous Custom… chooser update the selected outline when
        # it returns, without creating another settings window.
        self._refresh_inline_background_selection = refresh_inline_background_selection
        bg_scroll = Gtk.ScrolledWindow(); bg_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); bg_scroll.set_child(backgrounds)
        backgrounds.append(bg_grid)
        stack.add_named(bg_scroll, "background")

        shortcuts = page("Shortcuts", "Keyboard shortcuts for navigating and controlling Ludra.")
        shortcut_grid = Gtk.Grid(column_spacing=22, row_spacing=10); shortcut_grid.set_halign(Gtk.Align.START); shortcut_grid.add_css_class("ludra-shortcuts-panel")
        shortcut_commands = (
            ("Navigate games", "↑  ↓  ←  →"),
            ("Launch selected game", "Enter"),
            ("Game actions", "Menu / Shift+F10"),
            ("Search", "Ctrl+F"),
            ("Preferences", "Ctrl+,"),
            ("Refresh library", "Ctrl+R"),
            ("Move between controls", "Tab / Shift+Tab"),
            ("Keyboard Shortcuts", "F1"),
            ("Close", "Esc"),
        )
        for row_index, (name, key) in enumerate(shortcut_commands):
            n = Gtk.Label(label=name, xalign=0); n.set_size_request(190, -1); n.add_css_class("ludra-shortcut-name")
            k = Gtk.Label(label=key, xalign=0); k.add_css_class("ludra-shortcut-key")
            shortcut_grid.attach(n, 0, row_index, 1, 1); shortcut_grid.attach(k, 1, row_index, 1, 1)
        shortcuts.append(shortcut_grid)
        stack.add_named(shortcuts, "shortcuts")

        # Test132: compact, readable About page with an optional gallery entry.
        # Keep the real GTK logo at its approved size; don't rasterize the whole UI.
        about_scroll = Gtk.ScrolledWindow()
        about_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        about = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        about.set_margin_top(13); about.set_margin_bottom(20)
        about.set_margin_start(20); about.set_margin_end(20)
        about_scroll.set_child(about)

        about_logo_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        about_logo_slot.set_size_request(300, 63)
        about_logo_slot.set_halign(Gtk.Align.CENTER)
        about_logo_slot.set_margin_top(5)
        about_logo_slot.set_margin_bottom(2)
        about_brand = Gtk.Picture.new_for_filename("/app/share/ludra/ludra-about-medium.png")
        about_brand.set_content_fit(Gtk.ContentFit.CONTAIN)
        about_brand.set_can_shrink(True)
        about_brand.set_size_request(300, 63)
        about_logo_slot.append(about_brand)
        about.append(about_logo_slot)

        def about_line(txt, css_class=None, gap=0):
            lab = Gtk.Label(label=txt)
            lab.set_halign(Gtk.Align.CENTER)
            lab.set_justify(Gtk.Justification.CENTER)
            lab.set_wrap(True)
            lab.set_margin_top(gap)
            if css_class: lab.add_css_class(css_class)
            about.append(lab)
            return lab

        about_line("Your games. One place.", "ludra-about-tagline")
        about_line("Version 1.0.0 RC4", "dim-label", 7)
        about_line("A simple, visual game launcher for Linux.", None, 1)
        about_line("Created by Denus01", None, 5)
        about_line("With assistance by ChatGPT", "dim-label")

        # Test139: discreet, keyboard-accessible glass thumbnail near the bottom.
        collage_path = "/app/share/ludra/ludra-behind-the-scenes.png"
        behind_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        behind_section.set_halign(Gtk.Align.CENTER)
        behind_section.set_margin_top(70)
        # Small decorative strokes, consistent with Ludra glass styling.
        behind_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        behind_heading.set_halign(Gtk.Align.CENTER)
        for side in ("left", "right"):
            if side == "right":
                behind_label = Gtk.Label(label="Behind the scenes")
                behind_label.add_css_class("ludra-behind-label")
                # Text remains centered between two identical strokes.
                behind_heading.append(behind_label)
            stroke = Gtk.Box()
            stroke.add_css_class("ludra-behind-rule")
            stroke.set_size_request(48, 1)
            stroke.set_valign(Gtk.Align.CENTER)
            behind_heading.append(stroke)
        # Reorder to left stroke, text, right stroke.
        behind_section.append(behind_heading)

        def open_collage(*_):
            # Show only the artwork, scaled to the available area, and Close.
            viewer = Gtk.Window(transient_for=d, modal=False)
            viewer.set_title("Ludra — Behind the scenes")
            # RC4: size the viewer from the artwork rather than letting the
            # window stretch independently and leave large empty bands.
            # KDE/Wayland does not reliably enforce top-level aspect hints, so
            # this gallery viewer has a compact, non-resizable presentation.
            try:
                collage_pix = GdkPixbuf.Pixbuf.new_from_file(collage_path)
                image_ratio = collage_pix.get_width() / max(1, collage_pix.get_height())
            except Exception:
                image_ratio = 16.0 / 9.0
            image_width = min(960, round(620 * image_ratio))
            image_height = max(1, round(image_width / image_ratio))
            viewer.set_default_size(image_width + 20, image_height + 90)
            viewer.set_resizable(False)
            viewer.add_css_class("ludra-collage-viewer")
            # Match the Preferences window's real GTK titlebar and controls.
            collage_header = Gtk.HeaderBar()
            collage_header.add_css_class("ludra-preferences-titlebar")
            collage_header.set_show_title_buttons(True)
            collage_title = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            collage_title.set_halign(Gtk.Align.CENTER)
            collage_title.set_valign(Gtk.Align.CENTER)
            collage_icon = Gtk.Label(label="🎮")
            collage_icon.add_css_class("ludra-preferences-title-gear")
            collage_title.append(collage_icon)
            collage_name = Gtk.Label(label="Behind the scenes")
            collage_name.add_css_class("ludra-preferences-title")
            collage_title.append(collage_name)
            collage_header.set_title_widget(collage_title)
            viewer.set_titlebar(collage_header)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            outer.add_css_class("ludra-preferences-content")
            # Test140: a thin, translucent Ludra-style frame around the picture.
            frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            frame.add_css_class("ludra-collage-frame")
            frame.set_halign(Gtk.Align.CENTER)
            frame.set_valign(Gtk.Align.CENTER)
            artwork = Gtk.Picture.new_for_filename(collage_path)
            artwork.set_content_fit(Gtk.ContentFit.CONTAIN)
            artwork.set_can_shrink(True)
            artwork.set_size_request(image_width, image_height)
            artwork.set_halign(Gtk.Align.CENTER)
            artwork.set_valign(Gtk.Align.CENTER)
            frame.append(artwork)
            outer.append(frame)
            close_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            close_row.set_halign(Gtk.Align.CENTER)
            close_row.set_margin_top(6)
            close_row.set_margin_bottom(8)
            close_button = Gtk.Button(label="Close")
            close_button.add_css_class("ludra-toolbar-control")
            close_button.connect("clicked", lambda *_: viewer.close())
            close_row.append(close_button)
            outer.append(close_row)
            viewer.set_child(outer)
            viewer.present()

        thumb_button = Gtk.Button()
        thumb_button.add_css_class("ludra-behind-thumbnail")
        thumb_button.set_halign(Gtk.Align.CENTER)
        thumb_button.set_tooltip_text("Open Behind the scenes")
        thumbnail = Gtk.Picture.new_for_filename(collage_path)
        thumbnail.set_content_fit(Gtk.ContentFit.COVER)
        thumbnail.set_can_shrink(True)
        thumbnail.set_size_request(204, 108)
        thumb_button.set_child(thumbnail)
        thumb_button.connect("clicked", open_collage)
        behind_section.append(thumb_button)
        about.append(behind_section)
        stack.add_named(about_scroll, "about")

        nav = (("General","general"),("Library","library"),("Cover images","covers"),("Background","background"),("Shortcuts","shortcuts"),("About","about"))
        group = None
        for label_text, name in nav:
            b = Gtk.ToggleButton(label=label_text); b.set_halign(Gtk.Align.FILL); b.add_css_class("preferences-nav-button")
            if group is not None: b.set_group(group)
            else: group = b; b.set_active(True)
            b.connect("toggled", lambda btn, n=name: stack.set_visible_child_name(n) if btn.get_active() else None)
            sidebar.append(b)

        # Test55: one predictable exit for the whole unified Preferences window.
        # The expanding spacer keeps Close anchored to the bottom of the sidebar.
        sidebar_spacer = Gtk.Box(); sidebar_spacer.set_vexpand(True); sidebar.append(sidebar_spacer)
        close_preferences = Gtk.Button(label="Close")
        close_preferences.set_halign(Gtk.Align.FILL)
        close_preferences.add_css_class("preferences-close-button")
        close_preferences.connect("clicked", lambda *_: d.hide())
        sidebar.append(close_preferences)

        body.append(sidebar); body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)); body.append(stack); root.append(body)
        keys=Gtk.EventControllerKey(); keys.connect("key-pressed", lambda _c,key,_code,_state: (d.hide() or True) if key==Gdk.KEY_Escape else False); d.add_controller(keys)
        d.set_child(root); d.present()

    def build_preferences(self):
        menu = Gio.Menu()

        # Appearance
        appearance = Gio.Menu()
        appearance.append("Cover images", "app.cover_images")
        menu.append_section(None, appearance)

        # Library
        library = Gio.Menu()
        library.append("Add non-Steam game", "app.add_game")
        self._hidden_menu_item = Gio.MenuItem.new(
            f"Manage hidden ({len(self.settings.get('hidden_games', []))})",
            "app.hidden_games"
        )
        library.append_item(self._hidden_menu_item)
        menu.append_section(None, library)

        # Behavior lives in its own small settings window, keeping the
        # Preferences popover structurally consistent with the other sections.
        behaviour = Gio.Menu()
        behaviour.append("Behavior", "app.behavior")
        menu.append_section(None, behaviour)

        # Application
        application = Gio.Menu()
        application.append("Background", "app.backgrounds")
        application.append("Keyboard Shortcuts", "app.keyboard_commands")
        application.append("About Ludra", "app.about")
        menu.append_section(None, application)

        self._install_actions()
        popover = Gtk.PopoverMenu.new_from_model(menu)

        return popover

    def _update_hidden_menu_label(self):
        item = getattr(self, "_hidden_menu_item", None)
        if item is not None:
            hidden = set(self.settings.get("hidden_games", []))
            forced_visible = set(self.settings.get("forced_visible", []))
            auto_hidden = {g.get("key") for g in getattr(self, "games", []) if not is_real_game(g) and g.get("key") not in forced_visible}
            item.set_label(f"Manage hidden ({len(hidden | auto_hidden)})")

    def _install_actions(self):
        actions = [
            ("refresh", self.refresh), ("behavior", self.behavior_dialog), ("cover_images", self.cover_images_dialog), ("api_key", self.api_key_dialog), ("add_game", self.add_game_dialog), ("hidden_games", self.hidden_games_dialog), ("backgrounds", self.background_dialog), ("keyboard_commands", self.keyboard_commands_dialog), ("about", self.about_dialog),
        ]
        for name, fn in actions:
            action = Gio.SimpleAction.new(name, None); action.connect("activate", lambda _a, _p, f=fn: f()); self.add_action(action)

        source_actions = {
            "source_sgdbsteam": "SteamGridDB → Steam",
            "source_steam": "Steam",
            "source_sgdb": "SteamGridDB",
        }
        current = self.settings.get("artwork_source", "SteamGridDB → Steam")
        for name, value in source_actions.items():
            action = Gio.SimpleAction.new_stateful(name, None, GLib.Variant("b", current == value))
            def choose_source(_action, _parameter, selected=value):
                self.set_setting("artwork_source", selected)
                for action_name, action_value in source_actions.items():
                    installed = self.lookup_action(action_name)
                    if installed is not None:
                        installed.set_state(GLib.Variant("b", action_value == selected))
            action.connect("activate", choose_source)
            self.add_action(action)

    def behavior_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Behavior")
        d.set_default_size(500, 180)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(20); box.set_margin_end(20)

        header = Gtk.Box(spacing=10)
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda *_: d.close())
        header.append(close)
        title = Gtk.Label(label="Behavior", xalign=0)
        title.add_css_class("title-2"); title.set_hexpand(True)
        header.append(title)
        box.append(header)

        row = Gtk.Button()
        row.set_has_frame(False)
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row_box.set_margin_top(6); row_box.set_margin_bottom(6)
        row_box.set_margin_start(4); row_box.set_margin_end(4)
        mark = Gtk.Label(xalign=0); mark.set_size_request(18, -1)
        label = Gtk.Label(label="Close Ludra when a game starts", xalign=0)
        label.set_hexpand(True)
        row_box.append(mark); row_box.append(label); row.set_child(row_box)

        def refresh_mark():
            mark.set_text("✓" if self.settings.get("close_on_launch", False) else "")

        def toggle(*_args):
            self.settings["close_on_launch"] = not bool(self.settings.get("close_on_launch", False))
            save_json(settings_path(), self.settings)
            refresh_mark()

        row.connect("clicked", toggle)
        refresh_mark()
        box.append(row)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, key, _code, _state: (d.close() or True) if key == Gdk.KEY_Escape else False)
        d.add_controller(keys)
        d.set_child(box)
        d.present()

    def background_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Background")
        # Keep the selector at its intended 3-column layout.  Letting this
        # utility window resize makes the cards stretch into odd proportions.
        d.set_default_size(850, 735)
        d.set_resizable(False)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(20); outer.set_margin_bottom(20)
        outer.set_margin_start(22); outer.set_margin_end(22)

        header = Gtk.Box(spacing=10)
        back = Gtk.Button(label="Close")
        back.set_halign(Gtk.Align.START)

        def leave_backgrounds(*_args):
            # Background choices are live; Close leaves this window.
            d.close()

        back.connect("clicked", leave_backgrounds)
        header.append(back)

        title = Gtk.Label(label="Background", xalign=0)
        title.add_css_class("title-2")
        title.set_hexpand(True)
        header.append(title)
        outer.append(header)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, key, _code, _state: (leave_backgrounds() or True) if key == Gdk.KEY_Escape else False)
        d.add_controller(keys)

        hint = Gtk.Label(label="Choose a background — changes are shown immediately.", xalign=0)
        hint.add_css_class("dim-label")
        outer.append(hint)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        grid.set_halign(Gtk.Align.CENTER)
        # Keep a real outer gutter around the background cards.  The cards may
        # still share the available width, but they must never run flush into
        # the left/right edges of the scrolled area.
        grid.set_margin_top(4); grid.set_margin_bottom(4)
        grid.set_margin_start(18); grid.set_margin_end(18)
        scroller.set_child(grid)
        outer.append(scroller)

        choices = [
            ("Ludra Dawn", "background-thumb-dawn.jpg"),
            ("Aurora Blue", "background-thumb-aurora-blue.jpg"),
            ("Lavender Mist", "background-thumb-lavender-mist.jpg"),
            ("Rose Glow", "background-thumb-rose-glow.jpg"),
            ("Sage Light", "background-thumb-sage-light.jpg"),
            ("Twilight Glass", "background-thumb-twilight-glass.jpg"),
        ]
        buttons = {}

        def refresh_selection():
            selected = self.settings.get("background", "Ludra Dawn")
            for name, button in buttons.items():
                if name == selected:
                    button.add_css_class("background-choice-selected")
                else:
                    button.remove_css_class("background-choice-selected")

        def choose_builtin(_button, name):
            # Persist the choice immediately, then repaint the live gallery.
            # Keep this explicit here so the visual picker and startup restore
            # always use the same saved value.
            self.settings["background"] = name
            save_json(settings_path(), dict(self.settings))
            self.apply_css()
            refresh_selection()

        for index, (name, filename) in enumerate(choices):
            button = Gtk.Button()
            button.add_css_class("background-choice")
            button.set_tooltip_text(name)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            picture = Gtk.Picture.new_for_filename("/app/share/ludra/" + filename)
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_size_request(170, 96)
            label = Gtk.Label(label=name)
            label.set_ellipsize(3)
            card.append(picture); card.append(label)
            button.set_child(card)
            button.connect("clicked", choose_builtin, name)
            buttons[name] = button
            grid.attach(button, index % 3, index // 3, 1, 1)

        custom = Gtk.Button()
        custom.add_css_class("background-choice")
        custom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        custom_path = self.settings.get("custom_background", "")
        if custom_path and Path(custom_path).is_file():
            custom_picture = Gtk.Picture.new_for_filename(custom_path)
            custom_picture.set_content_fit(Gtk.ContentFit.COVER)
            custom_picture.set_size_request(170, 96)
            custom_box.append(custom_picture)
        else:
            custom_preview = Gtk.Box()
            custom_preview.set_size_request(170, 96)
            custom_preview.add_css_class("custom-background-preview")
            plus = Gtk.Label(label="+")
            plus.set_halign(Gtk.Align.CENTER); plus.set_valign(Gtk.Align.CENTER)
            plus.set_hexpand(True); plus.set_vexpand(True)
            plus.add_css_class("custom-background-plus")
            custom_preview.append(plus)
            custom_box.append(custom_preview)
        custom_box.append(Gtk.Label(label="Custom…"))
        custom.set_child(custom_box)
        custom.connect("clicked", lambda *_: self.choose_background())
        buttons["Custom"] = custom
        custom_index = len(choices)
        grid.attach(custom, custom_index % 3, custom_index // 3, 1, 1)

        # "None" deliberately keeps Ludra's normal GTK base/shade but removes
        # the decorative background image.  Custom and None stay last.
        none = Gtk.Button()
        none.add_css_class("background-choice")
        none.set_tooltip_text("None")
        none_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        none_preview = Gtk.Box()
        none_preview.set_size_request(170, 96)
        none_preview.add_css_class("no-background-preview")
        none_mark = Gtk.Label(label="∅")
        none_mark.set_halign(Gtk.Align.CENTER); none_mark.set_valign(Gtk.Align.CENTER)
        none_mark.set_hexpand(True); none_mark.set_vexpand(True)
        none_mark.add_css_class("no-background-mark")
        none_preview.append(none_mark)
        none_box.append(none_preview)
        none_box.append(Gtk.Label(label="None"))
        none.set_child(none_box)
        none.connect("clicked", choose_builtin, "None")
        buttons["None"] = none
        none_index = custom_index + 1
        grid.attach(none, none_index % 3, none_index // 3, 1, 1)

        refresh_selection()
        d.set_child(outer)
        d.present()

    def keyboard_commands_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Keyboard Shortcuts")
        d.set_default_size(460, 390)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20); box.set_margin_bottom(20); box.set_margin_start(24); box.set_margin_end(24)

        header = Gtk.Box(spacing=10)
        back = Gtk.Button(label="Close")
        back.connect("clicked", lambda *_: d.close())
        header.append(back)
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Keyboard Shortcuts</span>")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)
        box.append(header)

        commands = [
            ("Navigate games", "↑  ↓  ←  →"),
            ("Launch selected game", "Enter"),
            ("Game actions", "Menu / Shift+F10"),
            ("Search", "Ctrl+F"),
            ("Preferences", "Ctrl+,"),
            ("Return to library / Close", "Esc"),
            ("Move between controls", "Tab / Shift+Tab"),
            ("Keyboard Shortcuts", "F1"),
        ]
        grid = Gtk.Grid(column_spacing=28, row_spacing=12)
        grid.set_margin_top(8)
        for row, (command, key) in enumerate(commands):
            left = Gtk.Label(label=command); left.set_halign(Gtk.Align.START); left.set_hexpand(True)
            right = Gtk.Label(label=key); right.set_halign(Gtk.Align.END); right.add_css_class("dim-label")
            grid.attach(left, 0, row, 1, 1); grid.attach(right, 1, row, 1, 1)
        box.append(grid)

        d.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, keyval, _code, _state: (d.close() or True) if (Gdk.keyval_name(keyval) or "") == "Escape" else False)
        d.add_controller(keys)
        d.present()

    def _focused_card_index(self):
        for i, card in enumerate(getattr(self, "_visible_cards", [])):
            if card.has_focus():
                return i
        return -1

    def _focus_card(self, index):
        cards = getattr(self, "_visible_cards", [])
        if not cards:
            return False
        index = max(0, min(index, len(cards) - 1))
        cards[index].grab_focus()
        return True

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        name = Gdk.keyval_name(keyval) or ""
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if name == "F1":
            self.keyboard_commands_dialog()
            return True
        if ctrl and name.lower() == "f":
            self.search.grab_focus()
            return True
        if ctrl and name in ("comma", ","):
            self.pref_button.grab_focus()
            self.pref_button.popup()
            return True
        if name == "Escape":
            self.pref_button.popdown()
            if self.search.has_focus() and self.search.get_text():
                self.search.set_text("")
                return True
            return self._focus_card(max(0, self._focused_card_index()))

        idx = self._focused_card_index()
        if idx < 0:
            if self.search.has_focus():
                return False
            if name in ("Left", "Right", "Up", "Down"):
                return self._focus_card(0)
            return False

        columns = max(1, int(getattr(self, "_flow_columns", 1) or 1))
        target = idx
        if name == "Left": target = idx - 1
        elif name == "Right": target = idx + 1
        elif name == "Up": target = idx - columns
        elif name == "Down": target = idx + columns
        elif name in ("Return", "KP_Enter"):
            self.launch_game(self._visible_cards[idx].game)
            return True
        elif name == "Menu" or (shift and name == "F10"):
            self._visible_cards[idx].show_context_menu()
            return True
        else:
            return False

        if 0 <= target < len(self._visible_cards):
            return self._focus_card(target)
        return True

    def about_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("About Ludra")
        d.set_default_size(470, 345)
        d.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(26); box.set_margin_bottom(22)
        box.set_margin_start(28); box.set_margin_end(28)

        # Test90: same crisp, restrained identity as the Preferences About page.
        identity_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        identity_slot.set_size_request(300, 63)
        identity_slot.set_hexpand(False)
        identity_slot.set_halign(Gtk.Align.CENTER)
        identity = Gtk.Picture.new_for_filename("/app/share/ludra/ludra-about-medium.png")
        identity.set_content_fit(Gtk.ContentFit.CONTAIN)
        identity.set_can_shrink(True)
        identity.set_size_request(300, 63)
        identity.set_hexpand(False)
        identity_slot.append(identity)
        box.append(identity_slot)

        tagline = Gtk.Label(label="Your games. One place.")
        box.append(tagline)
        version = Gtk.Label(label="Version 1.0.0 RC4")
        version.add_css_class("dim-label")
        box.append(version)
        desc = Gtk.Label(label="A simple, visual game launcher for Linux.")
        desc.set_wrap(True)
        box.append(desc)
        credits = Gtk.Label(label="Created by Denus01\nWith assistance from ChatGPT")
        credits.set_justify(Gtk.Justification.CENTER)
        credits.set_wrap(True)
        credits.add_css_class("dim-label")
        box.append(credits)

        # Preserve the tiny hidden piece of Ludra history. 🤘
        easter = Gtk.Button(label="L")
        easter.set_halign(Gtk.Align.END)
        easter.set_has_frame(False)
        easter.set_opacity(0.07)
        easter.set_size_request(18, 18)
        easter.connect("clicked", lambda *_: self.easter_egg_dialog(d))
        box.append(easter)

        close = Gtk.Button(label="Close")
        close.set_halign(Gtk.Align.CENTER)
        close.connect("clicked", lambda *_: d.close())
        box.append(close)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, keyval, _code, _state: (d.close() or True) if (Gdk.keyval_name(keyval) or "") == "Escape" else False)
        d.add_controller(keys)
        d.set_child(box)
        d.present()

    def easter_egg_dialog(self, parent):
        e = Gtk.Window(transient_for=parent, modal=True)
        e.set_title("Ludra")
        e.set_default_size(520, 220)
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        b.set_margin_top(24); b.set_margin_bottom(24); b.set_margin_start(28); b.set_margin_end(28)
        msg = Gtk.Label(label="The Sacred Resize Code That Shall Not Be Named™, Computer B: Head of QA, and Ludra the Czech death-metal band walk into a Flatpak…\n\nIf you understand this, you were there.")
        msg.set_wrap(True)
        msg.set_justify(Gtk.Justification.CENTER)
        b.append(msg)
        c = Gtk.Button(label="🤘")
        c.set_halign(Gtk.Align.CENTER)
        c.connect("clicked", lambda *_: e.close())
        b.append(c)
        e.set_child(b)
        e.present()

    def choose_background(self):
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose custom background")
        filt = Gtk.FileFilter()
        filt.set_name("Images")
        filt.add_mime_type("image/png")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/webp")
        fs = Gio.ListStore.new(Gtk.FileFilter)
        fs.append(filt)
        dialog.set_filters(fs)
        dialog.set_default_filter(filt)
        dialog.open(self.window, None, self.background_chosen)

    def background_chosen(self, dialog, res):
        try:
            src = dialog.open_finish(res).get_path()
            if not src:
                return
            data = Path(src).read_bytes()
            if not _image_info(data):
                return
            suffix = Path(src).suffix.lower()
            if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
                suffix = ".jpg"
            dest = app_data_dir() / ("custom-background" + suffix)
            # Remove an older custom background with another extension.
            for old in app_data_dir().glob("custom-background.*"):
                try:
                    old.unlink()
                except Exception:
                    pass
            dest.write_bytes(data)
            self.settings["custom_background"] = str(dest)
            self.settings["background"] = "Custom"
            save_json(settings_path(), self.settings)
            self.apply_css()
            refresh = getattr(self, "_refresh_inline_background_selection", None)
            if refresh is not None:
                refresh()
        except Exception:
            pass

    def set_setting(self, key, value):
        self.settings[key] = value; save_json(settings_path(), self.settings)
        if key == "background": self.apply_css()
        elif key == "artwork_source": self.populate()

    def cover_images_dialog(self):
        """Cover artwork settings in a real window, not a nested popover."""
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Cover images")
        d.set_default_size(520, 360)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20)
        box.set_margin_start(20); box.set_margin_end(20)

        header = Gtk.Box(spacing=10)
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda *_: d.close())
        header.append(close)
        title = Gtk.Label(label="Cover images", xalign=0)
        title.add_css_class("title-2"); title.set_hexpand(True)
        header.append(title)
        box.append(header)

        source_title = Gtk.Label(label="Image source", xalign=0)
        source_title.add_css_class("heading")
        source_title.set_margin_top(4)
        box.append(source_title)

        cover_marks = {}
        choices = [
            ("SteamGridDB → Steam", "SteamGridDB → Steam"),
            ("Steam only", "Steam"),
            ("SteamGridDB only", "SteamGridDB"),
        ]

        def refresh_marks():
            active = self.settings.get("artwork_source", "SteamGridDB → Steam")
            for value, mark in cover_marks.items():
                mark.set_text("✓" if active == value else "")

        for label_text, value in choices:
            row = Gtk.Button()
            row.set_has_frame(False)
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.set_margin_top(3); row_box.set_margin_bottom(3)
            row_box.set_margin_start(4); row_box.set_margin_end(4)
            mark = Gtk.Label(xalign=0); mark.set_size_request(18, -1)
            label = Gtk.Label(label=label_text, xalign=0); label.set_hexpand(True)
            row_box.append(mark); row_box.append(label); row.set_child(row_box)
            cover_marks[value] = mark
            def choose_cover(_button, selected=value):
                self.set_setting("artwork_source", selected)
                refresh_marks()
            row.connect("clicked", choose_cover)
            box.append(row)
        refresh_marks()

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4); sep.set_margin_bottom(4)
        box.append(sep)

        api_title = Gtk.Label(label="SteamGridDB API key", xalign=0)
        api_title.add_css_class("heading")
        box.append(api_title)
        info = Gtk.Label(label="Stored locally for Ludra.", xalign=0)
        info.add_css_class("dim-label")
        box.append(info)

        key_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.PasswordEntry(); entry.set_text(sgdb_key(self.settings)); entry.set_show_peek_icon(True); entry.set_hexpand(True); entry.add_css_class("preferences-entry")
        key_row.append(entry)
        get_key = Gtk.Button(label="Get key ↗"); get_key.add_css_class("ludra-toolbar-control"); key_row.append(get_key)
        box.append(key_row)

        def open_key_page(_):
            try:
                subprocess.Popen(["xdg-open", "https://www.steamgriddb.com/profile/preferences/api"], start_new_session=True)
            except Exception as exc:
                print(f"Could not open SteamGridDB API page: {exc}")
        get_key.connect("clicked", open_key_page)

        save = Gtk.Button(label="Save API key"); save.add_css_class("ludra-toolbar-control")
        save.set_halign(Gtk.Align.END)
        def save_key(_):
            self.settings["steamgriddb_api_key"] = entry.get_text().strip()
            save_json(settings_path(), self.settings)
        save.connect("clicked", save_key)
        box.append(save)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, key, _code, _state: (d.close() or True) if key == Gdk.KEY_Escape else False)
        d.add_controller(keys)
        d.set_child(box)
        d.present()

    def api_key_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True); d.set_title("SteamGridDB API key"); d.set_default_size(520, 220)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); box.set_margin_top(20); box.set_margin_bottom(20); box.set_margin_start(20); box.set_margin_end(20)
        header = Gtk.Box(spacing=10)
        back = Gtk.Button(label="‹  Back"); back.add_css_class("ludra-toolbar-control")
        def return_to_cover_images(*_args):
            d.close()
            popover = self.pref_button.get_popover()
            # Re-open Preferences on the same Cover images submenu page that
            # launched this dialog, rather than dumping the user at the library.
            submenu = getattr(self, "_api_return_submenu", None)
            # Gtk.PopoverMenu resets its stack to the main page while it is
            # being mapped.  Therefore setting visible-submenu *before* popup()
            # is overwritten by GTK.  Re-open first, then switch pages on the
            # next main-loop iteration once the popover has been mapped.
            popover.popup()
            if submenu:
                def restore_cover_submenu():
                    popover.set_visible_submenu(submenu)
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(restore_cover_submenu)
        back.connect("clicked", return_to_cover_images); header.append(back)
        title = Gtk.Label(label="SteamGridDB API key", xalign=0); title.add_css_class("title-2"); title.set_hexpand(True); header.append(title)
        box.append(header)
        info = Gtk.Label(label="Paste your SteamGridDB API key. It is stored locally for Ludra."); info.set_wrap(True); info.set_halign(Gtk.Align.START); box.append(info)
        key_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.PasswordEntry(); entry.set_text(sgdb_key(self.settings)); entry.set_show_peek_icon(True); entry.set_hexpand(True); entry.add_css_class("preferences-entry"); key_row.append(entry)
        get_key = Gtk.Button(label="Get key ↗"); get_key.add_css_class("ludra-toolbar-control"); get_key.set_valign(Gtk.Align.CENTER); key_row.append(get_key); box.append(key_row)
        def open_key_page(_):
            try:
                subprocess.Popen(["xdg-open", "https://www.steamgriddb.com/profile/preferences/api"], start_new_session=True)
            except Exception as exc:
                print(f"Could not open SteamGridDB API page: {exc}")
        get_key.connect("clicked", open_key_page)
        buttons = Gtk.Box(spacing=8); buttons.set_halign(Gtk.Align.END); cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("ludra-toolbar-control"); save = Gtk.Button(label="Save"); save.add_css_class("ludra-toolbar-control")
        cancel.connect("clicked", lambda *_: d.close())
        def save_key(_): self.settings["steamgriddb_api_key"] = entry.get_text().strip(); save_json(settings_path(), self.settings); d.close(); self.populate()
        save.connect("clicked", save_key); buttons.append(cancel); buttons.append(save); box.append(buttons)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, key, _code, _state: (d.close() or True) if key == Gdk.KEY_Escape else False)
        d.add_controller(keys)
        d.set_child(box); d.present()

    def add_game_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True); d.set_title("Add non-Steam game"); d.set_default_size(640, 390)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); box.set_margin_top(20); box.set_margin_bottom(20); box.set_margin_start(20); box.set_margin_end(20)
        header = Gtk.Box(spacing=10)
        back = Gtk.Button(label="Close"); back.connect("clicked", lambda *_: d.close()); header.append(back)
        title = Gtk.Label(label="Add non-Steam game", xalign=0); title.add_css_class("title-2"); title.set_hexpand(True); header.append(title)
        box.append(header)
        name = Gtk.Entry(); name.set_placeholder_text("Game name"); box.append(Gtk.Label(label="Game name", xalign=0)); box.append(name)

        path_box = Gtk.Box(spacing=8); path = Gtk.Entry(); path.set_hexpand(True); path_box.append(path); browse = Gtk.Button(label="Browse…"); path_box.append(browse); box.append(Gtk.Label(label="Executable (optional)", xalign=0)); box.append(path_box)
        browse.connect("clicked", lambda *_: self.pick_executable(path))

        command = Gtk.Entry(); command.set_hexpand(True); command.set_placeholder_text("steam://rungameid/16987727714603499520"); box.append(Gtk.Label(label="Launch command / Steam URI (optional)", xalign=0)); box.append(command)
        hint = Gtk.Label(label="For Steam-added non-Steam games, paste the Steam URI here. If you use an executable, you can instead enter normal command-line arguments.", xalign=0); hint.set_wrap(True); hint.add_css_class("dim-label"); box.append(hint)

        buttons = Gtk.Box(spacing=8); buttons.set_halign(Gtk.Align.END); add = Gtk.Button(label="Add")
        # Enable Add only when the game has a usable title (or executable-derived
        # title) and at least one launch method. Keep the original validation
        # inside add_game as a second line of defense.
        def update_add_enabled(*_args):
            p = path.get_text().strip()
            c = command.get_text().strip()
            n = name.get_text().strip() or (Path(p).stem if p else "")
            add.set_sensitive(bool(n and (p or c)))
        for field in (name, path, command):
            field.connect("changed", update_add_enabled)
        update_add_enabled()
        def add_game(_):
            p = path.get_text().strip(); c = command.get_text().strip(); n = name.get_text().strip() or (Path(p).stem if p else "")
            if not n or (not p and not c): return
            item = {"kind": "custom", "key": "custom:" + GLib.uuid_string_random(), "name": n, "executable": p, "launch_command": c, "last_played": 0}
            self.custom_games.append(item); save_json(custom_games_path(), self.custom_games); d.close(); self.refresh()
        add.connect("clicked", add_game); buttons.append(add); box.append(buttons); d.set_child(box); d.present()

    def edit_game_dialog(self, game):
        d = Gtk.Window(transient_for=self.window, modal=True); d.set_title("Edit game"); d.set_default_size(640, 340)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); box.set_margin_top(20); box.set_margin_bottom(20); box.set_margin_start(20); box.set_margin_end(20)
        name = Gtk.Entry(); name.set_text(game.get("name", "")); box.append(Gtk.Label(label="Game name", xalign=0)); box.append(name)

        path_box = Gtk.Box(spacing=8); path = Gtk.Entry(); path.set_text(game.get("executable", "")); path.set_hexpand(True); path_box.append(path); browse = Gtk.Button(label="Browse…"); path_box.append(browse); box.append(Gtk.Label(label="Executable (optional)", xalign=0)); box.append(path_box)
        browse.connect("clicked", lambda *_: self.pick_executable(path))

        command = Gtk.Entry(); command.set_text(game.get("launch_command", "")); command.set_hexpand(True); command.set_placeholder_text("steam://rungameid/16987727714603499520"); box.append(Gtk.Label(label="Launch command / Steam URI (optional)", xalign=0)); box.append(command)
        hint = Gtk.Label(label="For Steam-added non-Steam games, paste the Steam URI here. If you use an executable, you can instead enter normal command-line arguments.", xalign=0); hint.set_wrap(True); hint.add_css_class("dim-label"); box.append(hint)

        buttons = Gtk.Box(spacing=8); buttons.set_halign(Gtk.Align.END); cancel = Gtk.Button(label="Cancel"); save = Gtk.Button(label="Save")
        cancel.connect("clicked", lambda *_: d.close())
        def save_game(_):
            pth = path.get_text().strip(); cmd = command.get_text().strip(); nm = name.get_text().strip() or (Path(pth).stem if pth else game.get("name", "Game"))
            if not nm or (not pth and not cmd): return
            game["name"] = nm; game["executable"] = pth; game["launch_command"] = cmd
            for item in self.custom_games:
                if item.get("key") == game.get("key"):
                    item.update(game)
            save_json(custom_games_path(), self.custom_games); d.close(); self.refresh()
        save.connect("clicked", save_game); buttons.append(cancel); buttons.append(save); box.append(buttons); d.set_child(box); d.present()

    def edit_steam_launch_dialog(self, game):
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Edit launch command")
        d.set_default_size(640, 230)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20); box.set_margin_bottom(20); box.set_margin_start(20); box.set_margin_end(20)

        title = Gtk.Label(label=game.get("name", "Steam game"), xalign=0)
        title.add_css_class("title-3"); box.append(title)
        box.append(Gtk.Label(label="Launch command override", xalign=0))
        command = Gtk.Entry(); command.set_hexpand(True)
        overrides = self.settings.setdefault("steam_launch_overrides", {})
        command.set_text(str(overrides.get(str(game.get("appid", "")), "")))
        command.set_placeholder_text(f"steam://rungameid/{game.get('appid', '')}")
        box.append(command)
        hint = Gtk.Label(label="Leave this empty to use Ludra's automatic Steam launch command. A Steam URI such as steam://rungameid/822240 can be entered here.", xalign=0)
        hint.set_wrap(True); hint.add_css_class("dim-label"); box.append(hint)

        buttons = Gtk.Box(spacing=8); buttons.set_halign(Gtk.Align.END)
        reset = Gtk.Button(label="Reset to automatic"); cancel = Gtk.Button(label="Cancel"); save = Gtk.Button(label="Save")
        cancel.connect("clicked", lambda *_: d.close())
        def reset_command(_): command.set_text("")
        reset.connect("clicked", reset_command)
        def save_command(_):
            appid = str(game.get("appid", "")); value = command.get_text().strip()
            if value: overrides[appid] = value
            else: overrides.pop(appid, None)
            save_json(settings_path(), self.settings); d.close()
        save.connect("clicked", save_command)
        buttons.append(reset); buttons.append(cancel); buttons.append(save); box.append(buttons)
        d.set_child(box); d.present()

    def pick_executable(self, entry):
        dialog = Gtk.FileDialog(); dialog.set_title("Select game executable")
        dialog.open(self.window, None, lambda obj, res: self.file_chosen(obj, res, entry))

    def file_chosen(self, dialog, res, entry):
        try: entry.set_text(dialog.open_finish(res).get_path())
        except Exception: pass

    def save_normalized_custom_cover(self, game, data):
        # Keep the user's original bytes. GdkPixbuf detects the image format
        # from content, so the historical .jpg cache filename is harmless even
        # for PNG/WebP. Preserving the source keeps transparency and gives the
        # artwork-derived backdrop the best possible input on every launch.
        try:
            if not _image_info(data):
                return
            path = custom_cover_path(game)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except Exception:
            pass

    def choose_image(self, game, parent=None):
        dialog = Gtk.FileDialog(); dialog.set_title("Choose cover image")
        filt = Gtk.FileFilter(); filt.set_name("Images"); filt.add_mime_type("image/png"); filt.add_mime_type("image/jpeg"); filt.add_mime_type("image/webp")
        fs = Gio.ListStore.new(Gtk.FileFilter); fs.append(filt); dialog.set_filters(fs); dialog.set_default_filter(filt)
        dialog.open(self.window, None, lambda obj, res: self.image_chosen(obj, res, game, parent))

    def image_chosen(self, dialog, res, game, parent):
        try:
            src = dialog.open_finish(res).get_path(); data = Path(src).read_bytes(); info = _image_info(data)
            if not info: return
            self.save_normalized_custom_cover(game, data)
            if parent: parent.close()
            self.populate()
        except Exception: pass

    def open_cover_search(self, game):
        if not sgdb_key(self.settings):
            self.api_key_dialog(); return
        CoverDialog(self, game)

    def reset_cover(self, game):
        try: custom_cover_path(game).unlink(missing_ok=True)
        except Exception: pass
        self.populate()

    def launch_game(self, game):
        try:
            if game["kind"] == "steam":
                override = str(self.settings.get("steam_launch_overrides", {}).get(str(game["appid"]), "")).strip()
                if override:
                    if override.startswith(("steam://", "http://", "https://", "file://")):
                        Gio.AppInfo.launch_default_for_uri(override, None)
                    else:
                        subprocess.Popen(shlex.split(override), start_new_session=True)
                else:
                    launch_steam(game["appid"])
            else: launch_custom(game)

            # Record the successful launch first. If requested, Ludra will
            # really terminate after this state has been persisted below.
            close_after_launch = bool(self.settings.get("close_on_launch", False))

            game["last_played"] = int(GLib.get_monotonic_time() / 1000)
            # monotonic is intentionally only used for ordering within this run; save wall clock too.
            game["last_played_wall"] = int(GLib.get_real_time() / 1000000)
            if game["kind"] == "custom":
                for item in self.custom_games:
                    if item.get("key") == game.get("key"): item.update(game)
                save_json(custom_games_path(), self.custom_games)
            else:
                self.settings.setdefault("last_played", {})[game["appid"]] = game["last_played_wall"]
                save_json(settings_path(), self.settings)
            self.sort_games()
            if close_after_launch:
                # Preserve the current window geometry before terminating.
                self._save_window_geometry()
                self.quit()
                return
            self.populate()
        except Exception as e:
            self.error_dialog(str(e))

    def last_played(self, game):
        if game["kind"] == "custom": return int(game.get("last_played_wall", 0))
        return int(self.settings.get("last_played", {}).get(game["appid"], 0))

    def remove_custom_game_dialog(self, game):
        """Remove a manually added Ludra entry, never the game itself."""
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Remove from Ludra")
        d.set_default_size(460, 210)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(22); box.set_margin_bottom(22)
        box.set_margin_start(22); box.set_margin_end(22)

        title = Gtk.Label(label=f'Remove “{game.get("name", "this game")}” from Ludra?', xalign=0)
        title.add_css_class("title-3")
        title.set_wrap(True)
        box.append(title)

        info = Gtk.Label(
            label="This removes only the Ludra library entry and its Ludra cover. "
                  "The game, Steam shortcut, and files on disk will not be deleted.",
            xalign=0,
        )
        info.set_wrap(True); info.add_css_class("dim-label")
        box.append(info)

        buttons = Gtk.Box(spacing=8); buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        remove = Gtk.Button(label="Remove from Ludra")
        remove.add_css_class("destructive-action")
        cancel.connect("clicked", lambda *_: d.close())

        def do_remove(_):
            key = game.get("key")
            self.custom_games = [item for item in self.custom_games if item.get("key") != key]
            save_json(custom_games_path(), self.custom_games)

            # Remove only Ludra-owned metadata/artwork for this manual entry.
            try:
                custom_cover_path(game).unlink(missing_ok=True)
            except Exception:
                pass
            hidden = self.settings.setdefault("hidden_games", [])
            if key in hidden:
                hidden.remove(key)
                save_json(settings_path(), self.settings)

            d.close()
            self.refresh()

        remove.connect("clicked", do_remove)
        buttons.append(cancel); buttons.append(remove); box.append(buttons)
        d.set_child(box); d.present()

    def hide_game(self, game):
        key = game.get("key")
        if not key:
            return
        hidden = self.settings.setdefault("hidden_games", [])
        if key not in hidden:
            hidden.append(key)
            save_json(settings_path(), self.settings)
        self._update_hidden_menu_label()
        self.populate()

    def restore_game(self, key, dialog=None):
        hidden = self.settings.setdefault("hidden_games", [])
        if key in hidden:
            hidden.remove(key)
        game = next((g for g in self.games if g.get("key") == key), None)
        if game is not None and not is_real_game(game):
            forced_visible = self.settings.setdefault("forced_visible", [])
            if key not in forced_visible:
                forced_visible.append(key)
        save_json(settings_path(), self.settings)
        self._update_hidden_menu_label()
        if dialog is not None:
            dialog.close()
            self.hidden_games_dialog()
        self.populate()

    def reset_hidden_games_dialog(self, parent):
        confirm = Gtk.Window(transient_for=parent, modal=True)
        confirm.set_title("Reset hidden list")
        confirm.set_default_size(410, 170)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20); box.set_margin_bottom(20); box.set_margin_start(20); box.set_margin_end(20)
        title = Gtk.Label(label="Unhide all games?", xalign=0)
        title.add_css_class("title-3")
        detail = Gtk.Label(
            label="This clears your hidden-games list. It does not uninstall or delete anything from Steam.",
            xalign=0
        )
        detail.set_wrap(True)
        buttons = Gtk.Box(spacing=8); buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        reset = Gtk.Button(label="Reset hidden list")
        reset.add_css_class("destructive-action")
        cancel.connect("clicked", lambda *_: confirm.close())
        def do_reset(_button):
            self.settings["hidden_games"] = []
            self.settings["forced_visible"] = []
            save_json(settings_path(), self.settings)
            self._update_hidden_menu_label()
            confirm.close()
            parent.close()
            self.populate()
        reset.connect("clicked", do_reset)
        buttons.append(cancel); buttons.append(reset)
        box.append(title); box.append(detail); box.append(buttons)
        confirm.set_child(box); confirm.present()

    def hidden_games_dialog(self):
        d = Gtk.Window(transient_for=self.window, modal=True)
        d.set_title("Manage hidden")
        d.set_default_size(500, 390)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(20); outer.set_margin_bottom(20); outer.set_margin_start(20); outer.set_margin_end(20)

        header = Gtk.Box(spacing=10)
        back = Gtk.Button(label="Close"); back.connect("clicked", lambda *_: d.close()); header.append(back)
        heading = Gtk.Label(label="Manage hidden", xalign=0)
        heading.add_css_class("title-2"); heading.set_hexpand(True)
        header.append(heading); outer.append(header)

        hidden = set(self.settings.get("hidden_games", []))
        forced_visible = set(self.settings.get("forced_visible", []))
        items = [g for g in self.games if g.get("key") in hidden or (not is_real_game(g) and g.get("key") not in forced_visible)]
        if not items:
            label = Gtk.Label(label="No hidden games or tools.", xalign=0)
            label.add_css_class("dim-label")
            outer.append(label)
        else:
            scroll = Gtk.ScrolledWindow(); scroll.set_vexpand(True)
            rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for game in sorted(items, key=lambda g: g.get("name", "").lower()):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                name = Gtk.Label(label=game.get("name", "Unknown"), xalign=0)
                name.set_hexpand(True)
                restore = Gtk.Button(label="Show")
                restore.connect("clicked", lambda _b, k=game.get("key"): self.restore_game(k, d))
                row.append(name); row.append(restore); rows.append(row)
            scroll.set_child(rows); outer.append(scroll)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        reset = Gtk.Button(label="Reset hidden list")
        reset.set_sensitive(bool(hidden))
        reset.connect("clicked", lambda *_: self.reset_hidden_games_dialog(d))
        footer.append(reset)
        spacer = Gtk.Box(); spacer.set_hexpand(True); footer.append(spacer)
        outer.append(footer)
        d.set_child(outer); d.present()

    def error_dialog(self, message):
        d = Gtk.AlertDialog(message="Ludra could not launch this game", detail=message); d.show(self.window)

    def refresh(self):
        if not hasattr(self, "status"): return
        self.status.set_text("Scanning library…")
        threading.Thread(target=self.scan_thread, daemon=True).start()

    def scan_thread(self):
        games = read_installed_games()
        custom = []
        for item in self.custom_games:
            item.setdefault("kind", "custom"); item.setdefault("last_played_wall", item.get("last_played", 0)); custom.append(item)
        games.extend(custom)
        GLib.idle_add(self.set_games, games)

    def sort_games(self):
        if self.settings.get("sort_by", "last_played") == "name":
            self.games.sort(key=lambda g: g.get("name", "").casefold())
        else:
            self.games.sort(key=lambda g: (self.last_played(g), g.get("name", "").casefold()), reverse=True)

    def set_games(self, games):
        self.games = games
        self.sort_games()
        self._update_hidden_menu_label()
        self.populate()
        return GLib.SOURCE_REMOVE

    def _on_layout_tick(self, widget, frame_clock):
        width = self.scroll.get_width()
        if width > 1 and width != self._last_viewport_width:
            self._last_viewport_width = width
            # Reflow immediately from the allocation GTK actually gave us.
            self._apply_flow_layout()
        return GLib.SOURCE_CONTINUE

    def _apply_flow_layout(self):
        self._flow_layout_timer = 0
        if not self._visible_cards:
            return GLib.SOURCE_REMOVE

        # Test109: continuous cover width and shared row-break calculation.
        # The old code reserved 220px for each column but drew 120px covers:
        # this produced large unused gaps and unexpectedly early wrapping.
        min_card_width, preferred_card_width, max_card_width = 120, 165, 210
        gap = max(8, min(32, int(self.settings.get("grid_spacing", 16))))
        viewport_width = self.scroll.get_width()
        if viewport_width <= 1:
            viewport_width = max(1, self.window.get_width() - 36)
        # Use the same inner width that GTK gives the padded gallery.
        # Retain Test109's original 8px buffer for layout rounding.
        available = max(min_card_width, viewport_width - 18 - 18 - 8)
        columns = max(1, min(len(self._visible_cards),
                             int((available + gap) // (preferred_card_width + gap))))
        # Use the actual allocated viewport to grow/shrink artwork fluidly.
        # Never request space beyond the viewport, or the scroller can impose
        # a minimum width on the main window.
        card_width = max(min_card_width, min(max_card_width,
                         int((available - gap * (columns - 1)) // columns)))
        card_height = round(card_width * 1.5)

        # Rebuilding is only needed when the number of columns changes.
        # At all other widths, update the existing cards in place to avoid
        # destroying/reparenting rows during a window resize.
        if columns != self._flow_columns or not self._gallery_rows:
            for card in self._visible_cards:
                parent = card.get_parent()
                if parent is not None:
                    parent.remove(card)
            child = self.flow.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.flow.remove(child)
                child = nxt
            self._gallery_rows = []
            for row_start in range(0, len(self._visible_cards), columns):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=gap)
                row.set_halign(Gtk.Align.CENTER)
                row.set_hexpand(False)
                for card in self._visible_cards[row_start:row_start + columns]:
                    row.append(card)
                self.flow.append(row)
                self._gallery_rows.append(row)
            self._flow_columns = columns

        # Spacing changes do not require reparenting or rebuilding rows.
        for row in self._gallery_rows:
            row.set_spacing(gap)
        self.flow.set_spacing(gap)

        for card in self._visible_cards:
            card.set_size_request(card_width, -1)
            card.card_slot.set_size_request(card_width, -1)
            card.card.set_size_request(card_width, -1)
            card.frame.set_size_request(card_width, card_height)
            card.picture.set_size_request(card_width, card_height)

        self.flow.queue_resize()
        return GLib.SOURCE_REMOVE

    def populate(self):
        if not hasattr(self, "flow"): return
        while child := self.flow.get_first_child():
            self.flow.remove(child)
        self._visible_cards = []
        self._flow_columns = 0
        self._gallery_rows = []
        self._flow_last_width = 0

        q = self.search.get_text().strip().lower() if hasattr(self, "search") else ""
        hidden = set(self.settings.get("hidden_games", []))
        forced_visible = set(self.settings.get("forced_visible", []))
        shown = [g for g in self.games if g.get("key") not in hidden and (is_real_game(g) or g.get("key") in forced_visible) and (not q or q in g["name"].lower())]
        if not shown:
            self.status.set_text("0 games")
            return

        for game in shown:
            card = GameCard(self, game)
            self._visible_cards.append(card)

        self.status.set_text(f"{len(shown)} games")
        GLib.idle_add(self._apply_flow_layout)

    def _apply_shadow_setting_css(self):
        # Restore the saved shadow immediately at startup, not only when the
        # Preferences page is visited. Reuse one provider to avoid CSS buildup.
        if not hasattr(self, "_shadow_setting_provider"):
            self._shadow_setting_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                self.window.get_display(), self._shadow_setting_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        strength = max(0.0, min(1.0, float(self.settings.get("shadow_intensity", 42)) / 100.0))
        hover = min(0.92, strength * 1.7)
        self._shadow_setting_provider.load_from_data((
            ".cover-frame { border-radius: 5.167%%; box-shadow: 0 5px 10px rgba(0,0,0,%.3f); }\n"
            ".game-button:hover .cover-frame, .game-button.hovered .cover-frame, "
            ".game-button:focus-visible .cover-frame { box-shadow: 0 10px 20px rgba(0,0,0,%.3f); }"
        ) % (strength, hover))

    def _apply_background_adjustment(self):
        self._background_adjustment_timer = 0
        self.apply_css()
        return GLib.SOURCE_REMOVE

    def _adjusted_wallpaper_path(self, source):
        """Preserve original artwork; cache brightness/contrast adjusted copies."""
        brightness = max(50, min(120, int(self.settings.get("background_brightness", 100))))
        contrast = max(75, min(125, int(self.settings.get("background_contrast", 100))))
        if brightness == 100 and contrast == 100:
            return source
        source = Path(source)
        stamp = str(source.stat().st_mtime_ns)
        digest = hashlib.sha256(f"{source}:{stamp}:{brightness}:{contrast}".encode()).hexdigest()[:16]
        cache_dir = app_data_dir() / "wallpaper-cache"
        cache_dir.mkdir(exist_ok=True)
        output = cache_dir / f"adjusted-{digest}.png"
        if output.exists():
            return output
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(source), 1920, 1200, True)
        rgba = pix if pix.get_has_alpha() else pix.add_alpha(False, 0, 0, 0)
        pixels = bytearray(rgba.get_pixels())
        b, c = brightness / 100.0, contrast / 100.0
        table = bytes(max(0, min(255, round(((v - 127.5) * c + 127.5) * b))) for v in range(256))
        # RGBA is four-byte aligned. Transform RGB in three fast slices;
        # preserve alpha and do not loop over millions of pixels in Python.
        for channel in range(3):
            pixels[channel::4] = pixels[channel::4].translate(table)
        result = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(bytes(pixels)), GdkPixbuf.Colorspace.RGB, True,
            8, rgba.get_width(), rgba.get_height(), rgba.get_rowstride())
        result.savev(str(output), "png", [], [])
        # Keep only a handful of variants as the sliders are explored.
        cached = sorted(cache_dir.glob("adjusted-*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
        for stale in cached[12:]:
            try: stale.unlink()
            except OSError: pass
        return output

    def apply_css(self):
        if hasattr(self, "bg_picture"):
            bg_files = {
                "Ludra Dawn": "background-dawn.jpg",
                "Aurora Blue": "background-aurora-blue.jpg",
                "Lavender Mist": "background-lavender-mist.jpg",
                "Rose Glow": "background-rose-glow.jpg",
                "Sage Light": "background-sage-light.jpg",
                "Twilight Glass": "background-twilight-glass.jpg",
            }
            selected_bg = self.settings.get("background", "Ludra Dawn")
            custom_bg = self.settings.get("custom_background", "")
            original_bg = (Path(custom_bg) if selected_bg == "Custom" and custom_bg and Path(custom_bg).is_file()
                           else Path("/app/share/ludra") / bg_files.get(selected_bg, "background-dawn.jpg"))
            try:
                display_bg = self._adjusted_wallpaper_path(original_bg) if selected_bg != "None" else original_bg
            except Exception as exc:
                print(f"Ludra: wallpaper adjustment failed: {exc}")
                display_bg = original_bg
            if selected_bg == "None":
                self.bg_picture.set_opacity(0.0)
            else:
                self.bg_picture.set_opacity(1.0)
                self.bg_picture.set_filename(str(display_bg))
        # Paint one continuous background on the GtkWindow CSS node. This is
        # the crucial Test37 experiment: unlike a Gtk.Picture in the content
        # area, the window node also sits behind the native titlebar child.
        if selected_bg == "None":
            # Test128: a soft, neutral, non-decorative surface instead of
            # the old nearly-black navy gradient.
            window_bg_css = "background-image: none; background-color: #303238;"
            preferences_bg_css = "background-image: none; background-color: rgba(61, 66, 75, .98);"
        else:
            bg_uri = Path(display_bg).resolve().as_uri()
            window_bg_css = (
                'background-image: url("' + bg_uri.replace('"', '\\"') + '"); '
                'background-size: cover; background-position: center; '
                'background-repeat: no-repeat; background-color: #090d14;'
            )
            preferences_bg_css = window_bg_css

        if not hasattr(self, "_ludra_style_provider"):
            self._ludra_style_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                self.window.get_display(), self._ludra_style_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        css = self._ludra_style_provider
        css.load_from_data(("""
        .background-image { opacity: 0; }
        .background-shade {
            background: linear-gradient(to bottom,
                rgba(5, 9, 16, .30) 0px,
                rgba(5, 9, 16, .18) 70px,
                rgba(5, 9, 16, .08) 145px,
                rgba(5, 9, 16, 0) 235px);
        }
        /* Test37: keep the real GTK titlebar (and therefore KWin's native
           move/resize behaviour), but visually soften it into the canvas.
           This is intentionally CSS-only: no window-mechanics code changes. */
        /* Test38 probe: remove every app-side opaque titlebar fill while
           keeping the real GTK CSD titlebar that restored KWin mechanics.
           If the black slab came from our titlebar CSS/theme ancestry, this
           exposes the GtkWindow wallpaper underneath. */
        window.ludra-main-window,
        window.ludra-main-window.background,
        window.ludra-main-window.csd {
            border: none;
            border-radius: 14px;
            box-shadow: none;
        }
        window.ludra-main-window > decoration {
            background: transparent;
            border: none;
            border-radius: 14px;
        }
        /* Test40: cosmetic-only header pass. Keep Test38/39 native CSD mechanics. */
        .ludra-window-handle,
        .ludra-window-handle:backdrop {
            background-color: transparent;
            /* Test61 Glass Otter: a translucent band that is strongest at
               Ludra's identity and degrades gently toward the window controls. */
            background-image: linear-gradient(to right,
                rgba(55, 62, 72, .50) 0%,
                rgba(48, 55, 65, .40) 38%,
                rgba(35, 43, 54, .26) 72%,
                rgba(20, 28, 39, .13) 100%);
            border: none;
            box-shadow: none;
            padding-top: 3px; padding-bottom: 3px;
        }
        .ludra-floating-header { padding: 5px 6px 5px 6px; background: transparent; }
        .ludra-window-controls { margin-left: 3px; }
        .ludra-window-button { min-width: 34px; min-height: 34px; padding: 0; border-radius: 12px; background: rgba(72,78,88,.54); background-image: none; border: 1px solid transparent; box-shadow: none; outline: none; }
        .ludra-window-button:hover { background: rgba(35,47,64,.70); }
        .ludra-identity { margin-right: 2px; }
        .ludra-gamepad { opacity: 1; }
        .ludra-brand { font-size: 23px; font-weight: 700; color: #f7f9fc; letter-spacing: .2px; }
        .ludra-header-separator { min-height: 25px; margin: 5px 2px; background: rgba(255,255,255,.20); }
        .background-choice { padding: 5px; border-radius: 10px; background: rgba(0, 0, 0, 0.28); }
        .background-choice-selected { outline: 2px solid @accent_color; outline-offset: 1px; }
        .ludra-background-controls { padding: 5px 0 0 0; }
        .ludra-background-adjustment-label { color: rgba(245, 247, 251, .88); font-size: 11px; }
        .ludra-background-adjustment-value { color: rgba(245, 247, 251, .72); font-size: 11px; }
        .ludra-background-adjustment-scale { margin: 0 0 2px 0; }
        .ludra-background-adjustment-reset { padding: 2px 8px; min-height: 22px; font-size: 11px; border-radius: 8px; background: rgba(55, 62, 76, .38); }
        .custom-background-preview { border-radius: 7px; background: alpha(@view_fg_color, .08); }
        /* Test110: Preferences now reuse Ludra's chosen wallpaper and sit
           on lighter glass panels instead of a nearly opaque dark slab. */
        window.ludra-preferences-window,
        window.ludra-preferences-window.background,
        window.ludra-preferences-window.csd {
            border: none;
            border-radius: 14px;
            box-shadow: none;
        }
        window.ludra-preferences-window > decoration {
            background: transparent;
            border: none;
            border-radius: 14px;
        }
        /* Test113: a compact transparent GTK headerbar with real Wayland
           dragging/resize controls (no hand-made window motion code). */
        headerbar.ludra-preferences-titlebar,
        headerbar.ludra-preferences-titlebar:backdrop {
            min-height: 34px;
            padding: 2px 8px;
            background-color: rgba(34,43,58,.36);
            background-image: linear-gradient(to right,
                rgba(55,62,72,.48), rgba(27,35,49,.24));
            border: none;
            box-shadow: none;
        }
        .ludra-preferences-title-gear {
            font-size: 18px;
            font-weight: 400;
            color: #f5f7fb;
        }
        .ludra-preferences-title {
            font-size: 14px;
            font-weight: 500;
            color: #f5f7fb;
        }
        headerbar.ludra-preferences-titlebar button {
            min-width: 28px;
            min-height: 28px;
            padding: 0;
            margin: 0 2px;
            border-radius: 10px;
            background: rgba(72,78,88,.48);
            border: 1px solid rgba(255,255,255,.10);
            box-shadow: none;
        }
        headerbar.ludra-preferences-titlebar button:hover {
            background: rgba(95,104,116,.65);
        }
        .ludra-preferences-content {
            background: linear-gradient(to bottom,
                rgba(8, 12, 18, .08) 0%,
                rgba(8, 12, 18, .13) 18%,
                rgba(8, 12, 18, .20) 100%);
        }
        .preferences-body {
            background: transparent;
        }
        .preferences-sidebar {
            background: rgba(18, 24, 33, .22);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 18px;
            padding: 8px;
            box-shadow: 0 6px 20px rgba(0,0,0,.08);
        }
        .preferences-stack {
            background: rgba(18, 24, 33, .18);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 20px;
            box-shadow: 0 6px 20px rgba(0,0,0,.08);
        }
        .preferences-nav-button,
        .preferences-close-button {
            min-height: 38px;
            padding: 0 14px;
            border-radius: 13px;
            outline: none;
            color: #f5f7fb;
            background: rgba(72,78,88,.36);
            border: 1px solid rgba(255,255,255,.10);
            box-shadow: 0 2px 8px rgba(0,0,0,.10);
        }
        .preferences-nav-button:hover,
        .preferences-close-button:hover {
            background: rgba(88,95,108,.46);
            border-color: rgba(255,255,255,.14);
        }
        .preferences-nav-button:checked {
            background: rgba(100,108,122,.54);
            border-color: rgba(255,255,255,.18);
        }
        .preferences-close-button { margin-top: 8px; }
        /* Test122: only Preferences action buttons get the compact treatment.
           The main window, selectors, sliders and cover grid are unchanged. */
        window.ludra-preferences-window .ludra-toolbar-control {
            min-height: 31px;
            padding: 0 11px;
            border-radius: 12px;
        }
        .preferences-entry {
            min-height: 35px;
            padding: 0 12px;
            border-radius: 15px;
            background: rgba(72,78,88,.55);
            border: 1px solid rgba(255,255,255,.14);
            box-shadow: 0 2px 8px rgba(0,0,0,.10);
            color: #f5f7fb;
        }
        .preferences-entry image {
            color: rgba(245,247,251,.82);
        }
        /* Test135: readable shortcuts on both pale and dark wallpapers. */
        .ludra-preferences-window .ludra-shortcuts-panel {
            background-color: rgba(72,78,88,.36);
            background-image: none;
            border-radius: 14px;
            padding: 15px 18px;
            box-shadow: none;
        }
        .ludra-preferences-window .ludra-shortcut-name {
            color: #f8f9fc;
        }
        .ludra-preferences-window .ludra-shortcut-key {
            color: #f2f3f8;
            font-weight: 500;
        }
        /* Test116: remove shadow/outline/edge artifacts only from unified
           Preferences selectors.  Keep GTK's checked marks and thumb sizing. */
        .ludra-about-tagline {
            font-size: 21px;
            font-weight: 700;
            color: #f9faff;
            text-shadow: 0 1px 7px rgba(80, 120, 205, .40);
        }
        .ludra-behind-label {
            color: #f4f6fa;
            font-size: 13px;
            font-weight: 500;
        }
        .ludra-behind-rule {
            min-height: 1px;
            background: rgba(235, 241, 255, 0.54);
            border-radius: 1px;
        }
        .ludra-behind-thumbnail {
            padding: 4px;
            border-radius: 13px;
            background: rgba(103, 112, 134, .34);
            border: 1px solid rgba(255,255,255,.30);
            box-shadow: 0 5px 12px rgba(0,0,0,.22);
        }
        .ludra-behind-thumbnail:hover {
            background: rgba(122, 132, 153, .44);
        }
        window.ludra-collage-viewer,
        window.ludra-collage-viewer.background,
        window.ludra-collage-viewer.csd {
            border: none;
            border-radius: 14px;
            box-shadow: none;
        }
        window.ludra-collage-viewer > decoration {
            background: transparent;
            border: none;
            border-radius: 14px;
        }
        .ludra-collage-frame {
            margin: 8px 10px 0 10px;
            padding: 5px;
            border-radius: 15px;
            background: rgba(103, 112, 134, .34);
            border: 1px solid rgba(255,255,255,.28);
            box-shadow: 0 5px 12px rgba(0,0,0,.18);
        }
        .ludra-preferences-window checkbutton > check,
        .ludra-preferences-window checkbutton > radio {
            min-width: 20px;
            min-height: 20px;
            border-radius: 999px;
            background-image: none;
            background-color: rgba(72,78,88,.52);
            border: 1px solid transparent;
            box-shadow: none;
            outline: none;
            outline-offset: 0;
        }
        .ludra-preferences-window checkbutton > check { border-radius: 6px; }
        .ludra-preferences-window checkbutton > check:checked,
        .ludra-preferences-window checkbutton > radio:checked {
            background-image: none;
            background-color: rgba(48,132,255,.95);
            border-color: transparent;
            box-shadow: none;
            outline: none;
        }
        .ludra-preferences-window checkbutton > check:hover,
        .ludra-preferences-window checkbutton > radio:hover {
            background-color: rgba(96,104,118,.56);
            border-color: transparent;
            box-shadow: none;
            outline: none;
        }
        .ludra-preferences-window scale trough {
            min-height: 6px;
            border-radius: 999px;
            background-image: none;
            background-color: rgba(72,78,88,.48);
            border: 1px solid transparent;
            box-shadow: none;
            outline: none;
        }
        .ludra-preferences-window scale highlight {
            border-radius: 999px;
            background-image: none;
            background-color: rgba(48,132,255,.96);
            border: none;
            box-shadow: none;
        }
        .ludra-preferences-window scale slider {
            min-width: 22px;
            min-height: 22px;
            border-radius: 999px;
            background-image: none;
            background-color: rgba(126,134,148,.92);
            border: 1px solid transparent;
            box-shadow: none;
            outline: none;
            outline-offset: 0;
        }
        .custom-background-plus { font-size: 34px; font-weight: 300; }
        .no-background-preview { border-radius: 7px; background: alpha(@view_fg_color, .035); }
        .no-background-mark { font-size: 30px; font-weight: 300; color: alpha(@view_fg_color, .62); }
        .app-title { font-weight: 700; font-size: 17px; }
        .status-pill { padding: 6px 12px; border-radius: 999px; background: rgba(72,78,88,.54); background-image: none; border: 1px solid transparent; outline: none; box-shadow: none; }
        .ludra-toolbar-control { min-height: 35px; padding: 0 13px; border-radius: 14px; background: rgba(72,78,88,.52); border: 1px solid rgba(255,255,255,.14); box-shadow: 0 2px 8px rgba(0,0,0,.10); }
        .ludra-search { min-height: 35px; border-radius: 15px; background: rgba(72,78,88,.55); border: 1px solid rgba(255,255,255,.14); box-shadow: 0 2px 8px rgba(0,0,0,.10); }
        .ludra-refresh-button { min-width: 35px; min-height: 35px; padding: 0; border-radius: 999px; background: rgba(72,78,88,.54); background-image: none; border: 1px solid transparent; box-shadow: none; outline: none; outline-offset: 0; }
        /* Test121: main header controls only; do not alter Preferences widgets,
           logo, separators, search width, or header vertical padding. */
        .ludra-floating-header .status-pill { padding-top: 4px; padding-bottom: 4px; }
        .ludra-floating-header .ludra-refresh-button {
            min-width: 35px; min-height: 31px;
        }
        .ludra-floating-header .ludra-main-pref-compact {
            min-height: 31px;
        }
        .ludra-floating-header .ludra-search {
            min-height: 31px;
            padding-top: 0; padding-bottom: 0;
        }
        /* Test125: only the main window command buttons shrink.
           Transparent edges avoid the Test124 one-pixel border artifacts. */
        .ludra-floating-header .ludra-window-button {
            min-width: 28px; min-height: 28px;
            padding: 0;
            border-radius: 10px;
            border: 1px solid transparent;
            box-shadow: none;
            outline: none;
        }

        /* Test126: harmonized main-header glass finish. Keep geometry fixed;
           transparent borders and no shadows prevent 1px GTK edge artifacts. */
        .ludra-floating-header .ludra-main-pref-compact,
        .ludra-floating-header .ludra-search,
        .ludra-floating-header .ludra-window-button {
            background-color: rgba(72,78,88,.54);
            background-image: none;
            border-color: transparent;
            box-shadow: none;
            outline: none;
        }
        /* Temporary 0.1.20-test2 comparison controls: deliberately tiny. */
        .ludra-onoff-pill { min-width: 36px; min-height: 18px; padding: 0 5px; border-radius: 999px; font-size: 9px; font-weight: 700; }
        headerbar { min-height: 0; }
        /* RC4 preview: softer charcoal cover context menu. Actions unchanged. */
        popover.ludra-cover-menu > contents {
            background: rgba(73, 80, 94, .97);
            color: #f5f6fa;
            border: 1px solid rgba(235, 240, 250, .20);
            border-radius: 13px;
            box-shadow: 0 8px 22px rgba(13, 17, 25, .30);
        }
        popover.ludra-cover-menu > arrow {
            background: rgba(73, 80, 94, .97);
            border-color: rgba(235, 240, 250, .20);
        }
        popover.ludra-cover-menu button.ludra-cover-menu-action {
            color: #f5f6fa;
            background: transparent;
            border: none;
            border-radius: 8px;
            padding: 6px 10px;
        }
        popover.ludra-cover-menu button.ludra-cover-menu-action:hover,
        popover.ludra-cover-menu button.ludra-cover-menu-action:focus-visible {
            background: rgba(210, 222, 240, .18);
        }
        popover.ludra-cover-menu separator {
            background: rgba(235, 240, 250, .20);
        }
        .game-button { background: transparent; border: none; padding: 0; margin: 0; min-width: 0; min-height: 0; }
        .game-card { padding: 0; margin: 0; min-width: 0; min-height: 0; }
        .cover-frame { box-shadow: 0 5px 10px rgba(0,0,0,.42); }
        .cover-frame { border-radius: 5.167%; background: transparent; }
        .cover-artwork { border-radius: 5.167%; }
        .game-button .cover-frame { min-width: 0; }
        .game-button .cover-frame picture { background: transparent; }
        .cover-hover-glow { background: transparent; border-radius: 5.167%; }
        .game-button:hover .cover-hover-glow, .game-button.hovered .cover-hover-glow { background: rgba(255,255,255,.17); }
        .game-title { color: #e9eef5; font-size: 13px; margin-left: 2px; margin-right: 2px; }
        .game-title-bg-dark { color: #ffffff; background: rgba(27,33,49,.59); border-radius: 8px; padding: 3px 6px; }
        .game-title-bg-light { color: #1f2737; background: rgba(231,233,228,.78); border-radius: 8px; padding: 3px 6px; }
        .game-title-bg-off { color: #ffffff; background: transparent; padding: 3px 6px; }
        .game-button:hover .game-title-bg-light, .game-button.hovered .game-title-bg-light { color: #131b29; }
        .game-button:hover .cover-frame, .game-button.hovered .cover-frame { box-shadow: 0 10px 20px rgba(0,0,0,.72); }
        .game-button:hover .game-title, .game-button.hovered .game-title { color: #ffffff; }
        .game-button:focus-visible .cover-frame { box-shadow: 0 10px 20px rgba(0,0,0,.72); }
        grid { background: transparent; }
        """ + "\n.ludra-main-window { " + window_bg_css + " }\n" + "\n.ludra-preferences-window { " + preferences_bg_css + " }\n" + "\n.ludra-collage-viewer { " + preferences_bg_css + " }\n"))
        # Experiment: override host GTK CSS for window corners only.
        if not hasattr(self, "_window_corners_provider"):
            self._window_corners_provider = Gtk.CssProvider()
            self._window_corners_provider.load_from_data("""
                window.ludra-main-window,
                window.ludra-preferences-window,
                window.ludra-collage-viewer {
                    border-radius: 14px;
                }
                window.ludra-main-window > decoration,
                window.ludra-preferences-window > decoration,
                window.ludra-collage-viewer > decoration {
                    border-radius: 14px;
                }
            """)
            Gtk.StyleContext.add_provider_for_display(
                self.window.get_display(),
                self._window_corners_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
            )
        self._apply_shadow_setting_css()


def main(): return Ludra().run(None)

if __name__ == "__main__": raise SystemExit(main())
