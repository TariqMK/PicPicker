"""End-to-end check of PicPicker: scan, name order, Subfolders, Keep, Delete, Undo (Windows), On This Day and
date order, on made-up sample photos.

It opens the real PicPicker window from source and drives it the way the buttons do, then checks each step's
effect on disk, not only the app's state. It only touches the files it makes in the work folder, and it uses a
temporary data folder, so the real cache and recent folders are never read or changed.
Needs the project's own packages (pip install -e .), nothing else. Standard library for everything it adds.

Usage:
  python scripts/check_e2e.py [--work <new empty folder>]
  Leave out --work to use a new temporary folder.

Note: on macOS and Linux, Delete sends one sample file (IMG_2.png, a 4 x 4 px grey square) to the system Trash.
The app has no undo there, so that file stays in the Trash.
"""
# Template from the tariq-project-standards skill. PicPicker has no local web server, so this drives the
# Tk window in-process instead of calling an HTTP API.
import argparse, hashlib, os, shutil, struct, sys, tempfile, time, zlib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --- Fill in for this app ----------------------------------------------------------------------------
APP_NAME = 'PicPicker'
# Made-up sample photos: relative path -> file date (PNG has no EXIF, so the app uses the modified date).
SAMPLES = {
    'IMG_1.png': datetime(2019, 3, 15, 10, 0),
    'IMG_2.png': datetime(2020, 7, 1, 9, 0),
    'IMG_10.png': datetime(2021, 3, 15, 18, 30),
    'sub/IMG_3.png': datetime(2018, 1, 20, 12, 0),
}
# -----------------------------------------------------------------------------------------------------

failures = []


def check(name, ok, detail=''):
    """Print PASS or FAIL for one step and remember failures."""
    print(('PASS ' if ok else 'FAIL ') + name + (f' -- {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(name)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def make_work_folder(path):
    """Use a new temporary folder, or the given one only if it's new or empty, so real files are never touched."""
    if path is None:
        return Path(tempfile.mkdtemp(prefix='check_e2e_'))
    work = Path(path)
    if work.exists() and any(work.iterdir()):
        sys.exit(f'Work folder must be new or empty: {work}')
    work.mkdir(parents=True, exist_ok=True)
    return work


def write_png(path, shade):
    """Write a 4 x 4 px grey PNG with the standard library only."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + bytes([shade, shade, shade]) * 4 for _ in range(4))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('--work', help='New or empty work folder; default is a new temporary folder')
args = parser.parse_args()

work = make_work_folder(args.work)
photos = work / 'photos'
data_root = work / 'app-data'
data_root.mkdir()
for i, (name, date) in enumerate(SAMPLES.items()):
    write_png(photos / name, 60 + i * 40)
    os.utime(photos / name, (date.timestamp(), date.timestamp()))
hashes = {name: sha(photos / name) for name in SAMPLES}
print(f'Work folder: {work}')

# --- App checks --------------------------------------------------------------------------------------
import tkinter as tk
import picpicker.app as app_module
from picpicker.paths import runtime_paths
from picpicker.recycle_bin import CAN_RESTORE
from picpicker.version import __version__

# Keep the app's cache and recent folders in the work folder, away from the real data folder.
app_module.runtime_paths = lambda: runtime_paths(project_root=data_root)

# A dialog would wait for a click that never comes. Record it as a failure instead.
from tkinter import messagebox
dialogs = []
for kind in ('showerror', 'showwarning', 'showinfo', 'askyesno', 'askokcancel'):
    setattr(messagebox, kind, lambda title, message='', _kind=kind, **_: dialogs.append(f'{_kind}: {title}: {message}'))

root = tk.Tk()
app = app_module.ImageOrganizer(root)


def pump(seconds=0.3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def wait_for_scan(timeout=30):
    end = time.monotonic() + timeout
    pump(0.1)
    while app._scanning and time.monotonic() < end:
        pump(0.05)
    pump(0.3)
    return not app._scanning


def names():
    return [p.relative_to(photos).as_posix() for p in app.images]


def unchanged(skip=()):
    return all(sha(photos / n) == h for n, h in hashes.items() if n not in skip)


check('Window title shows the version', root.title() == f'{APP_NAME} v{__version__}', root.title())
check('Data folder is the temporary one', Path(app.db_path).is_relative_to(data_root), app.db_path)

app.open_review_folder(str(photos))
check('Scan finishes', wait_for_scan())
check('Name order is natural, folder by folder', names() == ['IMG_1.png', 'IMG_2.png', 'IMG_10.png', 'sub/IMG_3.png'],
      names())
check('Folder is remembered in recent folders', str(photos) in app.recent_folders.folders, app.recent_folders.folders)

app.subdirs_var.set(False)
app.toggle_subdirs()
app.load_images(str(photos))
wait_for_scan()
check('Subfolders off leaves out sub/', names() == ['IMG_1.png', 'IMG_2.png', 'IMG_10.png'], names())

app.keep_image()
pump()
check('Keep moves to the next file', app.current_index == 1 and app.images[1].name == 'IMG_2.png', app.current_index)
check('Keep changes no file', unchanged())

app.delete_image()
pump()
check('Delete removes the file from the folder', not (photos / 'IMG_2.png').exists())
check('Delete moves to the next file', app.current_index == 2, app.current_index)
check('Delete leaves the other files unchanged', unchanged(skip={'IMG_2.png'}))

if CAN_RESTORE:
    app.undo_delete()
    pump()
    restored = photos / 'IMG_2.png'
    check('Undo restores the original bytes', restored.exists() and sha(restored) == hashes['IMG_2.png'])
    check('Undo returns to the restored file', app.current_index == 1, app.current_index)
else:
    check('Undo is off on this system (restore from Trash)', not app.undo_btn.enabled)

app.subdirs_var.set(True)
app.toggle_subdirs()
app.this_day_var.set(True)
app.toggle_this_day()
wait_for_scan()
app.set_viewing_day(3, 15)
app.load_images(str(photos))
wait_for_scan()
check('On This Day 15 Mar shows both years, oldest first', names() == ['IMG_1.png', 'IMG_10.png'], names())

app.this_day_var.set(False)
app.toggle_this_day()
wait_for_scan()
app.set_order('date')
wait_for_scan()
expected = sorted((n for n in SAMPLES if (photos / n).exists()), key=lambda n: SAMPLES[n])
check('Date order is oldest first', names() == expected, names())

check('No sample file changed', unchanged(skip={'IMG_2.png'}))
check('No error dialogs', not dialogs, ' | '.join(dialogs))
app.close()
# -----------------------------------------------------------------------------------------------------

shutil.rmtree(work, ignore_errors=True)
print(f'RESULT: {"FAIL" if failures else "PASS"} ({len(failures)} failed)')
sys.exit(1 if failures else 0)
