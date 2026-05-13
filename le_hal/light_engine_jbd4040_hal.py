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


def update_offset_file(file_path, channel, enabled, h_val, v_val)-> bool:
    """
    更新 offset 檔案內容。
    :param file_path: 檔案路徑 (例如 'offset')
    :param channel: 字串 'r', 'g', 或 'b'
    :param enabled: 整數 0 (disable) 或 1 (enabled)
    :param h_val: 新的 H 數值
    :param v_val: 新的 V 數值
    """
    # 將參數轉為顯示字串
    log.debug(f"enabled: {enabled}")
    log.debug(f"type(enabled): {type(enabled)}")
    status_str = "enabled" if enabled == '1' else "disabled"
    log.debug(f"status_str: {status_str}")
    target_channel = channel.upper()  # 轉為大寫匹配 R, G, B

    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return False

    # 讀取原始內容
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    # 定義正則表達式，用來匹配該通道的那一行
    # 格式：R(xxxx) H:yy, V:zz
    pattern = re.compile(rf"^{target_channel}\(.*\)\s+H:\d+,\s+V:\d+")

    found = False
    for line in lines:
        if pattern.match(line.strip()):
            # 構建新的內容行
            new_line = f"{target_channel}({status_str}) H:{h_val}, V:{v_val}\n"
            new_lines.append(new_line)
            found = True
        else:
            new_lines.append(line)

    if not found:
        print(f"Warning: Channel {target_channel} not found in file.")
        return False

    # 寫回檔案
    with open(file_path, 'w') as f:
        f.writelines(new_lines)

    print(f"Successfully updated {target_channel} to {status_str} H:{h_val}, V:{v_val}")
    return True

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

    # -------------------------
    # Public API: GET
    # -------------------------
    def get_brightness(self) -> dict:
        log.debug(f"get_brightness called")
        """
        return dict: {"R": "...", "G": "...", "B": "..."} (string or int ok)
        """
        log.debug(f"sysfs_luminance : {self.sysfs_luminance}")
        text = _safe_read(self.sysfs_luminance)
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
        log.debug(f"offset : {text}")
        offset = {}

        pattern = re.compile(
            r"([RGB])\((enable|disable|enabled|disabled)\)\s*H:\s*(\d+),?\s*V:\s*(\d+)"
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

        log.debug(f"offset : {offset}")
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
        log.debug(f"set_flip called with enable = {enable}")
        if not self.sysfs_flip.exists():
            return False
        v = "Flip is Enabled" if str(enable).strip() == "1" else "Flip is Disabled"
        return _safe_write(self.sysfs_flip, f"{v}")

    def set_mirror(self, enable: int) -> bool:
        log.debug(f"set_mirror called with enable = {enable}")
        if not self.sysfs_mirror.exists():
            return False
        v = "Mirror is Enabled" if str(enable).strip() == "1" else "Mirror is Disabled"
        return _safe_write(self.sysfs_flip, f"{v}")

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

        # ok = _safe_write(self.sysfs_offset, f"{ch} {en} {h} {v}")
        ok = update_offset_file(self.sysfs_offset, ch, en, h, v)

        return ok
