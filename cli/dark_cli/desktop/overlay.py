"""A glowing frame and ghost cursor that show while Dark controls the desktop.

Runs as its own process on Windows and reads JSON lines on stdin:
    {"window": "<handle>"}   frame that window
    {"path": [[x, y], ...]}  glide the ghost cursor to each control in turn, rippling at each
    {"scan": true}           sweep a scan line down the window as Dark looks at it
It fades out and exits when stdin closes. Every window is click-through, never takes
focus, and is excluded from screen capture, so the agent's input and screenshots are
unaffected.
"""

from __future__ import annotations

import ctypes
import json
import math
import queue
import sys
import threading
import time
from ctypes import wintypes

GREEN = (0, 255, 136)  # Dark's accent, #00ff88
FPS = 60
FADE = 0.3  # seconds
SCAN = 0.9  # seconds for one sweep

WS_POPUP = 0x80000000
# Layered, click-through, always on top, absent from the taskbar, never activated.
EX_STYLE = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 2
AC_SRC_ALPHA = 1
WDA_EXCLUDEFROMCAPTURE = 0x11
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PM_REMOVE = 1

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32")
dwmapi = ctypes.WinDLL("dwmapi")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]  # fmt: skip
user32.CreateWindowExW.restype = wintypes.HWND
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]  # fmt: skip
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindow.argtypes = user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = [
    wintypes.HWND
]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]  # fmt: skip
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# DefWindowProc must stay referenced for the life of the window class.
window_procedure = WNDPROC(lambda *message: user32.DefWindowProcW(*message))
CLASS = "DarkDesktopOverlay"


def premultiplied(alpha: float) -> bytes:
    a = max(0, min(255, round(alpha * 255)))
    red, green, blue = GREEN
    return bytes((blue * a // 255, green * a // 255, red * a // 255, a))


class Layer:
    """A click-through, always-on-top window that shows a BGRA image."""

    def __init__(self, instance):
        self.hwnd = user32.CreateWindowExW(
            EX_STYLE, CLASS, None, WS_POPUP, 0, 0, 1, 1, None, None, instance, None
        )
        user32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE)
        self.dc = gdi32.CreateCompatibleDC(None)
        self.bitmap = None
        self.size = (0, 0)
        self.shown = False

    def image(self, width: int, height: int, pixels: bytes) -> None:
        header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(
            self.dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0
        )
        ctypes.memmove(bits, pixels, len(pixels))
        gdi32.SelectObject(self.dc, bitmap)
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        self.bitmap, self.size = bitmap, (width, height)

    def show(self, x: float, y: float, alpha: float) -> None:
        if not self.bitmap:
            return
        blend = BLENDFUNCTION(0, 0, max(0, min(255, round(alpha * 255))), AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(
            self.hwnd,
            None,
            ctypes.byref(wintypes.POINT(round(x), round(y))),
            ctypes.byref(wintypes.SIZE(*self.size)),
            self.dc,
            ctypes.byref(wintypes.POINT(0, 0)),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        )
        if not self.shown:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.shown = True

    def close(self) -> None:
        user32.DestroyWindow(self.hwnd)
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        gdi32.DeleteDC(self.dc)


def glow(distance: float, thickness: float) -> float:
    return (1 - distance / thickness) ** 2.6 if distance < thickness else 0.0


def edge_images(width: int, height: int, thickness: int) -> dict[str, tuple[int, int, bytes]]:
    """Glow strips that sit outside a width x height rectangle, brightest at its edge."""
    t = thickness

    def strip(rows: int, columns: int, distance) -> bytes:
        return b"".join(
            b"".join(premultiplied(glow(distance(row, column), t)) for column in range(columns))
            for row in range(rows)
        )

    def horizontal(outward_row) -> bytes:
        # Corners fall off radially; the long middle of each row has one value.
        rows = []
        for row in range(t):
            dy = outward_row(row)
            left = b"".join(premultiplied(glow(math.hypot(t - c - 0.5, dy), t)) for c in range(t))
            right = b"".join(premultiplied(glow(math.hypot(c + 0.5, dy), t)) for c in range(t))
            rows.append(left + premultiplied(glow(dy, t)) * width + right)
        return b"".join(rows)

    return {
        "top": (width + 2 * t, t, horizontal(lambda row: t - row - 0.5)),
        "bottom": (width + 2 * t, t, horizontal(lambda row: row + 0.5)),
        "left": (t, height, strip(1, t, lambda _, c: t - c - 0.5) * height),
        "right": (t, height, strip(1, t, lambda _, c: c + 0.5) * height),
    }


def supersampled(size: int, inside, samples: int = 3) -> list[float]:
    step = 1 / samples
    offsets = [(i + 0.5) * step for i in range(samples)]
    return [
        sum(inside(x + ox, y + oy) for ox in offsets for oy in offsets) / samples**2
        for y in range(size)
        for x in range(size)
    ]


def blurred(values: list[float], size: int, radius: int) -> list[float]:
    def blur_line(line: list[float]) -> list[float]:
        return [
            sum(line[max(0, i - radius) : i + radius + 1]) / (2 * radius + 1)
            for i in range(len(line))
        ]

    rows = [blur_line(values[y * size : (y + 1) * size]) for y in range(size)]
    columns = [blur_line([rows[y][x] for y in range(size)]) for x in range(size)]
    return [columns[x][y] for y in range(size) for x in range(size)]


def cursor_image(scale: float) -> tuple[int, int, bytes, int]:
    """A green arrow pointer with a soft glow; returns size, size, pixels, tip offset."""
    unit = 1.6 * scale
    margin = round(8 * scale)
    size = round(20 * unit) + 2 * margin
    arrow = [(0, 0), (0, 17), (4.2, 13.2), (7, 19.5), (9.6, 18.4), (6.9, 12.2), (12.4, 12.2)]
    polygon = [(margin + x * unit, margin + y * unit) for x, y in arrow]

    def inside(x: float, y: float) -> bool:
        crossings = False
        for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                crossings = not crossings
        return crossings

    fill = supersampled(size, inside)
    halo = blurred(fill, size, max(2, round(4 * scale)))
    pixels = b"".join(
        premultiplied(min(1.0, f + 0.75 * h * (1 - f))) for f, h in zip(fill, halo, strict=True)
    )
    return size, size, pixels, margin


def ripple_images(scale: float, frames: int = 14) -> tuple[int, list[bytes]]:
    size = round(96 * scale)
    center = size / 2
    distances = [
        math.hypot(x + 0.5 - center, y + 0.5 - center) for y in range(size) for x in range(size)
    ]
    width = 3 * scale
    images = []
    for frame in range(frames):
        progress = frame / (frames - 1)
        radius = (6 + 34 * progress) * scale
        strength = (1 - progress) ** 1.4
        images.append(
            b"".join(
                premultiplied(strength * math.exp(-(((d - radius) / width) ** 2)))
                for d in distances
            )
        )
    return size, images


def scan_image(width: int, height: int) -> bytes:
    """A bright leading line with a fading trail above it."""
    rows = []
    for row in range(height):
        strength = 1.0 if row >= height - 2 else 0.45 * (row / (height - 1)) ** 2.5
        rows.append(premultiplied(strength) * width)
    return b"".join(rows)


def bounds(hwnd: int, margin: int) -> tuple[int, int, int, int] | None:
    """The window's visible rectangle, pulled in where a glow would leave its monitor."""
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    # The extended frame excludes the invisible resize borders of Windows 10 and 11.
    if dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    ):
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    monitor = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(monitor)):
        return rect.left, rect.top, rect.right, rect.bottom
    screen = monitor.rcMonitor
    return (
        max(rect.left, screen.left + margin),
        max(rect.top, screen.top + margin),
        min(rect.right, screen.right - margin),
        min(rect.bottom, screen.bottom - margin),
    )


def ease(progress: float) -> float:
    return 1 - (1 - min(1.0, max(0.0, progress))) ** 3


def read_commands(commands: queue.Queue, closed: threading.Event) -> None:
    for line in sys.stdin:
        try:
            commands.put(json.loads(line))
        except ValueError:
            continue
    closed.set()


def run() -> None:
    if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # per-monitor v2
        user32.SetProcessDPIAware()
    instance = kernel32.GetModuleHandleW(None)
    window_class = WNDCLASSEXW(
        cbSize=ctypes.sizeof(WNDCLASSEXW),
        lpfnWndProc=window_procedure,
        hInstance=instance,
        lpszClassName=CLASS,
    )
    user32.RegisterClassExW(ctypes.byref(window_class))
    scale = user32.GetDpiForSystem() / 96
    thickness = max(8, round(22 * scale))

    commands: queue.Queue = queue.Queue()
    closed = threading.Event()
    threading.Thread(target=read_commands, args=(commands, closed), daemon=True).start()

    edges = {name: Layer(instance) for name in ("top", "bottom", "left", "right")}
    pointer, ripple, scanner = Layer(instance), Layer(instance), Layer(instance)
    pointer_size, _, pointer_pixels, tip = cursor_image(scale)
    pointer.image(pointer_size, pointer_size, pointer_pixels)
    ripple_size, ripple_frames = ripple_images(scale)

    target = None
    framed = None  # size of the rectangle the edge images were built for
    start = time.monotonic()
    closing_at = None
    position = None
    glide = None  # (from, to, started)
    pending: list[tuple[float, float]] = []  # controls still to visit
    rippled_at = None
    ripple_point = (0.0, 0.0)
    scan_started = None
    scan_width = None
    trail = max(12, round(40 * scale))
    message = wintypes.MSG()

    while True:
        while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        now = time.monotonic()
        while not commands.empty():
            command = commands.get()
            if isinstance(command.get("window"), str) and command["window"].isdecimal():
                target = int(command["window"])
            for point in command.get("path") or []:
                if isinstance(point, list) and len(point) >= 2:
                    pending.append((float(point[0]), float(point[1])))
            if command.get("scan") is True:
                scan_started = now
        if closed.is_set() and closing_at is None:
            closing_at = now
        fade = ease((now - start) / FADE)
        if closing_at is not None:
            fade *= 1 - ease((now - closing_at) / FADE)
            if now - closing_at >= FADE:
                break
        pulse = 0.72 + 0.28 * math.sin((now - start) * 2 * math.pi * 0.7)

        rectangle = bounds(target, thickness) if target else None
        if rectangle and rectangle[2] > rectangle[0] and rectangle[3] > rectangle[1]:
            left, top, right, bottom = rectangle
            size = (right - left, bottom - top)
            if size != framed:
                for name, (w, h, pixels) in edge_images(*size, thickness).items():
                    edges[name].image(w, h, pixels)
                framed = size
            t = thickness
            places = {
                "top": (left - t, top - t),
                "bottom": (left - t, bottom),
                "left": (left - t, top),
                "right": (right, top),
            }
            for name, (x, y) in places.items():
                edges[name].show(x, y, fade * pulse)
        else:
            rectangle = None
            for layer in edges.values():
                layer.show(0, 0, 0)

        if scan_started is not None:
            progress = (now - scan_started) / SCAN
            # Without a framed window, the sweep covers the primary screen.
            left, top, right, bottom = rectangle or (
                0,
                0,
                user32.GetSystemMetrics(0),
                user32.GetSystemMetrics(1),
            )
            if progress >= 1 or right <= left:
                scanner.show(0, 0, 0)
                scan_started = None
            else:
                if right - left != scan_width:
                    scan_width = right - left
                    scanner.image(scan_width, trail, scan_image(scan_width, trail))
                travel = progress * progress * (3 - 2 * progress)
                y = top + travel * (bottom - top) - trail
                scanner.show(left, y, fade * min(1.0, (1 - progress) * 4))

        if position is None and rectangle:
            # The cursor waits in the middle of the window it controls until it has a target.
            position = ((rectangle[0] + rectangle[2]) / 2, (rectangle[1] + rectangle[3]) / 2)
        if glide is None and pending and (rippled_at is None or now - rippled_at > 0.15):
            if position is None:
                cursor = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(cursor))
                position = (float(cursor.x), float(cursor.y))
            glide = (position, pending.pop(0), now)
        if glide:
            origin, destination, started = glide
            progress = ease((now - started) / 0.35)
            position = tuple(
                o + (d - o) * progress for o, d in zip(origin, destination, strict=True)
            )
            if progress >= 1:
                glide, rippled_at, ripple_point = None, now, destination
        if position:
            pointer.show(position[0] - tip, position[1] - tip, fade)
        if rippled_at is not None:
            frame = int((now - rippled_at) * FPS)
            if frame < len(ripple_frames):
                ripple.image(ripple_size, ripple_size, ripple_frames[frame])
                ripple.show(
                    ripple_point[0] - ripple_size / 2, ripple_point[1] - ripple_size / 2, fade
                )
            else:
                ripple.show(0, 0, 0)
                rippled_at = None
        time.sleep(1 / FPS)

    for layer in (*edges.values(), pointer, ripple, scanner):
        layer.close()


if __name__ == "__main__":
    # Decoration only: any failure simply means no overlay.
    try:
        run()
    except Exception:
        sys.exit(0)
