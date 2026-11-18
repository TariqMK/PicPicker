"""Takes the README screenshots from the real app, filled with generated sample photos.

Writes:
  assets/screenshots/review.png        A folder part-way through review, with one deletion
  assets/screenshots/strip.png         The strip under the photo, with several deletions
  assets/screenshots/undo.png          Just after a delete, with Undo available (Windows only)
  assets/screenshots/order.png         The toolbar's order buttons, set to Date
  assets/screenshots/review-complete.png  The end of a folder, with the session's totals
  assets/screenshots/on-this-day.png   On This Day, showing today's date in earlier years

Sample photos are drawn by this script into a temporary folder; the app's cache and recent
folders also go there, so your own files and settings are never read or changed. Nothing
is deleted: the deleted frame on the contact strip is set directly. The window is drawn at
2x (1120 x 720 px layout, saved as 2240 x 1440 px). On a screen too small for that, it
falls back to 1x (1120 x 720 px) and says so.

The screenshots look the same on every platform: only the app's content is captured (no
title bar or window frame), the folder path is a neutral made-up one, and the Windows-only
Undo button is hidden except in undo.png. Fonts are the platform's own (Segoe UI on Windows, SF Pro on macOS).

Run from the repository root on Windows, macOS or Linux (X11), with the app's dependencies
installed and the window free to appear on screen for a few seconds:
  python assets/make_screenshots.py --version v3.1.1
--version is the release tag shown in the toolbar; it defaults to the newest local git tag.
On macOS, the app running the script needs Screen Recording permission
(System Settings > Privacy & Security > Screen Recording).
"""

import argparse
import ctypes
import math
import random
import subprocess
import sys
import tempfile
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path

import piexif
from PIL import Image, ImageDraw, ImageFilter, ImageGrab

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets' / 'screenshots'
SCALE = 2.0             # Layout pixels to screenshot pixels.
WINDOW = (1120, 720)    # Layout size of the window's content.


# ---- Sample photos ----------------------------------------------------------------------

def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def ridge(rng, width, base, roughness, steps=9):
    """A mountain ridge line by midpoint displacement."""
    points = [base + rng.uniform(-roughness, roughness), base + rng.uniform(-roughness, roughness)]
    spread = roughness
    for _ in range(steps):
        spread *= 0.55
        nxt = []
        for a, b in zip(points, points[1:]):
            nxt += [a, (a + b) / 2 + rng.uniform(-spread, spread)]
        points = nxt + [points[-1]]
    step = width / (len(points) - 1)
    return [(i * step, y) for i, y in enumerate(points)]


SCENES = [
    # sky top, sky horizon, sun colour, land near colour, has water
    ((24, 44, 92), (246, 160, 102), (255, 226, 170), (28, 30, 44), True),
    ((60, 122, 196), (178, 214, 238), (255, 252, 236), (38, 74, 56), False),
    ((18, 22, 48), (120, 74, 128), (250, 206, 214), (22, 20, 36), True),
    ((96, 150, 204), (232, 222, 196), (255, 246, 214), (86, 98, 62), False),
    ((34, 58, 96), (240, 120, 76), (255, 204, 128), (40, 26, 34), False),
    ((140, 180, 214), (230, 236, 240), (255, 255, 255), (60, 88, 104), True),
    ((44, 90, 140), (156, 206, 222), (255, 250, 230), (24, 66, 70), True),
    ((64, 40, 86), (236, 150, 120), (255, 220, 170), (40, 30, 52), False),
]


def scene(seed, size, palette):
    rng = random.Random(seed)
    w, h = size
    top, horizon, sun, near, water = palette
    image = Image.new('RGB', size)
    draw = ImageDraw.Draw(image)
    horizon_y = h * rng.uniform(0.55, 0.68)
    for y in range(h):
        draw.line([(0, y), (w, y)], fill=lerp(top, horizon, min(1, y / horizon_y) ** 1.4))

    glow = Image.new('L', size, 0)
    sx, sy, r = w * rng.uniform(0.25, 0.75), horizon_y * rng.uniform(0.45, 0.85), h * 0.06
    ImageDraw.Draw(glow).ellipse([sx - r * 3, sy - r * 3, sx + r * 3, sy + r * 3], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(r * 1.6))
    image = Image.composite(Image.new('RGB', size, sun), image, glow)
    draw = ImageDraw.Draw(image)
    draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=sun)

    layers = 4
    for i in range(layers):
        depth = i / (layers - 1)
        colour = lerp(lerp(horizon, top, 0.35), near, 0.35 + 0.65 * depth)
        base = horizon_y - h * 0.16 * (1 - depth) + (h * 0.05 if water else h * 0.12) * depth
        line = ridge(rng, w, base, h * (0.10 - 0.05 * depth))
        draw.polygon(line + [(w, h), (0, h)], fill=colour)

    if water:
        water_top = round(horizon_y + h * 0.10)
        band = image.crop((0, water_top - (h - water_top), w, water_top)).transpose(
            Image.Transpose.FLIP_TOP_BOTTOM)
        tint = Image.new('RGB', band.size, lerp(top, near, 0.5))
        reflection = Image.blend(band, tint, 0.45).filter(ImageFilter.GaussianBlur(3))
        image.paste(reflection, (0, water_top))
        # A few soft glints under the sun.
        glints = Image.new('L', size, 0)
        draw = ImageDraw.Draw(glints)
        for _ in range(28):
            y = rng.uniform(water_top + h * 0.02, h)
            x = sx + rng.gauss(0, w * 0.06) * (1 + (y - water_top) / h)
            length = rng.uniform(w * 0.01, w * 0.05)
            draw.line([(x - length, y), (x + length, y)], fill=120, width=max(2, h // 400))
        glints = glints.filter(ImageFilter.GaussianBlur(2))
        image = Image.composite(Image.new('RGB', size, lerp(sun, horizon, 0.3)), image, glints)

    grain = Image.effect_noise(size, 10).convert('RGB')
    return Image.blend(image, grain, 0.04)


def make_samples(folder: Path) -> None:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    rng = random.Random(7)
    files = []
    # Ten photos from the last two years, two of them portrait.
    for i in range(10):
        taken = today - timedelta(days=rng.randint(20, 700), minutes=rng.randint(420, 1100))
        files.append((f'IMG_{4210 + i * 3}.jpg', taken, (2400, 1600) if i not in (3, 7) else (1600, 2400)))
    # Four photos from today's date in earlier years, for On This Day.
    for years in (2, 5, 8, 11):
        taken = today.replace(year=today.year - years) + timedelta(hours=rng.randint(9, 18),
                                                                   minutes=rng.randint(0, 59))
        files.append((f'DSC_{1000 + years * 37}.jpg', taken, (2400, 1600)))
    for n, (name, taken, size) in enumerate(files):
        picture = scene(n * 11 + 3, size, SCENES[n % len(SCENES)])
        stamp = taken.strftime('%Y:%m:%d %H:%M:%S').encode()
        exif = piexif.dump({'0th': {piexif.ImageIFD.Make: b'Sample', piexif.ImageIFD.Model: b'Camera'},
                            'Exif': {piexif.ExifIFD.DateTimeOriginal: stamp}})
        picture.save(folder / name, quality=95, subsampling=0, exif=exif)


# ---- Driving the app --------------------------------------------------------------------

def newest_tag() -> str | None:
    result = subprocess.run(['git', 'tag', '--sort=-v:refname'], cwd=ROOT,
                            capture_output=True, text=True)
    tags = result.stdout.split()
    return tags[0] if tags else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', default=newest_tag(),
                        help='Release tag to show in the toolbar, for example v3.0.2.')
    args = parser.parse_args()
    if not args.version:
        sys.exit('No release tag found. Pass --version, for example --version v3.0.2.')
    if sys.platform == 'win32':
        # Work in physical pixels, so 1 window unit = 1 captured pixel.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    sys.path.insert(0, str(ROOT))
    # Show the release version, not the development one, in this process only.
    import picpicker.version
    picpicker.version.__version__ = args.version.lstrip('v')
    import picpicker.app as app_module
    from picpicker import app_icon, paths, theme, ui
    # Undo exists only on Windows; hide it so the screenshots are true on every platform.
    ui.CAN_RESTORE = False

    work = Path(tempfile.mkdtemp(prefix='picpicker-shots-'))
    samples = work / 'Holiday photos'
    samples.mkdir()
    make_samples(samples)
    app_module.runtime_paths = lambda: paths.runtime_paths(work / 'app')
    (work / 'app').mkdir()

    root = tk.Tk()
    # Captured pixels per window unit: 2 on a Retina Mac (Tk works in points), else 1.
    try:
        probe = ImageGrab.grab(bbox=(0, 0, 100, 100), all_screens=True)
    except (OSError, subprocess.CalledProcessError):
        sys.exit('Cannot capture the screen. On macOS, give the app running this script Screen '
                 'Recording permission. On Linux, run it in an X11 session.')
    ratio = probe.width / 100
    # Draw at 2x. If the 2x window doesn't fit (a small 1x screen), fall back to 1x.
    scale = SCALE
    layout_scale = scale / ratio
    margin = (40, 60)    # Room around the window: the menu bar and title bar take height.
    if any(round(v * layout_scale) + m > limit
           for v, m, limit in zip(WINDOW, margin, (root.winfo_screenwidth(), root.winfo_screenheight()))):
        scale = 1.0
        layout_scale = scale / ratio
        print(f'Note: the {SCALE:g}x window does not fit on this screen; saving at 1x instead. '
              'Retake on a high-DPI (Retina) display for sharper screenshots.')

    original_init = theme.Theme.__init__

    def fixed_scale(self, root):
        original_init(self, root)
        self.scale = layout_scale
    theme.Theme.__init__ = fixed_scale

    root._icons = [tk.PhotoImage(data=data) for data in app_icon.WINDOW]
    root.iconphoto(True, *root._icons)
    app = app_module.ImageOrganizer(root)
    # The real temporary path would show your user name; always show a neutral one instead.
    original_caption = app.update_caption

    def neutral_caption(*args):
        original_caption(*args)
        app.path_label.config(text=' Pictures/Holiday photos')
    app.update_caption = neutral_caption
    width, height = (round(v * layout_scale) for v in WINDOW)
    if width + margin[0] > root.winfo_screenwidth() or height + margin[1] > root.winfo_screenheight():
        sys.exit(f'The {width} x {height} window does not fit on this screen. '
                 'Use a larger or high-DPI display.')
    root.geometry(f"{width}x{height}+20+0")
    root.attributes('-topmost', True)
    OUT.mkdir(parents=True, exist_ok=True)
    expected = tuple(round(v * scale) for v in WINDOW)

    def capture(name, crop=None):
        """Save the window. crop=(widget, right, to_bottom) keeps only the band that widget sits in,
        up to `right` layout px across (None for full width) and down to the window's bottom edge
        when to_bottom is true."""
        root.lift()
        root.update()
        if 'Holiday photos' not in app.path_label.cget('text') and app.path_label.cget('text'):
            app.close()
            sys.exit('The folder label shows a real path. Fix the caption override before publishing.')
        x, y = root.winfo_rootx(), root.winfo_rooty()
        shot = ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()),
                              all_screens=True).convert('RGB')
        # Without screen-capture permission (macOS) the grab shows the desktop, not the app.
        bar = Image.new('RGB', (1, 1), app.theme.bar).getpixel((0, 0))
        corner = shot.getpixel((shot.width - 4, 4))
        if max(abs(a - b) for a, b in zip(corner, bar)) > 12:
            app.close()
            sys.exit('The capture does not show the app. On macOS, give the app running this '
                     'script Screen Recording permission, then run it again.')
        if shot.size != expected:
            shot = shot.resize(expected, Image.LANCZOS)
        if crop:
            widget, right, to_bottom = crop
            k = scale / layout_scale    # Window units to screenshot pixels.
            top = round((widget.winfo_rooty() - y) * k)
            bottom = shot.height if to_bottom else round((widget.winfo_rooty() - y + widget.winfo_height()) * k)
            shot = shot.crop((0, top, shot.width if right is None else round(right * scale), bottom))
        shot.save(OUT / f'{name}.png', optimize=True)
        print(f'Wrote assets/screenshots/{name}.png ({shot.width} x {shot.height} px)')

    def when_scanned(then):
        if app._scanning or not app.images:
            root.after(100, lambda: when_scanned(then))
        else:
            root.after(1200, then)

    def review():
        # Seven photos in: one deleted, the rest kept. Set directly so nothing is deleted.
        app.current_index = 6
        app.deleted_indices = {3}
        app.processed_count, app.deleted_count, app.space_saved_mb = 6, 1, 2.4
        app.show_current_image()
        root.after(1200, lambda: (capture('review'), strip()))

    def strip():
        # Further in, with a few more deletions: the strip and the bar under it.
        app.current_index = 10
        app.deleted_indices = {1, 3, 4, 8}
        app.processed_count, app.deleted_count, app.space_saved_mb = 10, 4, 9.7
        app.show_current_image()
        root.after(1200, lambda: (capture('strip', crop=(app.strip.master, None, True)), undo()))

    def undo():
        # Undo is Windows-only; show it here as it looks on Windows, just after a delete.
        undo_btn = ui.FlatButton(app.undo_btn.master, app.theme, 'Undo', None, variant='ghost',
                                 icon='undo', key='Ctrl Z', height=40)
        undo_btn.pack(side=tk.RIGHT, padx=(0, round(16 * layout_scale)))
        app.current_index = 5
        app.deleted_indices = {4}
        app.processed_count, app.deleted_count, app.space_saved_mb = 5, 1, 2.1
        app.show_current_image()
        root.after(1200, lambda: (capture('undo'), undo_btn.destroy(), order()))

    def order():
        app.processed_count, app.deleted_count, app.space_saved_mb = 0, 0, 0
        app.deleted_indices = set()
        app.set_order('date')
        def shot():
            toolbar = app.order_control.master.master
            right = (app.order_control.winfo_rootx() - root.winfo_rootx()
                     + app.order_control.winfo_width()) / layout_scale + 12
            capture('order', crop=(toolbar, right, False))
            app.set_order('name')
            when_scanned(complete)
        when_scanned(shot)

    def complete():
        # The end of the folder, with the totals for the session.
        app.processed_count, app.deleted_count, app.space_saved_mb = 14, 5, 18.6
        app.deleted_indices = {1, 3, 4, 8, 12}
        app.current_index = len(app.images)
        app.show_current_image()
        root.after(1200, lambda: (capture('review-complete'), on_this_day()))

    def on_this_day():
        app.processed_count, app.deleted_count, app.space_saved_mb = 0, 0, 0
        app.this_day_var.set(True)
        app.toggle_this_day()
        def second_photo():
            app.current_index = 1
            app.show_current_image()
            root.after(1200, lambda: (capture('on-this-day'), app.close()))
        when_scanned(second_photo)

    root.after(500, lambda: (app.open_review_folder(str(samples)), when_scanned(review)))
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
