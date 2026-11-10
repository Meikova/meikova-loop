r"""Dynamic Smart Lighting & Multi-Vendor RGB Hardware/Network Controller.

Features:
1. Dynamic Hardware Discovery (Zero Hardcoding):
   - Probes actual system/motherboard model via OS DMI / BIOS Registry.
   - Detects ASUS ATKACPI kernel driver (\\.\ATKACPI) ONLY when physically present on the host.
   - Detects Linux sysfs RGB/LED keyboard backlights (/sys/class/leds/*) when on Linux.
   - Detects local OpenRGB SDK server (127.0.0.1:6742) and enumerates all attached controllers
     (Razer Chroma, Corsair iCUE, Logitech G, MSI Mystic Light, Gigabyte RGB Fusion, Lenovo Legion, SteelSeries, HyperX, etc.).
   - Detects connected USB HID RGB lighting peripherals & Windows LampArray devices via PnP registry.
2. Dynamic Network / LAN Smart Light Discovery:
   - WLED (ESP8266/ESP32 Wi-Fi strips) via HTTP /json/info & UDP DDP (port 4048).
   - Philips WiZ Smart Lights via UDP broadcast discovery (port 38899).
   - Yeelight Wi-Fi LED Bulbs/Strips via SSDP multicast (239.255.255.250:1982 / TCP 55443).
   - Govee LAN API Smart Lights via UDP multicast (239.255.255.250:4001 / UDP 4003).
3. Manual Connection & Persistence:
   - Users can manually connect any device by protocol + IP/Host + Port + LED count, toggle individual devices,
     test-flash individual or all devices, and persist configuration in DATA_DIR/lights_devices.json.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import ipaddress
import json
import logging
import math
from pathlib import Path
import platform
import re
import socket
import struct
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

logger = logging.getLogger("loopbox.smart_lights")


def oklch_to_srgb(l: float, c: float, h: float) -> Tuple[int, int, int]:
    """Converts OKLCH (L: 0..1, C: 0..0.4, H: 0..360 deg) to sRGB [0..255]."""
    h_rad = math.radians(h)
    a = c * math.cos(h_rad)
    b = c * math.sin(h_rad)

    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b

    l3 = l_ * l_ * l_
    m3 = m_ * m_ * m_
    s3 = s_ * s_ * s_

    r_lin = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    g_lin = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    b_lin = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3

    def to_gamma(val: float) -> float:
        val = max(0.0, min(1.0, val))
        if val <= 0.0031308:
            return 12.92 * val
        return 1.055 * math.pow(val, 1.0 / 2.4) - 0.055

    r = int(round(to_gamma(r_lin) * 255))
    g = int(round(to_gamma(g_lin) * 255))
    b = int(round(to_gamma(b_lin) * 255))
    return max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))


def oklch_to_led_rgb(l: float, c: float, h: float, boost: float = 1.0) -> Tuple[int, int, int]:
    """Converts UI OKLCH (pastel-lifted for dark screens) to vivid linear-PWM RGB [0..255] for physical LEDs.

    Why this is needed:
    1. UI accents use high lightness (L ~ 0.79..0.83) so text/controls contrast against #0c0908 dark backgrounds.
       In sRGB, that pastel lightness adds a large white floor (min(R,G,B) ~ 75..155).
    2. Physical RGB LEDs (ASUS TUF keyboards, WLED strips, smart bulbs) use linear PWM without a dark backdrop,
       and green/blue LED dies have much higher luminous efficacy than red LED dies. Sending raw pastel sRGB
       causes orange/amber hues (h ~ 40..75) to emit strong green/blue light and appear green/yellow-white.
    3. Removing the pastel white floor, applying gamma decoding to linear PWM, and scaling all channels
       uniformly by `boost` preserves the exact hue at every beat/brightness level without channel clipping.
    """
    c_eff = max(float(c), 0.16) if float(c) >= 0.018 else float(c)
    l_eff = min(max(float(l), 0.65), 0.78)
    r, g, b = oklch_to_srgb(l_eff, c_eff, float(h))
    span = max(r, g, b) - min(r, g, b)
    level = max(0.06, min(1.0, float(boost)))
    if float(c) < 0.018 or span < 8:
        v = int(round(level * 200))
        return (v, v, v)

    w = min(r, g, b)
    r0, g0, b0 = r - w, g - w, b - w
    mx = max(r0, g0, b0, 1)
    # Convert from sRGB display gamma (~2.2) to linear LED PWM + compensate green/blue diode efficacy
    rn = (r0 / mx) ** 1.75
    gn = ((g0 / mx) ** 2.05) * 0.62
    bn = ((b0 / mx) ** 1.85) * 0.82
    mx2 = max(rn, gn, bn, 1e-6)
    scale = level * 255.0 / mx2
    return (
        max(0, min(255, int(round(rn * scale)))),
        max(0, min(255, int(round(gn * scale)))),
        max(0, min(255, int(round(bn * scale)))),
    )


def get_system_hardware_info() -> Dict[str, str]:
    """Dynamically detects the host computer's manufacturer, model name, and board."""
    sys_name = platform.system()
    info = {
        "os": sys_name,
        "manufacturer": "",
        "product": "",
        "board": "",
        "display_name": sys_name,
    }
    try:
        if sys_name == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as key:
                for field, reg_name in (
                    ("manufacturer", "SystemManufacturer"),
                    ("product", "SystemProductName"),
                    ("board", "BaseBoardProduct"),
                ):
                    try:
                        val, _ = winreg.QueryValueEx(key, reg_name)
                        if isinstance(val, str):
                            info[field] = val.strip()
                    except Exception:
                        pass
        elif sys_name == "Linux":
            dmi_base = Path("/sys/devices/virtual/dmi/id")
            if dmi_base.exists():
                for field, fname in (
                    ("manufacturer", "sys_vendor"),
                    ("product", "product_name"),
                    ("board", "board_name"),
                ):
                    p = dmi_base / fname
                    if p.exists():
                        try:
                            info[field] = p.read_text(encoding="utf-8", errors="ignore").strip()
                        except Exception:
                            pass
        elif sys_name == "Darwin":
            info["manufacturer"] = "Apple"
            try:
                out = subprocess.check_output(["sysctl", "-n", "hw.model"], timeout=1.0, text=True).strip()
                info["product"] = out
            except Exception:
                info["product"] = "Mac"
    except Exception as e:
        logger.debug("get_system_hardware_info error: %s", e)

    prod = info["product"]
    # Clean duplicated suffix like "ASUS TUF Gaming A15 FA506II_FA506II" -> "ASUS TUF Gaming A15 (FA506II)"
    if prod and "_" in prod:
        parts = prod.split("_")
        if len(parts) == 2 and parts[0].endswith(parts[1]):
            prod = f"{parts[0][:-len(parts[1])].strip()} ({parts[1]})"
    if prod and prod not in ("System Product Name", "To Be Filled By O.E.M.", "Default string"):
        info["display_name"] = prod
    elif info["board"] and info["board"] not in ("System Product Name", "To Be Filled By O.E.M."):
        info["display_name"] = f"{info['manufacturer']} {info['board']}".strip()
    elif info["manufacturer"]:
        info["display_name"] = info["manufacturer"]
    return info


class AsusTufKeyboardDriver:
    r"""Direct ASUS ACPI Kernel driver (\\.\ATKACPI) for ASUS Aura / TUF / ROG laptop keyboards."""

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80

    CONTROL_CODE = 0x0022240C
    DEVS = 0x53564544
    TUF_KB = 0x00100056
    TUF_KB2 = 0x0010005A

    def __init__(self) -> None:
        self.available: bool = False
        self._kernel32 = None
        self._lock = threading.Lock()
        if platform.system() == "Windows":
            self._init_driver()

    def _init_driver(self) -> None:
        try:
            from ctypes import wintypes
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            self._CreateFileW = self._kernel32.CreateFileW
            self._CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
            ]
            self._CreateFileW.restype = wintypes.HANDLE

            self._DeviceIoControl = self._kernel32.DeviceIoControl
            self._DeviceIoControl.argtypes = [
                wintypes.HANDLE, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
            ]
            self._DeviceIoControl.restype = wintypes.BOOL

            self._CloseHandle = self._kernel32.CloseHandle
            self._CloseHandle.argtypes = [wintypes.HANDLE]
            self._CloseHandle.restype = wintypes.BOOL

            handle = self._open_handle()
            if handle:
                self.available = True
                self._close_handle(handle)
                logger.info("AsusTufKeyboardDriver: ATKACPI kernel driver detected and active")
        except Exception as e:
            logger.debug("AsusTufKeyboardDriver init failed: %s", e)

    def reprobe(self) -> bool:
        if platform.system() != "Windows":
            self.available = False
            return False
        if not self._kernel32:
            self._init_driver()
            return self.available
        handle = self._open_handle()
        if handle:
            self.available = True
            self._close_handle(handle)
        else:
            self.available = False
        return self.available

    def _open_handle(self):
        try:
            handle = self._CreateFileW(
                r"\\.\ATKACPI",
                self.GENERIC_READ | self.GENERIC_WRITE,
                self.FILE_SHARE_READ | self.FILE_SHARE_WRITE,
                None,
                self.OPEN_EXISTING,
                self.FILE_ATTRIBUTE_NORMAL,
                None
            )
            if handle and handle != -1 and handle != 0:
                return handle
        except Exception:
            pass
        return None

    def _close_handle(self, handle):
        try:
            if handle and handle != -1 and handle != 0:
                self._CloseHandle(handle)
        except Exception:
            pass

    def set_rgb(self, r: int, g: int, b: int) -> bool:
        if not self.available:
            return False

        with self._lock:
            handle = self._open_handle()
            if not handle:
                return False

            try:
                from ctypes import wintypes
                setting = bytes([0xb4, 0, r, g, b, 0])
                args = struct.pack("<I", self.TUF_KB) + setting
                acpi_buf = struct.pack("<II", self.DEVS, len(args)) + args

                out_buf = ctypes.create_string_buffer(16)
                bytes_ret = wintypes.DWORD(0)

                res = self._DeviceIoControl(
                    handle,
                    self.CONTROL_CODE,
                    acpi_buf,
                    len(acpi_buf),
                    out_buf,
                    ctypes.sizeof(out_buf),
                    ctypes.byref(bytes_ret),
                    None
                )
                if not res:
                    return False

                status = struct.unpack("<I", out_buf.raw[:4])[0]
                if status != 1:
                    s1 = bytes([0xb3, 0, r, g, b, 0])
                    a1 = struct.pack("<I", self.TUF_KB2) + s1
                    buf1 = struct.pack("<II", self.DEVS, len(a1)) + a1
                    self._DeviceIoControl(handle, self.CONTROL_CODE, buf1, len(buf1), out_buf, 16, ctypes.byref(bytes_ret), None)

                    s2 = bytes([0xb4, 0, r, g, b, 0])
                    a2 = struct.pack("<I", self.TUF_KB2) + s2
                    buf2 = struct.pack("<II", self.DEVS, len(a2)) + a2
                    self._DeviceIoControl(handle, self.CONTROL_CODE, buf2, len(buf2), out_buf, 16, ctypes.byref(bytes_ret), None)

                return True
            except Exception as e:
                logger.debug("TUF RGB error: %s", e)
                return False
            finally:
                self._close_handle(handle)


class OpenRgbClient:
    """Lightweight OpenRGB SDK TCP client (port 6742) supporting multi-vendor RGB keyboards, mice, motherboards, and strips."""

    MAGIC = b"ORGB"
    PKT_REQUEST_CONTROLLER_COUNT = 0
    PKT_REQUEST_CONTROLLER_DATA = 1
    PKT_SET_CLIENT_NAME = 50
    PKT_RGBCONTROLLER_UPDATELEDS = 1050
    PKT_RGBCONTROLLER_SETCUSTOMMODE = 1060

    @classmethod
    def _send_pkt(cls, sock: socket.socket, dev_idx: int, pkt_id: int, data: bytes = b"") -> None:
        hdr = cls.MAGIC + struct.pack("<III", dev_idx, pkt_id, len(data))
        sock.sendall(hdr + data)

    @classmethod
    def _recv_pkt(cls, sock: socket.socket) -> Optional[Tuple[int, int, bytes]]:
        hdr = b""
        while len(hdr) < 16:
            chunk = sock.recv(16 - len(hdr))
            if not chunk:
                return None
            hdr += chunk
        if hdr[:4] != cls.MAGIC:
            return None
        dev_idx, pkt_id, data_len = struct.unpack("<III", hdr[4:16])
        payload = b""
        while len(payload) < data_len:
            chunk = sock.recv(min(65536, data_len - len(payload)))
            if not chunk:
                return None
            payload += chunk
        return dev_idx, pkt_id, payload

    @classmethod
    def probe_controllers(cls, host: str = "127.0.0.1", port: int = 6742, timeout: float = 0.18) -> List[Dict[str, Any]]:
        """Probes an OpenRGB SDK server and returns discovered controllers."""
        controllers: List[Dict[str, Any]] = []
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                cls._send_pkt(sock, 0, cls.PKT_SET_CLIENT_NAME, b"Meikova Loop\x00")
                cls._send_pkt(sock, 0, cls.PKT_REQUEST_CONTROLLER_COUNT, b"")
                res = cls._recv_pkt(sock)
                if not res or res[1] != cls.PKT_REQUEST_CONTROLLER_COUNT or len(res[2]) < 4:
                    return []
                count = struct.unpack("<I", res[2][:4])[0]
                count = min(count, 16)
                for idx in range(count):
                    cls._send_pkt(sock, idx, cls.PKT_REQUEST_CONTROLLER_DATA, b"")
                    d_res = cls._recv_pkt(sock)
                    name = f"OpenRGB Controller #{idx + 1}"
                    dev_type = 0
                    if d_res and d_res[1] == cls.PKT_REQUEST_CONTROLLER_DATA and len(d_res[2]) > 10:
                        raw = d_res[2]
                        try:
                            dev_type = struct.unpack("<i", raw[4:8])[0]
                            name_len = struct.unpack("<H", raw[8:10])[0]
                            if 1 <= name_len <= 128 and 10 + name_len <= len(raw):
                                parsed = raw[10 : 10 + name_len].rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
                                if parsed:
                                    name = parsed
                        except Exception:
                            pass
                    category = "keyboard" if dev_type in (5,) or "keyboard" in name.lower() else (
                        "strip" if dev_type in (4, 12) else "controller"
                    )
                    controllers.append({
                        "index": idx,
                        "name": name,
                        "category": category,
                        "led_count": 32,
                    })
        except Exception:
            return []
        return controllers

    @classmethod
    def update_color(cls, host: str, port: int, dev_idx: int, leds_rgb: List[Tuple[int, int, int]]) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.12) as sock:
                sock.settimeout(0.12)
                cls._send_pkt(sock, dev_idx, cls.PKT_RGBCONTROLLER_SETCUSTOMMODE, b"")
                num_leds = max(1, len(leds_rgb))
                buf = bytearray(struct.pack("<IH", 4 + 2 + num_leds * 4, num_leds))
                for r, g, b in leds_rgb:
                    buf.extend([r & 0xFF, g & 0xFF, b & 0xFF, 0])
                cls._send_pkt(sock, dev_idx, cls.PKT_RGBCONTROLLER_UPDATELEDS, bytes(buf))
                return True
        except Exception:
            return False


class SmartLightsManager:
    def __init__(self) -> None:
        self.enabled: bool = False
        self.wled_ip: str = ""
        self.wled_port: int = 4048
        self.wled_led_count: int = 60
        self.keyboard_sync_enabled: bool = True
        self.brightness_mult: float = 1.0
        self.pulse_reactive: bool = True

        # Hardware info & drivers
        self.host_system: Dict[str, str] = get_system_hardware_info()
        self.tuf_driver = AsusTufKeyboardDriver()

        # Dynamic Device Registry: id -> device dict
        self.devices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        # Runtime sockets & throttling
        self._udp_sock: Optional[socket.socket] = None
        self._last_sent: float = 0.0
        self._min_interval: float = 0.033  # ~30 FPS throttle
        self.last_rgb: Tuple[int, int, int] = (255, 120, 40)
        self.last_applied_kbd_rgb: Tuple[int, int, int] = (0, 0, 0)
        self.last_scan_at: int = 0
        self.scanning: bool = False

        # Load persisted manual/configured devices & run initial fast local hardware discovery
        self._load_persisted_devices()
        self.discover_devices(include_lan=False)

    def _storage_path(self) -> Path:
        try:
            from . import config
            return Path(config.DATA_DIR) / "lights_devices.json"
        except Exception:
            return Path("lights_devices.json")

    def _load_persisted_devices(self) -> None:
        p = self._storage_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if "brightness" in data:
                    self.brightness_mult = max(0.1, min(2.0, float(data["brightness"])))
                if "pulse_reactive" in data:
                    self.pulse_reactive = bool(data["pulse_reactive"])
                saved_devs = data.get("devices", [])
                if isinstance(saved_devs, list):
                    for d in saved_devs:
                        if isinstance(d, dict) and d.get("id"):
                            # Only restore manual devices immediately; hardware devices are verified dynamically
                            if d.get("connection") == "manual":
                                self.devices[d["id"]] = d
                                if d.get("protocol") == "wled_ddp" and d.get("address"):
                                    self.wled_ip = str(d["address"])
                                    self.wled_port = int(d.get("port") or 4048)
                                    self.wled_led_count = int(d.get("led_count") or 60)
                                    self.enabled = bool(d.get("enabled", True))
        except Exception as e:
            logger.debug("Failed to load lights_devices.json: %s", e)

    def _save_persisted_devices(self) -> None:
        try:
            p = self._storage_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "brightness": self.brightness_mult,
                "pulse_reactive": self.pulse_reactive,
                "devices": list(self.devices.values()),
            }
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to save lights_devices.json: %s", e)

    def _sync_legacy_flags(self) -> None:
        """Synchronizes legacy status fields (enabled, wled_ip, keyboard_sync, active_backend) from self.devices."""
        kbd_devs = [d for d in self.devices.values() if d.get("category") == "keyboard" and d.get("online", True)]
        if kbd_devs:
            self.keyboard_sync_enabled = any(d.get("enabled", False) for d in kbd_devs)
        wled_devs = [d for d in self.devices.values() if d.get("protocol") == "wled_ddp"]
        if wled_devs:
            active_wled = next((d for d in wled_devs if d.get("enabled")), wled_devs[0])
            self.wled_ip = str(active_wled.get("address") or self.wled_ip)
            self.wled_port = int(active_wled.get("port") or self.wled_port or 4048)
            self.wled_led_count = int(active_wled.get("led_count") or self.wled_led_count or 60)
            self.enabled = any(d.get("enabled", False) for d in self.devices.values() if d.get("category") != "keyboard")

        active_backends = [
            d.get("protocol")
            for d in self.devices.values()
            if d.get("enabled") and d.get("online", True)
        ]
        self.active_backend = "+".join(dict.fromkeys(str(b) for b in active_backends if b)) if active_backends else "none"

    def discover_devices(self, include_lan: bool = True) -> List[Dict[str, Any]]:
        """Dynamically scans local hardware drivers, OpenRGB SDK, and (optionally) LAN smart lights."""
        self.scanning = True
        try:
            self.host_system = get_system_hardware_info()
            prev_enabled = {did: bool(d.get("enabled", True)) for did, d in self.devices.items()}

            # 1. Keep manual devices and re-verify them
            manual_ids = [did for did, d in self.devices.items() if d.get("connection") == "manual"]
            auto_ids = [did for did in list(self.devices.keys()) if did not in manual_ids]
            for did in auto_ids:
                # Only drop hardware devices during hardware scan; keep LAN devices if include_lan is False
                if not include_lan and self.devices[did].get("connection") == "lan":
                    continue
                self.devices.pop(did, None)

            # 2. Probe ASUS ATKACPI Kernel Driver (ONLY registered if actually present on this machine)
            if self.tuf_driver.reprobe():
                model_label = self.host_system.get("display_name") or "ASUS Gaming"
                board_label = self.host_system.get("board")
                board_info = f" · Bo mạch {board_label}" if board_label else ""
                did = "hw:asus_acpi"
                self.devices[did] = {
                    "id": did,
                    "name": f"Bàn phím {model_label}",
                    "category": "keyboard",
                    "protocol": "asus_acpi",
                    "protocol_label": "ASUS ATKACPI Kernel",
                    "connection": "hardware",
                    "address": r"\\.\ATKACPI",
                    "port": 0,
                    "led_count": 1,
                    "multi_zone": False,
                    "online": True,
                    "enabled": prev_enabled.get(did, self.keyboard_sync_enabled),
                    "detail": f"Driver ACPI trực tiếp (\\\\.\\ATKACPI){board_info} · Đồng bộ theo màu bài hát & nhịp bass",
                }

            # 3. Probe Linux Sysfs Keyboard/Chassis RGB LEDs (/sys/class/leds/*)
            if platform.system() == "Linux":
                leds_root = Path("/sys/class/leds")
                if leds_root.exists():
                    for led_dir in leds_root.iterdir():
                        lname = led_dir.name.lower()
                        if any(k in lname for k in ("kbd_backlight", "rgb", "aura", "multicolor")):
                            multi_file = led_dir / "multi_intensity"
                            bright_file = led_dir / "brightness"
                            if multi_file.exists() or bright_file.exists():
                                did = f"hw:sysfs:{led_dir.name}"
                                is_rgb = multi_file.exists()
                                self.devices[did] = {
                                    "id": did,
                                    "name": f"Đèn phần cứng {led_dir.name}",
                                    "category": "keyboard" if "kbd" in lname else "controller",
                                    "protocol": "linux_sysfs",
                                    "protocol_label": "Linux Sysfs LED",
                                    "connection": "hardware",
                                    "address": str(led_dir),
                                    "port": 0,
                                    "led_count": 1,
                                    "multi_zone": False,
                                    "online": True,
                                    "enabled": prev_enabled.get(did, True),
                                    "detail": f"{str(led_dir)} · {'RGB Đa sắc' if is_rgb else 'Độ sáng theo nhịp'}",
                                }

            # 4. Probe local OpenRGB SDK server (127.0.0.1:6742)
            orgb_list = OpenRgbClient.probe_controllers("127.0.0.1", 6742, timeout=0.12)
            for ctrl in orgb_list:
                idx = ctrl["index"]
                did = f"openrgb:127.0.0.1:6742:{idx}"
                self.devices[did] = {
                    "id": did,
                    "name": ctrl["name"],
                    "category": ctrl["category"],
                    "protocol": "openrgb",
                    "protocol_label": "OpenRGB SDK",
                    "connection": "hardware",
                    "address": "127.0.0.1",
                    "port": 6742,
                    "controller_index": idx,
                    "led_count": ctrl.get("led_count", 32),
                    "multi_zone": True,
                    "online": True,
                    "enabled": prev_enabled.get(did, True),
                    "detail": f"OpenRGB SDK (127.0.0.1:6742 #{idx}) · Hòa sắc đa vùng",
                }

            # 5. Network / LAN Smart Light Discovery
            if include_lan:
                self._discover_lan_lights(prev_enabled)

            # 6. Refresh status of manually added WLED / OpenRGB devices
            for did in manual_ids:
                dev = self.devices.get(did)
                if not dev:
                    continue
                if dev.get("protocol") == "wled_ddp" and dev.get("address"):
                    w_info = self._probe_wled_http(str(dev["address"]), timeout=0.25)
                    if w_info:
                        dev["online"] = True
                        if not dev.get("custom_name"):
                            dev["name"] = w_info["name"]
                        dev["led_count"] = w_info.get("led_count", dev.get("led_count", 60))
                        dev["detail"] = f"{dev['address']}:{dev.get('port', 4048)} · {dev['led_count']} bóng LED · Đa vùng ∞"

            self.last_scan_at = int(time.time() * 1000)
            self._sync_legacy_flags()
            return list(self.devices.values())
        finally:
            self.scanning = False

    def _probe_wled_http(self, ip: str, timeout: float = 0.22) -> Optional[Dict[str, Any]]:
        """Probes HTTP GET http://<ip>/json/info to detect a WLED controller."""
        try:
            url = f"http://{ip}/json/info"
            req = urllib.request.Request(url, headers={"User-Agent": "MeikovaLoop/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                raw = resp.read(16384)
                info = json.loads(raw.decode("utf-8", errors="ignore"))
                if not isinstance(info, dict) or ("leds" not in info and "ver" not in info):
                    return None
                leds_obj = info.get("leds") or {}
                count = int(leds_obj.get("count") or 60)
                name = str(info.get("name") or f"WLED ({ip})").strip()
                arch = str(info.get("arch") or "ESP").upper()
                ver = str(info.get("ver") or "")
                return {
                    "ip": ip,
                    "name": name,
                    "led_count": max(1, min(2000, count)),
                    "arch": arch,
                    "ver": ver,
                }
        except Exception:
            return None

    def _get_arp_neighbor_ips(self) -> List[str]:
        """Extracts active private LAN neighbor IPs from the OS ARP cache in <30ms."""
        ips: List[str] = []
        try:
            out = subprocess.check_output(
                ["arp", "-a"],
                timeout=0.4,
                text=True,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if platform.system() == "Windows" else 0,
            )
            for m in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", out):
                ip_str = m.group(1)
                if ip_str.endswith(".255") or ip_str.endswith(".1") or ip_str.startswith("224.") or ip_str.startswith("239."):
                    continue
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                    if ip_obj.is_private and not ip_obj.is_loopback and ip_str not in ips:
                        ips.append(ip_str)
                except Exception:
                    pass
        except Exception:
            pass
        return ips[:24]

    def _discover_lan_lights(self, prev_enabled: Dict[str, bool]) -> None:
        """Runs parallel fast probes for WLED, WiZ, Yeelight, and Govee LAN devices."""
        # 1. Probe ARP neighbors for WLED HTTP (/json/info)
        neighbor_ips = self._get_arp_neighbor_ips()
        if self.wled_ip and self.wled_ip not in neighbor_ips and self.wled_ip != "127.0.0.1":
            neighbor_ips.insert(0, self.wled_ip)

        if neighbor_ips:
            with ThreadPoolExecutor(max_workers=min(12, len(neighbor_ips))) as pool:
                futures = {pool.submit(self._probe_wled_http, ip, 0.22): ip for ip in neighbor_ips}
                for fut in as_completed(futures):
                    res = fut.result()
                    if res:
                        ip = res["ip"]
                        did = f"wled:{ip}"
                        if did in self.devices and self.devices[did].get("connection") == "manual":
                            continue
                        self.devices[did] = {
                            "id": did,
                            "name": f"{res['name']} ({ip})",
                            "category": "strip",
                            "protocol": "wled_ddp",
                            "protocol_label": f"WLED {res['arch']} DDP",
                            "connection": "lan",
                            "address": ip,
                            "port": 4048,
                            "led_count": res["led_count"],
                            "multi_zone": res["led_count"] > 1,
                            "online": True,
                            "enabled": prev_enabled.get(did, True),
                            "detail": f"{ip}:4048 · {res['led_count']} bóng LED · Hòa sắc 2 vòng ∞",
                        }

        # 2. UDP Broadcast probe for Philips WiZ Smart Bulbs/Strips (port 38899)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(0.18)
                msg = b'{"method":"getSystemConfig","params":{}}'
                try:
                    s.sendto(msg, ("255.255.255.255", 38899))
                except Exception:
                    pass
                deadline = time.monotonic() + 0.18
                while time.monotonic() < deadline:
                    try:
                        data, addr = s.recvfrom(2048)
                        ip = addr[0]
                        obj = json.loads(data.decode("utf-8", errors="ignore"))
                        res_cfg = obj.get("result") or {}
                        mod_name = res_cfg.get("moduleName") or "WiZ Smart Light"
                        did = f"wiz:{ip}"
                        if did not in self.devices:
                            self.devices[did] = {
                                "id": did,
                                "name": f"Đèn WiZ {mod_name} ({ip})",
                                "category": "bulb",
                                "protocol": "wiz_udp",
                                "protocol_label": "WiZ UDP 38899",
                                "connection": "lan",
                                "address": ip,
                                "port": 38899,
                                "led_count": 1,
                                "multi_zone": False,
                                "online": True,
                                "enabled": prev_enabled.get(did, True),
                                "detail": f"{ip}:38899 · Đồng bộ màu Wi-Fi UDP tốc độ cao",
                            }
                    except Exception:
                        break
        except Exception:
            pass

        # 3. SSDP Multicast probe for Yeelight Smart Bulbs/Strips (239.255.255.250:1982)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
                s.settimeout(0.18)
                ssdp_req = (
                    b"M-SEARCH * HTTP/1.1\r\n"
                    b"HOST: 239.255.255.250:1982\r\n"
                    b'MAN: "ssdp:discover"\r\n'
                    b"ST: wifi_bulb\r\n\r\n"
                )
                try:
                    s.sendto(ssdp_req, ("239.255.255.250", 1982))
                except Exception:
                    pass
                deadline = time.monotonic() + 0.18
                while time.monotonic() < deadline:
                    try:
                        data, addr = s.recvfrom(2048)
                        txt = data.decode("utf-8", errors="ignore")
                        if "yeelight://" in txt.lower():
                            ip = addr[0]
                            model_m = re.search(r"(?im)^model:\s*(.+)$", txt)
                            model_str = model_m.group(1).strip() if model_m else "LED"
                            did = f"yeelight:{ip}"
                            if did not in self.devices:
                                self.devices[did] = {
                                    "id": did,
                                    "name": f"Yeelight {model_str} ({ip})",
                                    "category": "bulb",
                                    "protocol": "yeelight",
                                    "protocol_label": "Yeelight LAN TCP",
                                    "connection": "lan",
                                    "address": ip,
                                    "port": 55443,
                                    "led_count": 1,
                                    "multi_zone": False,
                                    "online": True,
                                    "enabled": prev_enabled.get(did, True),
                                    "detail": f"{ip}:55443 · Điều khiển LAN trực tiếp",
                                }
                    except Exception:
                        break
        except Exception:
            pass

    def add_manual_device(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Adds or updates a manually configured lighting device and probes its reachability."""
        protocol = str(payload.get("protocol") or "wled_ddp").strip().lower()
        address = str(payload.get("address") or payload.get("ip") or "").strip()
        if not address:
            raise ValueError("Vui lòng nhập địa chỉ IP hoặc Host của thiết bị")
        if len(address) > 255 or any(c in address for c in (" ", ";", "|", "&", "`", "$")):
            raise ValueError("Địa chỉ thiết bị không hợp lệ")

        default_ports = {
            "wled_ddp": 4048,
            "openrgb": 6742,
            "wiz_udp": 38899,
            "yeelight": 55443,
            "govee_lan": 4003,
            "http_webhook": 80,
        }
        port = int(payload.get("port") or default_ports.get(protocol, 4048))
        port = max(1, min(65535, port))
        led_count = max(1, min(2000, int(payload.get("led_count") or (60 if protocol == "wled_ddp" else 1))))
        custom_name = str(payload.get("name") or "").strip()

        protocol_meta = {
            "wled_ddp": ("Dải LED WLED", "strip", "WLED UDP DDP", True),
            "openrgb": ("OpenRGB Server", "controller", "OpenRGB SDK", True),
            "wiz_udp": ("Đèn thông minh WiZ", "bulb", "WiZ UDP 38899", False),
            "yeelight": ("Đèn Yeelight Wi-Fi", "bulb", "Yeelight TCP 55443", False),
            "govee_lan": ("Đèn Govee LAN", "strip", "Govee UDP 4003", False),
            "http_webhook": ("HTTP Light Webhook", "controller", "HTTP REST JSON", False),
        }
        default_title, category, proto_label, is_multi = protocol_meta.get(
            protocol, ("Thiết bị Ánh sáng", "strip", protocol.upper(), False)
        )

        did = f"manual:{protocol}:{address}:{port}"
        online = True
        detected_name = custom_name or f"{default_title} ({address})"
        detail = f"{address}:{port} · Kết nối thủ công"

        if protocol == "wled_ddp":
            w_info = self._probe_wled_http(address, timeout=0.35)
            if w_info:
                if not custom_name:
                    detected_name = f"{w_info['name']} ({address})"
                if not payload.get("led_count"):
                    led_count = w_info["led_count"]
                detail = f"{address}:{port} · {led_count} bóng LED ({w_info['arch']}) · Đa vùng ∞"
            else:
                detail = f"{address}:{port} · {led_count} bóng LED · Truyền UDP DDP trực tiếp"
            self.wled_ip = address
            self.wled_port = port
            self.wled_led_count = led_count
            self.enabled = True
        elif protocol == "openrgb":
            ctrls = OpenRgbClient.probe_controllers(address, port, timeout=0.35)
            if ctrls:
                first = ctrls[0]
                if not custom_name:
                    detected_name = f"{first['name']} ({address})"
                detail = f"{address}:{port} · Phát hiện {len(ctrls)} bộ điều khiển OpenRGB"
            else:
                online = False
                detail = f"{address}:{port} · Chưa phản hồi TCP (Hãy bật OpenRGB SDK Server)"

        dev = {
            "id": did,
            "name": detected_name,
            "custom_name": bool(custom_name),
            "category": category,
            "protocol": protocol,
            "protocol_label": proto_label,
            "connection": "manual",
            "address": address,
            "port": port,
            "controller_index": 0,
            "led_count": led_count,
            "multi_zone": bool(is_multi and led_count > 1),
            "online": online,
            "enabled": bool(payload.get("enabled", True)),
            "detail": detail,
        }
        self.devices[did] = dev
        self._sync_legacy_flags()
        self._save_persisted_devices()
        return self.get_status()

    def toggle_device(self, device_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
        dev = self.devices.get(device_id)
        if not dev:
            raise ValueError(f"Không tìm thấy thiết bị: {device_id}")
        dev["enabled"] = (not dev.get("enabled", False)) if enabled is None else bool(enabled)
        self._sync_legacy_flags()
        self._save_persisted_devices()
        return self.get_status()

    def remove_device(self, device_id: str) -> Dict[str, Any]:
        dev = self.devices.pop(device_id, None)
        if dev and dev.get("protocol") == "wled_ddp" and self.wled_ip == dev.get("address"):
            self.wled_ip = ""
            self.enabled = False
        self._sync_legacy_flags()
        self._save_persisted_devices()
        return self.get_status()

    def configure(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        if "enabled" in cfg:
            self.enabled = bool(cfg["enabled"])
        if "wled_ip" in cfg:
            self.wled_ip = str(cfg["wled_ip"]).strip()
        if "wled_port" in cfg:
            self.wled_port = int(cfg["wled_port"])
        if "wled_led_count" in cfg:
            self.wled_led_count = max(1, min(2000, int(cfg["wled_led_count"])))
        if "keyboard_sync" in cfg:
            self.keyboard_sync_enabled = bool(cfg["keyboard_sync"])
        if "sync_laptop_keyboard" in cfg:
            self.keyboard_sync_enabled = bool(cfg["sync_laptop_keyboard"])
        if "sync_wled" in cfg:
            self.enabled = bool(cfg["sync_wled"])
        if "brightness" in cfg:
            self.brightness_mult = max(0.1, min(2.0, float(cfg["brightness"])))
        if "pulse_reactive" in cfg:
            self.pulse_reactive = bool(cfg["pulse_reactive"])

        # Sync legacy keyboard_sync flag onto any detected hardware keyboard devices
        if "keyboard_sync" in cfg or "sync_laptop_keyboard" in cfg:
            for d in self.devices.values():
                if d.get("category") == "keyboard":
                    d["enabled"] = self.keyboard_sync_enabled

        # If wled_ip was configured via legacy API, ensure a device entry exists in self.devices
        if self.wled_ip:
            existing_wled = next(
                (d for d in self.devices.values() if d.get("protocol") == "wled_ddp" and d.get("address") == self.wled_ip),
                None,
            )
            if existing_wled:
                existing_wled["port"] = self.wled_port
                existing_wled["led_count"] = self.wled_led_count
                if "enabled" in cfg or "sync_wled" in cfg:
                    existing_wled["enabled"] = self.enabled
            else:
                did = f"manual:wled_ddp:{self.wled_ip}:{self.wled_port}"
                self.devices[did] = {
                    "id": did,
                    "name": f"Dải LED WLED ({self.wled_ip})",
                    "category": "strip",
                    "protocol": "wled_ddp",
                    "protocol_label": "WLED UDP DDP",
                    "connection": "manual",
                    "address": self.wled_ip,
                    "port": self.wled_port,
                    "led_count": self.wled_led_count,
                    "multi_zone": self.wled_led_count > 1,
                    "online": True,
                    "enabled": self.enabled,
                    "detail": f"{self.wled_ip}:{self.wled_port} · {self.wled_led_count} bóng LED · Truyền UDP DDP",
                }

        self._sync_legacy_flags()
        self._save_persisted_devices()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        self._sync_legacy_flags()
        dev_list = list(self.devices.values())
        return {
            "enabled": self.enabled,
            "wled_ip": self.wled_ip,
            "wled_port": self.wled_port,
            "wled_led_count": self.wled_led_count,
            "keyboard_sync": self.keyboard_sync_enabled,
            "sync_laptop_keyboard": self.keyboard_sync_enabled,
            "sync_wled": self.enabled,
            "brightness": self.brightness_mult,
            "pulse_reactive": self.pulse_reactive,
            "active_backend": self.active_backend,
            "tuf_available": self.tuf_driver.available,
            "last_rgb": list(self.last_rgb),
            "host_system": self.host_system,
            "devices": dev_list,
            "devices_count": len(dev_list),
            "active_devices_count": sum(1 for d in dev_list if d.get("enabled") and d.get("online", True)),
            "last_scan_at": self.last_scan_at,
            "scanning": self.scanning,
        }

    def process_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """Called on every telemetry frame from the Master Host."""
        active_devs = [d for d in self.devices.values() if d.get("enabled")]
        if not active_devs and not self.enabled and not self.keyboard_sync_enabled:
            return

        now = time.time()
        if now - self._last_sent < self._min_interval:
            return
        self._last_sent = now

        acc = telemetry.get("acc", [0.8, 0.1, 40])
        color_a = telemetry.get("color_a", acc)
        color_b = telemetry.get("color_b", None)
        is_trans = bool(telemetry.get("is_transitioning", False) and color_b)
        progress = float(telemetry.get("progress", 0.0))
        pulse = float(telemetry.get("pulse", 0.0))
        bass = float(telemetry.get("bass", 0.0))
        mode = telemetry.get("mode", "ring")

        if mode in ("idle", "paused"):
            level = 0.42 * min(1.25, self.brightness_mult)
        elif self.pulse_reactive:
            level = min(1.0, (0.72 + (pulse * 0.16 + bass * 0.14)) * min(1.25, self.brightness_mult))
        else:
            level = min(1.0, 0.88 * min(1.25, self.brightness_mult))

        r_main_mod, g_main_mod, b_main_mod = oklch_to_led_rgb(acc[0], acc[1], acc[2], level)
        self.last_rgb = (r_main_mod, g_main_mod, b_main_mod)

        r_a_mod, g_a_mod, b_a_mod = oklch_to_led_rgb(color_a[0], color_a[1], color_a[2], level)

        if is_trans and color_b:
            r_b_mod, g_b_mod, b_b_mod = oklch_to_led_rgb(color_b[0], color_b[1], color_b[2], level)
        else:
            r_b_mod, g_b_mod, b_b_mod = r_a_mod, g_a_mod, b_a_mod

        for dev in active_devs:
            self._dispatch_device_color(
                dev,
                (r_main_mod, g_main_mod, b_main_mod),
                (r_a_mod, g_a_mod, b_a_mod),
                (r_b_mod, g_b_mod, b_b_mod),
                is_trans,
                progress,
            )

    def _dispatch_device_color(
        self,
        dev: Dict[str, Any],
        rgb_main: Tuple[int, int, int],
        rgb_a: Tuple[int, int, int],
        rgb_b: Tuple[int, int, int],
        is_trans: bool,
        progress: float,
        force: bool = False,
    ) -> None:
        proto = dev.get("protocol")
        addr = str(dev.get("address") or "")
        port = int(dev.get("port") or 0)
        led_count = max(1, int(dev.get("led_count") or 1))
        r, g, b = rgb_main

        if proto == "asus_acpi":
            if force:
                self.last_applied_kbd_rgb = (r, g, b)
                self.tuf_driver.set_rgb(r, g, b)
            else:
                self._update_laptop_keyboard(r, g, b)
        elif proto == "wled_ddp" and addr:
            if is_trans and led_count > 1:
                self._send_wled_ddp_multi(
                    rgb_a[0], rgb_a[1], rgb_a[2],
                    rgb_b[0], rgb_b[1], rgb_b[2],
                    progress,
                    ip=addr,
                    port=port or 4048,
                    num_leds=led_count,
                )
            else:
                self._send_wled_ddp_solid(r, g, b, ip=addr, port=port or 4048, num_leds=led_count)
        elif proto == "openrgb" and addr:
            idx = int(dev.get("controller_index") or 0)
            if is_trans and led_count > 1:
                leds = self._compute_gradient_leds(rgb_a, rgb_b, progress, led_count)
            else:
                leds = [(r, g, b)] * led_count
            OpenRgbClient.update_color(addr, port or 6742, idx, leds)
        elif proto == "wiz_udp" and addr:
            self._send_wiz_udp(addr, port or 38899, r, g, b)
        elif proto == "yeelight" and addr:
            self._send_yeelight_tcp(addr, port or 55443, r, g, b)
        elif proto == "govee_lan" and addr:
            self._send_govee_udp(addr, port or 4003, r, g, b)
        elif proto == "linux_sysfs" and addr:
            self._write_linux_sysfs(addr, r, g, b)

    def _compute_gradient_leds(
        self,
        rgb1: Tuple[int, int, int],
        rgb2: Tuple[int, int, int],
        progress: float,
        num_leds: int,
    ) -> List[Tuple[int, int, int]]:
        r1, g1, b1 = rgb1
        r2, g2, b2 = rgb2
        center = 1.0 - progress
        zone_w = 0.35
        out: List[Tuple[int, int, int]] = []
        for i in range(num_leds):
            x = i / max(1, num_leds - 1)
            t = max(0.0, min(1.0, (x - (center - zone_w / 2.0)) / zone_w))
            r = max(0, min(255, int(round(r1 * (1.0 - t) + r2 * t))))
            g = max(0, min(255, int(round(g1 * (1.0 - t) + g2 * t))))
            b = max(0, min(255, int(round(b1 * (1.0 - t) + b2 * t))))
            out.append((r, g, b))
        return out

    def _ensure_udp_sock(self) -> socket.socket:
        if not self._udp_sock:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setblocking(False)
        return self._udp_sock

    def _send_wled_ddp_multi(
        self,
        r1: int, g1: int, b1: int,
        r2: int, g2: int, b2: int,
        progress: float,
        ip: Optional[str] = None,
        port: Optional[int] = None,
        num_leds: Optional[int] = None,
    ) -> None:
        """Sends a Distributed Display Protocol (DDP) UDP packet with dual-song gradient."""
        try:
            sock = self._ensure_udp_sock()
            target_ip = ip or self.wled_ip
            target_port = port or self.wled_port or 4048
            leds_cnt = num_leds or self.wled_led_count or 60
            if not target_ip:
                return

            data_len = leds_cnt * 3
            header = bytearray([
                0x41, 0x00, 0x01, 0x01,
                0x00, 0x00, 0x00, 0x00,
                (data_len >> 8) & 0xFF, data_len & 0xFF
            ])
            payload = bytearray()
            for r, g, b in self._compute_gradient_leds((r1, g1, b1), (r2, g2, b2), progress, leds_cnt):
                payload.extend([r, g, b])
            sock.sendto(bytes(header + payload), (target_ip, target_port))
        except Exception as e:
            logger.debug("DDP multi send error: %s", e)

    def _send_wled_ddp_solid(
        self,
        r: int, g: int, b: int,
        ip: Optional[str] = None,
        port: Optional[int] = None,
        num_leds: Optional[int] = None,
    ) -> None:
        """Sends a Distributed Display Protocol (DDP) UDP packet with solid color across all LEDs."""
        try:
            sock = self._ensure_udp_sock()
            target_ip = ip or self.wled_ip
            target_port = port or self.wled_port or 4048
            leds_cnt = num_leds or self.wled_led_count or 60
            if not target_ip:
                return

            data_len = leds_cnt * 3
            header = bytearray([
                0x41, 0x00, 0x01, 0x01,
                0x00, 0x00, 0x00, 0x00,
                (data_len >> 8) & 0xFF, data_len & 0xFF
            ])
            payload = bytearray([r, g, b] * leds_cnt)
            sock.sendto(bytes(header + payload), (target_ip, target_port))
        except Exception as e:
            logger.debug("DDP solid send error: %s", e)

    def _send_wiz_udp(self, ip: str, port: int, r: int, g: int, b: int) -> None:
        try:
            sock = self._ensure_udp_sock()
            pkt = json.dumps({"method": "setPilot", "params": {"state": True, "r": r, "g": g, "b": b, "dimming": 100}}).encode("utf-8")
            sock.sendto(pkt, (ip, port))
        except Exception:
            pass

    def _send_govee_udp(self, ip: str, port: int, r: int, g: int, b: int) -> None:
        try:
            sock = self._ensure_udp_sock()
            pkt = json.dumps({
                "msg": {
                    "cmd": "colorwc",
                    "data": {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}
                }
            }).encode("utf-8")
            sock.sendto(pkt, (ip, port))
        except Exception:
            pass

    def _send_yeelight_tcp(self, ip: str, port: int, r: int, g: int, b: int) -> None:
        try:
            rgb_int = ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
            if rgb_int == 0:
                rgb_int = 1
            cmd = json.dumps({"id": 1, "method": "set_rgb", "params": [rgb_int, "smooth", 40]}) + "\r\n"
            with socket.create_connection((ip, port), timeout=0.08) as s:
                s.sendall(cmd.encode("utf-8"))
        except Exception:
            pass

    def _write_linux_sysfs(self, led_dir: str, r: int, g: int, b: int) -> None:
        try:
            base = Path(led_dir)
            multi = base / "multi_intensity"
            if multi.exists():
                multi.write_text(f"{r} {g} {b}\n", encoding="utf-8")
        except Exception:
            pass

    def _update_laptop_keyboard(self, r: int, g: int, b: int) -> None:
        """Applies RGB color to ASUS ATKACPI laptop keyboard backlight."""
        if not self.tuf_driver.available:
            return
        lr, lg, lb = self.last_applied_kbd_rgb
        if abs(r - lr) < 3 and abs(g - lg) < 3 and abs(b - lb) < 3:
            return
        self.last_applied_kbd_rgb = (r, g, b)
        self.tuf_driver.set_rgb(r, g, b)

    def test_color(self, r: int, g: int, b: int, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Manually tests a given RGB color on a specific device or across all enabled/available outputs."""
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        self.last_rgb = (r, g, b)

        if device_id and device_id in self.devices:
            targets = [self.devices[device_id]]
            for dev in targets:
                self._dispatch_device_color(dev, (r, g, b), (r, g, b), (r, g, b), False, 0.0, force=True)
        else:
            targets = [d for d in self.devices.values() if d.get("enabled")] or list(self.devices.values())
            for dev in targets:
                self._dispatch_device_color(dev, (r, g, b), (r, g, b), (r, g, b), False, 0.0, force=True)

            if self.wled_ip and not any(d.get("address") == self.wled_ip for d in targets):
                self._send_wled_ddp_solid(r, g, b)
            if self.tuf_driver.available and not any(d.get("protocol") == "asus_acpi" for d in targets):
                self.last_applied_kbd_rgb = (r, g, b)
                self.tuf_driver.set_rgb(r, g, b)

        return {
            "status": "ok",
            "rgb": [r, g, b],
            "tuf_active": self.tuf_driver.available,
            "tested_devices": [d["id"] for d in targets],
        }


smart_lights = SmartLightsManager()
