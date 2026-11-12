#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""svg2png.py: turn an SVG whose size is given in mm into a PNG, with headless Edge or Chrome. Standard library only.

    python svg2png.py drawing.svg                       drawing.png beside it, 300 dpi, transparent background
    python svg2png.py drawing.svg out.png --dpi 400
    python svg2png.py drawing.svg --background "#F5F4EF"        the page colour instead of transparency
    python svg2png.py drawing.svg part.png --crop 0,206,204,252   only that rectangle of the drawing (mm)

The PNG is the drawing at dpi pixels per inch and says so in its pHYs chunk, so a program that honours the
resolution (KiCad's image import does) places it at the drawing's size in mm with a scale of 1. 300 dpi is
11.8 px per mm: the 2.6 mm text of an architecture diagram is 31 px tall and stays sharp on an A3 print.

The browser is looked for in BROWSER (a path), then in the usual places for Edge and Chrome. Nothing is
downloaded: the browser opens a small local HTML page that shows the SVG at the pixel size and screenshots it.
"""
import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

BROWSERS = [
    os.environ.get('BROWSER', ''),
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
]
ON_PATH = ['msedge', 'google-chrome', 'chromium', 'chromium-browser', 'chrome']


def find_browser():
    for path in BROWSERS:
        if path and os.path.isfile(path):
            return path
    for name in ON_PATH:
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError('no Edge or Chrome found; set BROWSER to the executable')


def svg_size_mm(svg_path):
    with open(svg_path, encoding='utf-8') as f:
        head = f.read(4000)
    m = re.search(r'<svg[^>]*\swidth="([0-9.]+)mm"[^>]*\sheight="([0-9.]+)mm"', head)
    if not m:
        raise ValueError('%s: the <svg> element needs width and height in mm' % svg_path)
    return float(m.group(1)), float(m.group(2))


def _chunks(data):
    at = 8
    while at < len(data):
        length, kind = struct.unpack_from('>L4s', data, at)
        yield kind, data[at + 8: at + 8 + length], at, at + 12 + length
        at += 12 + length


def png_info(path):
    """(width, height, colour type, first pixel) of a PNG. The first pixel needs no unfiltering."""
    with open(path, 'rb') as f:
        data = f.read()
    width = height = ctype = None
    idat = zlib.decompressobj()
    first = b''
    for kind, body, _a, _b in _chunks(data):
        if kind == b'IHDR':
            width, height, _depth, ctype = struct.unpack_from('>LLBB', body)
        elif kind == b'IDAT' and len(first) < 5:
            first += idat.decompress(body, 64)
    return width, height, ctype, tuple(bytearray(first[1:5]))


def set_dpi(path, dpi):
    """Write the resolution into the PNG (a pHYs chunk after IHDR), replacing one that is there."""
    with open(path, 'rb') as f:
        data = f.read()
    per_metre = int(round(dpi / 0.0254))
    body = struct.pack('>LLB', per_metre, per_metre, 1)
    phys = struct.pack('>L', len(body)) + b'pHYs' + body + struct.pack('>L', zlib.crc32(b'pHYs' + body) & 0xFFFFFFFF)
    out = [data[:8]]
    for kind, _body, a, b in _chunks(data):
        if kind == b'pHYs':
            continue
        out.append(data[a:b])
        if kind == b'IHDR':
            out.append(phys)
    with open(path, 'wb') as f:
        f.write(b''.join(out))


def convert(svg_path, png_path=None, dpi=300, background=None, crop=None, browser=None, quiet=False):
    """Render svg_path to png_path. crop is (x0, y0, x1, y1) in mm of the drawing. Returns (width, height) in px."""
    svg_path = os.path.abspath(svg_path)
    png_path = os.path.abspath(png_path or os.path.splitext(svg_path)[0] + '.png')
    browser = browser or find_browser()
    wmm, hmm = svg_size_mm(svg_path)
    scale = dpi / 25.4
    full_w, full_h = int(round(wmm * scale)), int(round(hmm * scale))
    if crop:
        x0, y0 = int(round(crop[0] * scale)), int(round(crop[1] * scale))
        out_w, out_h = int(round(crop[2] * scale)) - x0, int(round(crop[3] * scale)) - y0
    else:
        x0 = y0 = 0
        out_w, out_h = full_w, full_h
    work = tempfile.mkdtemp(prefix='svg2png_')
    try:
        shot = os.path.join(work, 'shot.png')
        page = os.path.join(work, 'page.html')
        with open(page, 'w', encoding='utf-8') as f:
            f.write('<!doctype html><html><head><meta charset="utf-8"><style>'
                    'html,body{margin:0;padding:0;overflow:hidden;background:%s}'
                    'img{position:absolute;left:%dpx;top:%dpx;width:%dpx;height:%dpx}'
                    '</style></head><body><img src="%s"></body></html>'
                    % (background or 'transparent', -x0, -y0, full_w, full_h,
                       'file:///' + svg_path.replace(os.sep, '/').lstrip('/')))
        cmd = [browser, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
               '--no-default-browser-check', '--disable-extensions', '--force-device-scale-factor=1',
               '--user-data-dir=' + os.path.join(work, 'profile'),
               '--default-background-color=' + ('00000000' if not background else 'FFFFFFFF'),
               '--window-size=%d,%d' % (out_w, out_h), '--screenshot=' + shot,
               'file:///' + page.replace(os.sep, '/').lstrip('/')]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.time() + 60          # the launcher can return before the screenshot is on disk
        size = -1
        while time.time() < deadline:
            if os.path.isfile(shot):
                now = os.path.getsize(shot)
                if now > 0 and now == size:
                    break
                size = now
            time.sleep(0.5)
        if not os.path.isfile(shot) or os.path.getsize(shot) == 0:
            raise RuntimeError('the browser wrote no screenshot: ' + ' '.join(cmd))
        shutil.copyfile(shot, png_path)
    finally:
        for _try in range(10):               # the browser may still hold its profile for a moment
            shutil.rmtree(work, ignore_errors=True)
            if not os.path.isdir(work):
                break
            time.sleep(0.5)
    set_dpi(png_path, dpi)
    width, height, ctype, first = png_info(png_path)
    if (width, height) != (out_w, out_h):
        raise RuntimeError('%s is %dx%d px, expected %dx%d' % (png_path, width, height, out_w, out_h))
    if not quiet:
        print('%s: %d x %d px at %d dpi (%.1f x %.1f mm), %s, %.0f kB'
              % (png_path, width, height, dpi, width / scale, height / scale,
                 'background ' + background if background else
                 ('transparent' if ctype == 6 and first[3] == 0 else 'colour type %d, first pixel %r' % (ctype, first)),
                 os.path.getsize(png_path) / 1024.0))
    return width, height


def main(argv=None):
    ap = argparse.ArgumentParser(description='SVG (sized in mm) to PNG through headless Edge or Chrome.')
    ap.add_argument('svg')
    ap.add_argument('png', nargs='?')
    ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--background', default=None, help='a CSS colour; default transparent')
    ap.add_argument('--crop', default=None, help='x0,y0,x1,y1 in mm of the drawing')
    ap.add_argument('--browser', default=None)
    args = ap.parse_args(argv)
    crop = tuple(float(v) for v in args.crop.split(',')) if args.crop else None
    convert(args.svg, args.png, args.dpi, args.background, crop, args.browser)
    return 0


if __name__ == '__main__':
    sys.exit(main())
