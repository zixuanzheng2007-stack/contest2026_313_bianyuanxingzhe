#!/usr/bin/env python3
"""边缘行者 PC 控制台：COM7 遥控 + 无损 RLE RGB565 实时镜像。

依赖: pip install pyserial
推荐: pip install pillow  （直接解码 RGB565，显著降低渲染延迟）
"""
from __future__ import annotations

import queue
import os
import struct
import threading
import time
import traceback
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None  # type: ignore

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore

try:
    from PIL import Image, ImageTk

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

BAUD = 1000000
DISP_W, DISP_H = 390, 450
# PC 画布目标（LCD 390×450 的 2 倍，整数 nearest 放大，禁止双线性）
VIEW_W, VIEW_H = 780, 900
FB_MAGIC = b"\x89EWF"
RLE_MAGIC = b"\x89EWR"
FRAME_MAGICS = (FB_MAGIC, RLE_MAGIC)
MAX_FRAME_PAYLOAD = 2 * 1024 * 1024
# goldfish 模拟器风格：设备边框内嵌屏，nearest 像素块
BEZEL_SIDE = 18
BEZEL_TOP = 32
BEZEL_BOT = 14
FRAME_FILL = "#2b2b2b"
FRAME_OUTLINE = "#666"
SCREEN_BORDER = "#111"
MAX_REMOTE_UTF8 = 600
ARTIFACTS = Path(__file__).resolve().parents[1] / "VMware_share" / "artifacts"


def read_host_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if value or winreg is None:
        return value
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return ""


def normalize_remote_text(text: str, max_bytes: int = MAX_REMOTE_UTF8) -> str:
    """Make one UTF-8 console line without splitting a code point."""
    clean = text.replace("\r", " ").replace("\n", " ")
    raw = clean.encode("utf-8")
    if len(raw) <= max_bytes:
        return clean
    return raw[:max_bytes].decode("utf-8", errors="ignore")


def remote_text_command(text: str, submit: bool = False) -> str:
    verb = "@submit" if submit else "@input"
    return f"{verb} {normalize_remote_text(text)}"


def wheel_drag_end(point: tuple[int, int], delta: int,
                   distance: int = 48) -> tuple[int, int]:
    """Map a wheel notch to an LCD drag while keeping the point on-screen."""
    direction = 1 if delta > 0 else -1
    return point[0], max(0, min(DISP_H - 1, point[1] + direction * distance))


def map_canvas_to_lcd(x: int, y: int, x0: int, y0: int,
                      display_w: int, display_h: int,
                      frame_w: int, frame_h: int) -> tuple[int, int] | None:
    if min(display_w, display_h, frame_w, frame_h) <= 0:
        return None
    ix = x - x0
    iy = y - y0
    if ix < 0 or iy < 0 or ix >= display_w or iy >= display_h:
        return None
    fx = int(ix * frame_w / display_w)
    fy = int(iy * frame_h / display_h)
    lcd_x = int((fx + 0.5) * DISP_W / frame_w)
    lcd_y = int((fy + 0.5) * DISP_H / frame_h)
    return (max(0, min(DISP_W - 1, lcd_x)),
            max(0, min(DISP_H - 1, lcd_y)))


def rgb565_to_rgb(data: bytes) -> bytes:
    """RGB565 → RGB888，用位移扩位（比 255//31 更利文字边缘）。"""
    out = bytearray(len(data) // 2 * 3)
    j = 0
    for i in range(0, len(data), 2):
        if i + 1 >= len(data):
            break
        p = data[i] | (data[i + 1] << 8)
        r = (p >> 11) & 0x1F
        g = (p >> 5) & 0x3F
        b = p & 0x1F
        out[j] = (r << 3) | (r >> 2)
        out[j + 1] = (g << 2) | (g >> 4)
        out[j + 2] = (b << 3) | (b >> 2)
        j += 3
    return bytes(out[:j])


def pick_integer_zoom(w: int, h: int) -> int:
    """把源帧整数倍放大到尽量填满 VIEW_W×VIEW_H，禁止小数缩放。"""
    if w <= 0 or h <= 0:
        return 2
    zw = VIEW_W // w
    zh = VIEW_H // h
    return max(1, min(zw, zh))


def fit_mirror_size(w: int, h: int, canvas_w: int,
                    canvas_h: int) -> tuple[int, int]:
    """Fit the complete LCD inside the live canvas without cropping."""
    avail_w = max(1, canvas_w - BEZEL_SIDE * 2 - 8)
    avail_h = max(1, canvas_h - BEZEL_TOP - BEZEL_BOT - 8)
    scale = min(VIEW_W / max(1, w), VIEW_H / max(1, h),
                avail_w / max(1, w), avail_h / max(1, h))
    return max(1, int(w * scale)), max(1, int(h * scale))


def scale_rgb_nearest(rgb: bytes, w: int, h: int,
                      out_w: int, out_h: int) -> tuple[bytes, int, int]:
    """Pure nearest-neighbor resize used when Pillow is unavailable."""
    if out_w == w and out_h == h:
        return rgb, w, h
    out = bytearray(out_w * out_h * 3)
    row_in = w * 3
    for oy in range(out_h):
        sy = min(h - 1, oy * h // out_h)
        for ox in range(out_w):
            sx = min(w - 1, ox * w // out_w)
            si = sy * row_in + sx * 3
            di = (oy * out_w + ox) * 3
            out[di:di + 3] = rgb[si:si + 3]
    return bytes(out), out_w, out_h


def rgb_to_photoimage(rgb: bytes, w: int, h: int, out_w: int, out_h: int,
                      master: tk.Misc) -> tk.PhotoImage:
    """Resize with nearest sampling and create a PhotoImage."""
    if _HAS_PIL:
        im = Image.frombytes("RGB", (w, h), rgb)
        nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST", Image.NEAREST)
        if (out_w, out_h) != (w, h):
            im = im.resize((out_w, out_h), nearest)
        return ImageTk.PhotoImage(im, master=master)
    if (out_w, out_h) != (w, h):
        rgb, w, h = scale_rgb_nearest(rgb, w, h, out_w, out_h)
    ppm = f"P6\n{w} {h}\n255\n".encode("ascii") + rgb
    return tk.PhotoImage(data=ppm, format="PPM", master=master)


def rgb565_to_photoimage(data: bytes, w: int, h: int, out_w: int, out_h: int,
                         master: tk.Misc) -> tk.PhotoImage:
    """优先让 Pillow 原生解码 little-endian RGB565，避免 Python 逐像素转换。"""
    if _HAS_PIL:
        im = Image.frombytes("RGB", (w, h), data, "raw", "BGR;16")
        if (out_w, out_h) != (w, h):
            nearest = getattr(getattr(Image, "Resampling", Image),
                              "NEAREST", Image.NEAREST)
            im = im.resize((out_w, out_h), nearest)
        return ImageTk.PhotoImage(im, master=master)
    return rgb_to_photoimage(
        rgb565_to_rgb(data), w, h, out_w, out_h, master)


def decode_rle565(payload: bytes, expected_bytes: int) -> bytes:
    """解码板端 PackBits 风格 RGB565；格式错误时拒绝整帧。"""
    out = bytearray()
    pos = 0
    while pos < len(payload):
        control = payload[pos]
        pos += 1
        count = (control & 0x7F) + 1
        if control & 0x80:
            if pos + 2 > len(payload):
                raise ValueError("truncated RLE run")
            pixel = payload[pos:pos + 2]
            pos += 2
            out.extend(pixel * count)
        else:
            size = count * 2
            if pos + size > len(payload):
                raise ValueError("truncated RLE literal")
            out.extend(payload[pos:pos + size])
            pos += size
        if len(out) > expected_bytes:
            raise ValueError("RLE frame expands past dimensions")
    if len(out) != expected_bytes:
        raise ValueError(
            f"RLE size mismatch: got {len(out)}, expected {expected_bytes}")
    return bytes(out)


@dataclass(frozen=True)
class MirrorFrame:
    width: int
    height: int
    rgb565: bytes
    wire_bytes: int
    codec: str
    received_at: float


class SerialFrameParser:
    """从串口字节流分离二进制帧与文本日志。"""

    def __init__(self) -> None:
        self._buf = bytearray()

    @staticmethod
    def _magic_at(buf: bytearray, index: int) -> bytes | None:
        for magic in FRAME_MAGICS:
            if buf[index:index + len(magic)] == magic:
                return magic
        return None

    @staticmethod
    def _first_magic(buf: bytearray) -> int:
        indexes = [i for magic in FRAME_MAGICS
                   if (i := buf.find(magic)) >= 0]
        return min(indexes) if indexes else -1

    @staticmethod
    def _partial_magic_suffix(buf: bytearray) -> int:
        keep = 0
        for n in range(1, min(3, len(buf)) + 1):
            suffix = bytes(buf[-n:])
            if any(magic.startswith(suffix) for magic in FRAME_MAGICS):
                keep = n
        return keep

    def feed(self, chunk: bytes) -> tuple[list[MirrorFrame], str]:
        self._buf.extend(chunk)
        frames: list[MirrorFrame] = []
        text_parts: list[str] = []

        while True:
            idx = self._first_magic(self._buf)
            if idx < 0:
                if self._buf:
                    keep = self._partial_magic_suffix(self._buf)
                    emit = len(self._buf) - keep
                    if emit:
                        text_parts.append(
                            self._buf[:emit].decode("utf-8", errors="replace"))
                        del self._buf[:emit]
                break
            if idx > 0:
                text_parts.append(self._buf[:idx].decode("utf-8", errors="replace"))
                del self._buf[:idx]
                continue
            if len(self._buf) < 12:
                break
            magic = self._magic_at(self._buf, 0)
            if magic is None:
                del self._buf[0]
                continue
            w, h, length = struct.unpack_from("<HHI", self._buf, 4)
            if (w <= 0 or h <= 0 or w > 2048 or h > 2048 or
                    length <= 0 or length > MAX_FRAME_PAYLOAD):
                text_parts.append("[mirror] invalid frame header\n")
                del self._buf[0]
                continue
            total = 12 + length
            if len(self._buf) < total:
                break
            payload = bytes(self._buf[12:total])
            del self._buf[:total]
            expected = w * h * 2
            try:
                if magic == RLE_MAGIC:
                    rgb565 = decode_rle565(payload, expected)
                    codec = "RLE"
                elif length == expected:
                    rgb565 = payload
                    codec = "RAW"
                else:
                    raise ValueError(
                        f"raw size mismatch: got {length}, expected {expected}")
            except ValueError as exc:
                text_parts.append(f"[mirror] dropped corrupt frame: {exc}\n")
                continue
            frames.append(MirrorFrame(
                width=w,
                height=h,
                rgb565=rgb565,
                wire_bytes=length,
                codec=codec,
                received_at=time.monotonic(),
            ))
        return frames, "".join(text_parts)


class EdgeWalkerPanel:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("边缘行者 · DevKit 控制台")
        self.root.geometry("1480x1020")
        self.root.minsize(1000, 700)

        self.ser: serial.Serial | None = None
        self.rx_text_q: queue.Queue[str] = queue.Queue()
        self.rx_frame_q: queue.Queue[MirrorFrame] = queue.Queue(maxsize=2)
        self.stop_rx = threading.Event()
        self.parser = SerialFrameParser()
        self.mirror_var = tk.BooleanVar(value=True)
        self.mirror_mode = tk.StringVar(value="fast")
        self._photo: tk.PhotoImage | None = None
        self._display_w = 0
        self._display_h = 0
        self._frame_w = 0
        self._frame_h = 0
        self._img_x0 = 0
        self._img_y0 = 0
        self._mirror_fps = tk.StringVar(value="镜像: --")
        self._last_frame_t = 0.0
        self._touch_down: tuple[int, int] | None = None
        self._touch_last_send = 0.0
        self._serial_write_lock = threading.Lock()
        self._remote_sync_job: str | None = None
        self._last_remote_text: str | None = None
        self._resize_job: str | None = None
        self._latest_frame: MirrorFrame | None = None
        self._last_mirror_keepalive = 0.0

        self._build_ui()
        self.root.report_callback_exception = self._report_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_ports()
        self._place_window()
        self.root.after(25, self.drain_rx)
        self.root.after(500, self.mirror_poll)
        self.root.after(400, self._auto_connect)

    def _report_callback_exception(self, exc_type: type[BaseException],
                                   value: BaseException, tb: object) -> None:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        detail = "".join(traceback.format_exception(exc_type, value, tb))
        with (ARTIFACTS / "ew_panel_crash.log").open("a", encoding="utf-8") as fp:
            fp.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n{detail}")
        self.append_log(f"[panel] callback error: {value}\n")
        self.status.configure(text="界面异常（已记录）", foreground="#a00")

    def _place_window(self) -> None:
        """适配屏幕并置前，避免 1480×1020 超出显示器或被其它窗口挡住。"""
        self.root.update_idletasks()
        sw = max(self.root.winfo_screenwidth(), 800)
        sh = max(self.root.winfo_screenheight(), 600)
        w = min(1480, sw - 32)
        h = min(1020, sh - 48)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(1000, w), min(700, h))
        try:
            self.root.state("normal")
        except tk.TclError:
            pass
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(350, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _auto_connect(self) -> None:
        if self.ser and self.ser.is_open:
            return
        if serial is None:
            import sys

            messagebox.showwarning(
                "缺少 pyserial",
                f"当前 Python:\n{sys.executable}\n\n"
                "请对该解释器安装:\n"
                f'  "{sys.executable}" -m pip install pyserial pillow\n\n'
                "或设置 EW_PANEL_PYTHON 指向已有 pyserial 的 python.exe",
            )
            return
        port = self.port_var.get().strip() or "COM7"
        self.port_var.set(port)
        self.connect()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="串口").pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value="COM7")
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=10)
        self.port_box.pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="刷新", command=self.refresh_ports).pack(side=tk.LEFT)
        self.btn_conn = ttk.Button(top, text="连接", command=self.toggle_conn)
        self.btn_conn.pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="RTS 复位", command=self.hw_reset).pack(side=tk.LEFT)
        self.status = ttk.Label(top, text="未连接", foreground="#666")
        self.status.pack(side=tk.LEFT, padx=12)
        ttk.Label(top, textvariable=self._mirror_fps, foreground="#036").pack(side=tk.RIGHT)

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.columnconfigure(0, minsize=380, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, width=380, padding=4)
        right = ttk.Frame(body, padding=4)
        left.grid(row=0, column=0, sticky=tk.NSEW)
        right.grid(row=0, column=1, sticky=tk.NSEW)
        left.grid_propagate(False)

        nb = ttk.Notebook(left)
        nb.pack(fill=tk.BOTH, expand=True)
        self._tab_remote(nb)
        self._tab_wifi(nb)
        self._tab_agent(nb)
        self._tab_nsh(nb)
        self._tab_mirror(right)

        log_frame = ttk.LabelFrame(self.root, text="串口日志", padding=6)
        log_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.log = scrolledtext.ScrolledText(log_frame, height=4, font=("Consolas", 9))
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        pil_hint = "Pillow NEAREST" if _HAS_PIL else "内置 nearest 放大"
        ttk.Label(
            self.root,
            text=f"镜像：nearest 自适应完整显示（{pil_hint}）。单帧(HD)=390×450 全清。",
            foreground="#444",
        ).pack(pady=(0, 6))

    def _tab_remote(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="快捷遥控")
        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=2)
        for label, cmd in (
            ("预警页", "@goto warn"),
            ("WiFi 页", "@goto wifi"),
            ("Agent 页", "@goto chat"),
        ):
            ttk.Button(row, text=label, width=12,
                       command=lambda c=cmd: self.send_at(c)).pack(side=tk.LEFT, padx=2)
        row2 = ttk.Frame(f)
        row2.pack(fill=tk.X, pady=8)
        for index, (label, cmd) in enumerate((
            ("假目标 10m", "@fake 10 20"),
            ("橙色 SOFT", "@alert soft demo"),
            ("橙色 STRONG", "@alert strong demo"),
            ("红色 CRIT", "@alert crit demo"),
            ("清除 NONE", "@alert none"),
        )):
            ttk.Button(row2, text=label, width=12,
                       command=lambda c=cmd: self.send_at(c)).grid(
                           row=index // 2, column=index % 2,
                           sticky=tk.EW, padx=2, pady=2)
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)

    def _tab_wifi(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="WiFi")
        self.ssid_var = tk.StringVar()
        self.pass_var = tk.StringVar()
        ttk.Label(f, text="SSID").pack(anchor=tk.W)
        ttk.Entry(f, textvariable=self.ssid_var, width=36).pack(fill=tk.X, pady=2)
        ttk.Label(f, text="密码").pack(anchor=tk.W, pady=(6, 0))
        ttk.Entry(f, textvariable=self.pass_var, width=36, show="*").pack(fill=tk.X, pady=2)
        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)
        ttk.Button(row, text="扫描", command=lambda: self.send_at("@scan")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="连接", command=self.wifi_join).pack(side=tk.LEFT, padx=2)

    def _tab_agent(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Agent")
        self.ask_var = tk.StringVar(value="告警怎么工作？")
        ttk.Entry(f, textvariable=self.ask_var, width=40).pack(fill=tk.X, pady=4)
        ttk.Button(f, text="发送 @ask", command=self.agent_ask).pack(anchor=tk.W, pady=4)

    def _tab_nsh(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="NSH")
        self.nsh_var = tk.StringVar(value="ew fake 10 20")
        ttk.Entry(f, textvariable=self.nsh_var, width=36).pack(fill=tk.X, pady=6)
        ttk.Button(f, text="发送 NSH", command=self.send_nsh).pack(anchor=tk.W)

    def _tab_mirror(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="实时屏镜像", font=("", 10, "bold")).pack(anchor=tk.W)
        ctl = ttk.Frame(parent)
        ctl.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(
            ctl, text="开启镜像", variable=self.mirror_var,
            command=self.toggle_mirror,
        ).pack(side=tk.LEFT)
        ttk.Label(ctl, text="模式").pack(side=tk.LEFT, padx=(8, 2))
        self.mode_box = ttk.Combobox(
            ctl, textvariable=self.mirror_mode, width=8, state="readonly",
            values=("fast", "normal", "hd"),
        )
        self.mode_box.pack(side=tk.LEFT)
        self.mode_box.bind("<<ComboboxSelected>>", self.on_mirror_mode)
        ttk.Button(ctl, text="单帧(HD)", command=self.mirror_snap_hd).pack(
            side=tk.LEFT, padx=6)

        key_row = ttk.Frame(parent)
        key_row.pack(fill=tk.X, pady=(2, 4))
        ttk.Label(key_row, text="键盘透传").pack(side=tk.LEFT)
        self.remote_input_var = tk.StringVar()
        self.remote_entry = ttk.Entry(key_row, textvariable=self.remote_input_var)
        self.remote_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.remote_entry.bind("<Return>", self.on_remote_submit)
        self.remote_input_var.trace_add("write", self.on_remote_changed)
        ttk.Button(key_row, text="发送", command=self.remote_submit).pack(side=tk.LEFT)

        cw = VIEW_W + BEZEL_SIDE * 2 + 8
        ch = VIEW_H + BEZEL_TOP + BEZEL_BOT + 8
        self.canvas = tk.Canvas(
            parent, width=1, height=1, bg="#1e1e1e",
            highlightthickness=1, highlightbackground="#888",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=4)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<MouseWheel>", self.on_canvas_wheel)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self._canvas_w = 1
        self._canvas_h = 1
        self.canvas.create_text(
            cw // 2, ch // 2,
            text="等待镜像帧…\n勾选「开启镜像」或点「单帧(HD)」\n（整数 nearest，仿 goldfish 屏）",
            fill="#888", tags="placeholder",
        )

    def append_log(self, text: str) -> None:
        if not text:
            return
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def drain_rx(self) -> None:
        while True:
            try:
                chunk = self.rx_text_q.get_nowait()
            except queue.Empty:
                break
            # 镜像开时跳过 AT 逐行日志，减轻 UI 卡顿
            if self.mirror_var.get() and "[ew-at]" in chunk:
                continue
            self.append_log(chunk)
        latest: MirrorFrame | None = None
        while True:
            try:
                latest = self.rx_frame_q.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.show_frame(latest)
        self.root.after(25, self.drain_rx)

    def _draw_device_chrome(self, x0: int, y0: int, dw: int, dh: int,
                            src_w: int, src_h: int) -> None:
        """goldfish 风格：外框 + 屏区黑边 + 分辨率标签。"""
        body_x0 = x0 - BEZEL_SIDE
        body_y0 = y0 - BEZEL_TOP
        body_x1 = x0 + dw + BEZEL_SIDE
        body_y1 = y0 + dh + BEZEL_BOT
        self.canvas.create_rectangle(
            body_x0, body_y0, body_x1, body_y1,
            fill=FRAME_FILL, outline=FRAME_OUTLINE, width=2, tags="chrome",
        )
        self.canvas.create_rectangle(
            x0 - 2, y0 - 2, x0 + dw + 2, y0 + dh + 2,
            fill=SCREEN_BORDER, outline="#444", width=1, tags="chrome",
        )
        scale = min(dw / max(1, src_w), dh / max(1, src_h))
        label = f"DevKit-LCD  {src_w}×{src_h}  ×{scale:.2f} nearest"
        self.canvas.create_text(
            (body_x0 + body_x1) // 2, body_y0 + 14,
            text=label, fill="#bbb", font=("Segoe UI", 9), tags="chrome",
        )

    def show_frame(self, frame: MirrorFrame) -> None:
        self._latest_frame = frame
        self._render_frame(frame, update_stats=True)

    def on_canvas_resize(self, event: tk.Event) -> None:
        self._canvas_w = max(1, event.width)
        self._canvas_h = max(1, event.height)
        if self._latest_frame is None:
            return
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, self._render_latest_frame)

    def _render_latest_frame(self) -> None:
        self._resize_job = None
        if self._latest_frame is not None:
            self._render_frame(self._latest_frame, update_stats=False)

    def _render_frame(self, frame: MirrorFrame, update_stats: bool) -> None:
        w, h, rgb565 = frame.width, frame.height, frame.rgb565
        self._frame_w, self._frame_h = w, h
        self._canvas_w = max(1, self.canvas.winfo_width())
        self._canvas_h = max(1, self.canvas.winfo_height())
        out_w, out_h = fit_mirror_size(
            w, h, self._canvas_w, self._canvas_h)
        self._photo = rgb565_to_photoimage(
            rgb565, w, h, out_w, out_h, self.root)
        dw, dh = self._photo.width(), self._photo.height()
        self._display_w, self._display_h = dw, dh
        self.canvas.delete("all")
        self._img_x0 = max(0, (self._canvas_w - dw) // 2)
        self._img_y0 = max(0, (self._canvas_h - dh) // 2)
        self._draw_device_chrome(self._img_x0, self._img_y0, dw, dh, w, h)
        self.canvas.create_image(
            self._img_x0, self._img_y0, image=self._photo, anchor=tk.NW,
        )
        if not update_stats:
            return
        now = time.time()
        hint = ""
        if w < DISP_W - 4:
            hint = " [低分辨率流，单帧请点 HD 或重烧固件]"
        raw_bytes = max(1, w * h * 2)
        ratio = frame.wire_bytes / raw_bytes
        age_ms = (time.monotonic() - frame.received_at) * 1000.0
        wire_kib = frame.wire_bytes / 1024.0
        if self._last_frame_t > 0:
            fps = 1.0 / max(now - self._last_frame_t, 0.001)
            self._mirror_fps.set(
                f"镜像: {w}×{h} {frame.codec} {wire_kib:.1f}KiB "
                f"({ratio:.0%}) {fps:.1f}fps {age_ms:.0f}ms{hint}")
        else:
            self._mirror_fps.set(
                f"镜像: {w}×{h} {frame.codec} {wire_kib:.1f}KiB "
                f"({ratio:.0%}) {age_ms:.0f}ms{hint}")
        self._last_frame_t = now

    def mirror_snap_hd(self) -> None:
        """单帧全分辨率（新固件 snap 内强制 scale=1，不改变流模式）。"""
        self.send_at("@mirror snap")

    def mirror_poll(self) -> None:
        now = time.monotonic()
        if (self.mirror_var.get() and self.ser and self.ser.is_open
                and now - self._last_mirror_keepalive >= 2.0):
            self._last_mirror_keepalive = now
            self.send_at(self.mirror_cmd_for_mode())
        self.root.after(500, self.mirror_poll)

    def mirror_cmd_for_mode(self) -> str:
        mode = self.mirror_mode.get().strip().lower()
        if mode == "hd":
            return "@mirror hd"
        if mode == "normal":
            return "@mirror normal"
        return "@mirror fast"

    def on_mirror_mode(self, _event: object | None = None) -> None:
        if self.mirror_var.get():
            self.send_at(self.mirror_cmd_for_mode())

    def toggle_mirror(self) -> None:
        if self.mirror_var.get():
            self.send_at(self.mirror_cmd_for_mode())
        else:
            self.send_at("@mirror off")

    def refresh_ports(self) -> None:
        if serial is None:
            return
        ports = [p.device for p in list_ports.comports()]
        if "COM7" not in ports:
            ports = ["COM7"] + ports
        self.port_box["values"] = ports

    def toggle_conn(self) -> None:
        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self) -> None:
        if serial is None:
            import sys

            messagebox.showerror(
                "缺少 pyserial",
                f'"{sys.executable}" -m pip install pyserial pillow',
            )
            return
        port = self.port_var.get().strip()
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.02)
            self.ser.dtr = False
            self.ser.rts = False
        except Exception as e:
            messagebox.showerror("连接失败", str(e))
            return
        self.parser = SerialFrameParser()
        self.stop_rx.clear()
        threading.Thread(target=self._reader, daemon=True).start()
        self.btn_conn.configure(text="断开")
        self.status.configure(text=f"已连接 {port}", foreground="#060")
        self.append_log(f"\n=== 已连接 {port} ===\n")
        if self.mirror_var.get():
            self.send_at(self.mirror_cmd_for_mode())
        self.root.after(900, self.provision_mimo_config)

    def provision_mimo_config(self) -> None:
        key = read_host_secret("MIMO_API_KEY")
        if not (key.startswith("tp-") and len(key) < 160
                and not any(ch.isspace() for ch in key)):
            self.append_log("[panel] MiMo config not provisioned: MIMO_API_KEY unavailable\n")
            return
        self.send_at("@mimo-set " + key)
        self.append_log("[panel] MiMo config provision requested (key redacted)\n")

    def disconnect(self) -> None:
        if self.ser and self.ser.is_open and self.mirror_var.get():
            try:
                self.send_at("@mirror off")
            except Exception:
                pass
        self.stop_rx.set()
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        self.btn_conn.configure(text="连接")
        self.status.configure(text="未连接", foreground="#666")

    def _reader(self) -> None:
        assert self.ser is not None
        while not self.stop_rx.is_set():
            try:
                n = self.ser.in_waiting
                if n:
                    chunk = self.ser.read(n)
                    frames, text = self.parser.feed(chunk)
                    if text:
                        self.rx_text_q.put(text)
                    for fr in frames:
                        try:
                            self.rx_frame_q.put_nowait(fr)
                        except queue.Full:
                            try:
                                self.rx_frame_q.get_nowait()
                            except queue.Empty:
                                pass
                            self.rx_frame_q.put_nowait(fr)
                else:
                    time.sleep(0.008)
            except Exception:
                self.rx_text_q.put("[panel] serial reader stopped\n")
                break

    def _write_line(self, line: str) -> None:
        if not self.ser or not self.ser.is_open:
            messagebox.showwarning("未连接", "请先连接 COM7")
            return
        payload = (line.rstrip("\r\n") + "\r\n").encode("utf-8")
        try:
            with self._serial_write_lock:
                self.ser.write(payload)
                self.ser.flush()
        except Exception as exc:
            self.append_log(f"[panel] serial write failed: {exc}\n")
            self.status.configure(text="串口写入失败", foreground="#a00")
            return
        if line.startswith("@join "):
            shown = "@join ***"
        elif line.startswith("@mimo-set "):
            shown = "@mimo-set ***"
        elif line.startswith("@input ") or line.startswith("@submit "):
            shown = f"{line.split(' ', 1)[0]} <UTF-8 {len(payload) - 2} bytes>"
        else:
            shown = line
        self.append_log(f">>> {shown}\n")

    def send_at(self, cmd: str) -> None:
        if not cmd.startswith("@"):
            cmd = "@" + cmd
        self._write_line(cmd)

    def send_nsh(self) -> None:
        self._write_line(self.nsh_var.get().strip())

    def hw_reset(self) -> None:
        if not self.ser or not self.ser.is_open:
            return
        self.ser.setRTS(True)
        time.sleep(0.12)
        self.ser.setRTS(False)
        self.append_log(">>> [RTS reset]\n")

    def wifi_join(self) -> None:
        ssid = self.ssid_var.get().strip()
        pwd = self.pass_var.get()
        if not ssid:
            messagebox.showwarning("SSID", "请填写热点名")
            return
        if " " in ssid or " " in pwd:
            self.send_at(f'@join "{ssid}" "{pwd}"')
        else:
            self.send_at(f"@join {ssid} {pwd}")

    def agent_ask(self) -> None:
        q = self.ask_var.get().strip()
        if q:
            self.send_at(f"@ask {q}")

    def on_remote_changed(self, *_args: object) -> None:
        if self._remote_sync_job is not None:
            self.root.after_cancel(self._remote_sync_job)
        self._remote_sync_job = self.root.after(160, self.remote_sync)

    def remote_sync(self) -> None:
        self._remote_sync_job = None
        text = normalize_remote_text(self.remote_input_var.get())
        if self.ser and self.ser.is_open and text != self._last_remote_text:
            self._last_remote_text = text
            self.send_at(remote_text_command(text))

    def remote_submit(self) -> None:
        if self._remote_sync_job is not None:
            self.root.after_cancel(self._remote_sync_job)
            self._remote_sync_job = None
        text = normalize_remote_text(self.remote_input_var.get())
        self._last_remote_text = text
        self.send_at(remote_text_command(text, submit=True))

    def on_remote_submit(self, _event: object | None = None) -> str:
        self.remote_submit()
        return "break"

    def _canvas_to_lcd(self, x: int, y: int) -> tuple[int, int] | None:
        return map_canvas_to_lcd(
            x, y, self._img_x0, self._img_y0,
            self._display_w, self._display_h,
            self._frame_w, self._frame_h)

    def on_canvas_press(self, event: tk.Event) -> None:
        point = self._canvas_to_lcd(event.x, event.y)
        if point is None:
            return
        self._touch_down = point
        self._touch_last_send = time.monotonic()
        self.send_at(f"@touch down {point[0]} {point[1]}")
        self.remote_entry.focus_set()

    def on_canvas_drag(self, event: tk.Event) -> None:
        if self._touch_down is None:
            return
        point = self._canvas_to_lcd(event.x, event.y)
        if point is None:
            return
        now = time.monotonic()
        if now - self._touch_last_send >= 0.10:
            self._touch_last_send = now
            self.send_at(f"@touch move {point[0]} {point[1]}")

    def on_canvas_release(self, event: tk.Event) -> None:
        if self._touch_down is None:
            return
        point = self._canvas_to_lcd(event.x, event.y) or self._touch_down
        self.send_at(f"@touch up {point[0]} {point[1]}")
        self._touch_down = None

    def on_canvas_wheel(self, event: tk.Event) -> str:
        point = self._canvas_to_lcd(event.x, event.y)
        if point is None or event.delta == 0:
            return "break"
        end = wheel_drag_end(point, event.delta)
        self.send_at(f"@touch down {point[0]} {point[1]}")
        self.send_at(f"@touch move {end[0]} {end[1]}")
        self.send_at(f"@touch up {end[0]} {end[1]}")
        return "break"

    def on_close(self) -> None:
        self.disconnect()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    EdgeWalkerPanel().run()


if __name__ == "__main__":
    main()
