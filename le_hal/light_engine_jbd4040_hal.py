from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from pathlib import Path
import re
import gpiod
from gpiod.line import Direction, Value

from global_def import *


def _parse_key_value_lines(text: str, cast_int: bool) -> dict:
    d = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if cast_int:
            try:
                d[k] = int(v)
            except Exception:
                d[k] = v
        else:
            d[k] = v
    return d


def _safe_read(path: Path) -> str:
    try:
        ret_str = path.read_text().strip()
        log.debug(f"{path} read {ret_str}")
        return ret_str
    except Exception as e:
        log.warning(f"[LE] read failed {path}: {e}")
        return ""


def _safe_write(path: Path, text: str) -> bool:
    """
    write sysfs. return True if wrote, False if skipped/failed
    """
    try:
        if not path.exists():
            log.warning(f"[LE] write skipped, path not exists: {path}")
            return False
        path.write_text(text)
        # log.debug(f"[LE] write OK: {path}")
        return True
    except Exception as e:
        log.warning(f"[LE] write failed {path}: {e}")
        return False


class LightEngineJBD4040Controller(QObject):
    """
    Hardware layer:
    - sysfs read/write
    - persist restore/save
    - temperature protection timer + GPIO (-2V)
    """

    # True = protecting, False = recovered
    temp_event = pyqtSignal(bool)

    def __init__(
        self,
        oe_params_path: Path,
        temp_limit_hi: int = 55,
        temp_limit_lo: int = 45,
        temp_poll_ms: int = 100,
        enable_timer: bool = True,
    ):
        super().__init__()
        self.temp_log_counter = 0

        base = oe_params_path

        # sysfs nodes
        self.sysfs_luminance = base / "luminance"
        self.sysfs_current = base / "current"
        self.sysfs_temperature = base / "temperature"
        self.sysfs_flip = base / "flip"
        self.sysfs_mirror = base / "mirror"
        self.sysfs_offset = base / "offset"

        log.debug(f"{LightEngineJBD4040Controller} init done")

    def _safe_read(self, path: Path) -> str:
        try:
            ret_str = path.read_text().strip()
            log.debug(f"{path} read {ret_str}")
            return ret_str
        except Exception as e:
            log.warning(f"[LE] read failed {path}: {e}")
            return ""

    # -------------------------
    # Public API: GET
    # -------------------------
    def get_brightness(self) -> dict:
        log.debug(f"get_brightness called")
        """
        return dict: {"R": "...", "G": "...", "B": "..."} (string or int ok)
        """
        log.debug(f"sysfs_luminance : {self.sysfs_luminance}")
        text = self._safe_read(self.sysfs_luminance)
        log.debug(f"luminance : {text}")
        return _parse_key_value_lines(text, cast_int=False)

    def get_current(self) -> dict:
        log.debug(f"get_current called")
        text = _safe_read(self.sysfs_current)
        return _parse_key_value_lines(text, cast_int=True)

    def get_temperature(self) -> dict:
        log.debug(f"get_temperature called")
        text = _safe_read(self.sysfs_temperature)
        return _parse_key_value_lines(text, cast_int=True)

    def get_flip(self) -> int:
        log.debug(f"get_flip called")
        text = _safe_read(self.sysfs_flip).lower()
        return 1 if "enable" in text else 0

    def get_mirror(self) -> int:
        log.debug(f"get_mirror called")
        text = _safe_read(self.sysfs_mirror).lower()
        return 1 if "enable" in text else 0

    def get_offset(self) -> dict:
        log.debug(f"get_offset called")
        """
        parse:
            R(enabled) H:3, V:1
        -> { "re":"1", "rh":"3","rv":"1", ... }
        """

        text = _safe_read(self.sysfs_offset)
        offset = {}

        pattern = re.compile(
            r"([RGB])\((enabled|disabled)\)\s*H:\s*(\d+),\s*V:(\d+)"
        )

        for line in text.splitlines():
            log.debug(f"offset raw line = [{line}]")

            m = pattern.match(line.strip())
            if not m:
                continue

            color, en, h, v = m.groups()

            color = color.lower()

            offset[f"{color}e"] = "1" if en == "enabled" else "0"
            offset[f"{color}h"] = h
            offset[f"{color}v"] = v

        return offset

    # -------------------------
    # Public API: SET
    # -------------------------
    def set_brightness(self, r=None, g=None, b=None) -> bool:
        log.debug(f"set_brightness called")
        ok = True
        ok &= self._set_rgb_triplet(self.sysfs_luminance,r, g, b)
        return ok

    def set_current(self, r=None, g=None, b=None) -> bool:
        log.debug(f"set_current called")
        ok = True
        ok &= self._set_rgb_triplet(self.sysfs_current, r, g, b)
        return ok

    def _set_rgb_triplet(self, sysfs: Path, r, g, b) -> bool:
        log.debug(f"_set_rgb_triplet called")
        wrote_any = False
        try:
            target_oe_params_str = (f"R:{r}\n"
                                    f"G:{g}\n"
                                    f"B:{b}")
            sysfs.write_text(target_oe_params_str)
            wrote_any = True
        except Exception as e:
            log.debug(f"_set_rgb_triplet exception : {e}")
        return wrote_any

    def set_flip(self, enable: int) -> bool:
        log.debug(f"set_flip called")
        if not self.sysfs_flip.exists():
            return False
        v = "1" if str(enable).strip() == "1" else "0"
        try:
            self.path_flip.write_text(v)
        except Exception:
            pass
        return _safe_write(self.sysfs_flip, f"r {v}")

    def set_mirror(self, enable: int) -> bool:
        log.debug(f"set_mirror called")
        if not self.sysfs_mirror.exists():
            return False
        v = "1" if str(enable).strip() == "1" else "0"
        try:
            self.path_mirror.write_text(v)
        except Exception:
            pass
        return _safe_write(self.sysfs_mirror, f"r {v}")

    def set_offset(self, ch: str, en: str, h: str, v: str) -> bool:
        log.debug(f"set_offset called")
        """
        ch: 'r'/'g'/'b'
        en: '0'/'1'
        h,v: int string
        """

        # normalize input
        ch = ch.lower().strip()

        # only allow r/g/b
        if ch not in ("r", "g", "b"):
            return False

        # sysfs must exist
        if not self.sysfs_offset.exists():
            return False

        # normalize values
        en = "1" if str(en).strip() == "1" else "0"
        h = str(h).strip()
        v = str(v).strip()

        # h/v must be valid numbers
        if not h.isdigit() or not v.isdigit():
            return False

        log.debug(f"[LE] set_offset ch={ch}, en={en}, h={h}, v={v}")
        log.debug(f"[LE] sysfs_offset exists={self.sysfs_offset.exists()}, path={self.sysfs_offset}")

        # write to hardware
        ok = _safe_write(self.sysfs_offset, f"{ch} {en} {h} {v}")

        # only persist if hardware write succeeded
        if ok:
            persist = {
                "r": self.path_offset_r,
                "g": self.path_offset_g,
                "b": self.path_offset_b
            }[ch]

            try:
                persist.write_text(f"{en},{h},{v}")
            except Exception:
                pass

        return ok
