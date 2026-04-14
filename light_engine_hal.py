from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from pathlib import Path
import re
import gpiod
from gpiod.line import Direction, Value

from global_def import *

class LightEngineController(QObject):
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
        i2c_dev_path: str = "/sys/bus/i2c/devices/2-0059",
        gpiochip: str = "/dev/gpiochip0",
        n2v_gpio_offset: int = 4,
        temp_limit_hi: int = 55,
        temp_limit_lo: int = 45,
        temp_poll_ms: int = 100,
        enable_timer: bool = True,
    ):
        super().__init__()

        self.temp_log_counter = 0
        base = Path(i2c_dev_path)

        # sysfs nodes
        self.sysfs_luminance = base / "luminance"
        self.sysfs_current = base / "current"
        self.sysfs_temperature = base / "temperature"
        self.sysfs_flip = base / "flip"
        self.sysfs_mirror = base / "mirror"
        self.sysfs_offset = base / "offset"

        # persist folder
        self.path_persist = Path(PERSIST_CONFIG_URI_PATH)
        self.path_persist.mkdir(parents=True, exist_ok=True)

        # persist files
        self.path_lumin_r = self.path_persist / "persis_le_lumin_r"
        self.path_lumin_g = self.path_persist / "persis_le_lumin_g"
        self.path_lumin_b = self.path_persist / "persis_le_lumin_b"

        self.path_current_r = self.path_persist / "persis_le_current_r"
        self.path_current_g = self.path_persist / "persis_le_current_g"
        self.path_current_b = self.path_persist / "persis_le_current_b"

        self.path_flip = self.path_persist / "persis_le_flip"
        self.path_mirror = self.path_persist / "persis_le_mirror"

        self.path_offset_r = self.path_persist / "persis_le_offset_r"
        self.path_offset_g = self.path_persist / "persis_le_offset_g"
        self.path_offset_b = self.path_persist / "persis_le_offset_b"

        # temp protection state
        self.temp_protecting = 1
        self.temp_limit_hi = int(temp_limit_hi)
        self.temp_limit_lo = int(temp_limit_lo)

        # GPIO (-2V) control
        self.gpio_chip = None
        self.gpio_offset = int(n2v_gpio_offset)
        self.gpio_settings = None
        self.gpiochip_path = gpiochip

        self._init_gpio()

        # restore persisted states (do NOT crash if sysfs missing)
        self.restore_all()

        # Timer inside controller
        self.timer = QTimer(self)
        self.timer.setInterval(int(temp_poll_ms))
        self.timer.timeout.connect(self.temperature_tick)
        if enable_timer:
            QTimer.singleShot(0, self.timer.start)

    # -------------------------
    # GPIO
    # -------------------------
    def _init_gpio(self):
        try:
            self.gpio_chip = gpiod.Chip(self.gpiochip_path)
            self.gpio_settings = gpiod.LineSettings()
            self.gpio_settings.direction = Direction.OUTPUT
        except Exception as e:
            # common: permission denied / device not exist
            log.warning(f"[LE] GPIO not available: {e}")
            self.gpio_chip = None
            self.gpio_settings = None

    def _n2v_on_off(self, on: bool) -> None:
        if self.gpio_chip is None or self.gpio_settings is None:
            # allow running on host or without permission
            return

        try:
            req = self.gpio_chip.request_lines(
                config={self.gpio_offset: self.gpio_settings},
                consumer="JBD_N2V",
            )
            req.set_values({self.gpio_offset: Value.ACTIVE if on else Value.INACTIVE})
            req.release()
        except Exception as e:
            log.warning(f"[LE] GPIO set failed: {e}")

    # -------------------------
    # Restore / Persist helpers
    # -------------------------
    def _touch_if_missing(self, path: Path) -> None:
        try:
            if not path.exists():
                path.touch()
        except Exception as e:
            log.warning(f"[LE] touch failed {path}: {e}")

    def _safe_read(self, path: Path) -> str:
        try:
            return path.read_text().strip()
        except Exception:
            return ""

    def _safe_write(self, path: Path, text: str) -> bool:
        """
        write sysfs. return True if wrote, False if skipped/failed
        """
        try:
            if not path.exists():
                return False
            path.write_text(text)
            return True
        except Exception as e:
            log.warning(f"[LE] write failed {path}: {e}")
            return False

    def restore_all(self) -> None:
        # ensure persist files exist
        for p in [
            self.path_lumin_r, self.path_lumin_g, self.path_lumin_b,
            self.path_current_r, self.path_current_g, self.path_current_b,
            self.path_flip, self.path_mirror,
            self.path_offset_r, self.path_offset_g, self.path_offset_b,
        ]:
            self._touch_if_missing(p)

        # brightness restore
        self._restore_simple_rgb(self.path_lumin_r, self.sysfs_luminance, "r")
        self._restore_simple_rgb(self.path_lumin_g, self.sysfs_luminance, "g")
        self._restore_simple_rgb(self.path_lumin_b, self.sysfs_luminance, "b")

        # current restore
        self._restore_simple_rgb(self.path_current_r, self.sysfs_current, "r")
        self._restore_simple_rgb(self.path_current_g, self.sysfs_current, "g")
        self._restore_simple_rgb(self.path_current_b, self.sysfs_current, "b")

        # flip / mirror restore
        self._restore_flag(self.path_flip, self.sysfs_flip)
        self._restore_flag(self.path_mirror, self.sysfs_mirror)

        # offset restore
        self._restore_offset(self.path_offset_r, self.sysfs_offset, "r")
        self._restore_offset(self.path_offset_g, self.sysfs_offset, "g")
        self._restore_offset(self.path_offset_b, self.sysfs_offset, "b")

    def _restore_simple_rgb(self, persist: Path, sysfs: Path, ch: str) -> None:
        value = self._safe_read(persist)
        if not value:
            return
        self._safe_write(sysfs, f"{ch} {value}")

    def _restore_flag(self, persist: Path, sysfs: Path) -> None:
        # sysfs may not exist on some build -> skip
        if not sysfs.exists():
            return
        value = self._safe_read(persist)
        if value not in ("0", "1"):
            return
        self._safe_write(sysfs, f"r {value}")

    def _restore_offset(self, persist: Path, sysfs: Path, ch: str) -> None:
        if not sysfs.exists():
            return
        value = self._safe_read(persist)
        if not value:
            return
        try:
            en, h, v = [x.strip() for x in value.split(",", 2)]
        except ValueError:
            return
        if en and h and v:
            self._safe_write(sysfs, f"{ch} {en} {h} {v}")

    # -------------------------
    # Public API: GET
    # -------------------------
    def get_brightness(self) -> dict:
        """
        return dict: {"R": "...", "G": "...", "B": "..."} (string or int ok)
        """
        text = self._safe_read(self.sysfs_luminance)
        return self._parse_key_value_lines(text, cast_int=False)

    def get_current(self) -> dict:
        text = self._safe_read(self.sysfs_current)
        return self._parse_key_value_lines(text, cast_int=True)

    def get_temperature(self) -> dict:
        text = self._safe_read(self.sysfs_temperature)
        return self._parse_key_value_lines(text, cast_int=True)

    def get_flip(self) -> int:
        text = self._safe_read(self.sysfs_flip).lower()
        return 1 if "enable" in text else 0

    def get_mirror(self) -> int:
        text = self._safe_read(self.sysfs_mirror).lower()
        return 1 if "enable" in text else 0

    def get_offset(self) -> dict:
        """
        parse:
            R(enabled)H: 12, V:34
        -> { "RE":"1", "RH":"12","RV":"34", ... }
        """
        text = self._safe_read(self.sysfs_offset)
        offset = {}
        pattern = re.compile(r"([RGB])\((enabled|disabled)\)H:\s*(\d+),\s*V:(\d+)")
        for line in text.splitlines():
            m = pattern.match(line.strip())
            if not m:
                continue
            color, en, h, v = m.groups()
            offset[f"{color}E"] = "1" if en == "enabled" else "0"
            offset[f"{color}H"] = h
            offset[f"{color}V"] = v
        return offset

    def _parse_key_value_lines(self, text: str, cast_int: bool) -> dict:
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

    # -------------------------
    # Public API: SET
    # -------------------------
    def set_brightness(self, r=None, g=None, b=None) -> bool:
        ok = True
        ok &= self._set_rgb_triplet(self.sysfs_luminance, self.path_lumin_r, self.path_lumin_g, self.path_lumin_b, r, g, b)
        return ok

    def set_current(self, r=None, g=None, b=None) -> bool:
        ok = True
        ok &= self._set_rgb_triplet(self.sysfs_current, self.path_current_r, self.path_current_g, self.path_current_b, r, g, b)
        return ok

    def _set_rgb_triplet(self, sysfs: Path, pr: Path, pg: Path, pb: Path, r, g, b) -> bool:
        wrote_any = False
        if r is not None:
            wrote_any |= self._safe_write(sysfs, f"r {r}")
            try: pr.write_text(str(r))
            except Exception: pass
        if g is not None:
            wrote_any |= self._safe_write(sysfs, f"g {g}")
            try: pg.write_text(str(g))
            except Exception: pass
        if b is not None:
            wrote_any |= self._safe_write(sysfs, f"b {b}")
            try: pb.write_text(str(b))
            except Exception: pass
        return wrote_any

    def set_flip(self, enable: int) -> bool:
        if not self.sysfs_flip.exists():
            return False
        v = "1" if str(enable).strip() == "1" else "0"
        try:
            self.path_flip.write_text(v)
        except Exception:
            pass
        return self._safe_write(self.sysfs_flip, f"r {v}")

    def set_mirror(self, enable: int) -> bool:
        if not self.sysfs_mirror.exists():
            return False
        v = "1" if str(enable).strip() == "1" else "0"
        try:
            self.path_mirror.write_text(v)
        except Exception:
            pass
        return self._safe_write(self.sysfs_mirror, f"r {v}")

    def set_offset(self, ch: str, en: str, h: str, v: str) -> bool:
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

        # write to hardware
        ok = self._safe_write(self.sysfs_offset, f"{ch} {en} {h} {v}")

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

    # -------------------------
    # Temperature protection
    # -------------------------
    def temperature_tick(self) -> None:
        if platform.machine() == 'x86_64':
            return

        temps = self.get_temperature()
        if not temps:
            # log.debug("get temp fail")
            return

        try:
            tr = int(temps.get("R"))
            tg = int(temps.get("G"))
            tb = int(temps.get("B"))
        except Exception:
            return

        self.temp_log_counter += 1
        if self.temp_log_counter >= 30:
            log.debug(f"[DEBUG] Current Temps - R:{tr} G:{tg} B:{tb} (Protecting:{self.temp_protecting})")
            self.temp_log_counter = 0

        if self.temp_protecting == 1:
            # recover
            if tr <= self.temp_limit_lo and tg <= self.temp_limit_lo and tb <= self.temp_limit_lo:
                self.temp_protecting = 0
                self._n2v_on_off(True)
                self.temp_event.emit(False)
                log.debug(f"[LE] Temp recovered R:{tr} G:{tg} B:{tb}")
        else:
            # protect
            if tr >= self.temp_limit_hi or tg >= self.temp_limit_hi or tb >= self.temp_limit_hi:
                self.temp_protecting = 1
                self._n2v_on_off(False)
                self.temp_event.emit(True)
                log.debug(f"[LE] Temp protecting R:{tr} G:{tg} B:{tb}")
