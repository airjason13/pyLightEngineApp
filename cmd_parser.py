from global_def import *
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from unix_client import UnixClient


class CmdParser(QObject):
    unix_data_ready_to_send = pyqtSignal(str)

    def __init__(self, msg_unix_client:UnixClient,le_controller):
        super().__init__()
        self.msg_unix_client = msg_unix_client
        self.le = le_controller
        # self.le.temp_event.connect(self._on_temp_event)

    def cmd_unknown(self, data:dict):
        pass

    def parse_cmds(self, data) -> None:
        log.debug("data : %s", data)

        d = {}
        for item in data.split(';'):
            item = item.strip()
            if not item:
                continue
            if ':' in item:
                key, value = item.split(':', 1)
                key, value = key.strip(), value.strip()
                if not key or not value:
                    log.warning("Empty key or value: %s", item)
                    continue
                d[key] = value
            else:
                log.warning("invalid item (missing ':'): %s", item)

        # data
        d.setdefault('data', 'no_data')

        log.debug("parsed dict: %s", d)

        # CC: check if cmd is defined
        cmd:str = d.get('cmd')
        handler = self.cmd_function_map.get(cmd, self.cmd_unknown)

        log.debug("cmd: %s", cmd)
        try:
            handler(self, d)
        except Exception as e:
            log.exception("handler exception {e} for cmd=%s with data=%s", cmd, d)

    def le_get_sw_version(self, data:dict):
        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = Version
        log.debug("data : %s", data)
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_set_test(self, data:dict):
        log.debug("data : %s", data)

    def le_get_brightness(self, data:dict):
        vals = self.le.get_brightness()
        payload = ",".join(f"{k}={v}" for k, v in vals.items())
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{payload}"
        self.unix_data_ready_to_send.emit(reply)

    def le_get_current(self, data:dict):
        vals = self.le.get_current()
        payload = ",".join(f"{k}={v}" for k, v in vals.items())
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{payload}"
        self.unix_data_ready_to_send.emit(reply)

    def le_get_temperature(self, data:dict):
        vals = self.le.get_temperature()
        payload = ",".join(f"{k}={v}" for k, v in vals.items())
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{payload}"
        self.unix_data_ready_to_send.emit(reply)

    def le_get_mirror(self, data:dict):
        val = self.le.get_mirror()
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{val}"
        self.unix_data_ready_to_send.emit(reply)

    def le_get_flip(self, data:dict):
        val = self.le.get_flip()
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{val}"
        self.unix_data_ready_to_send.emit(reply)

    def le_get_offset(self, data:dict):
        vals = self.le.get_offset()
        payload = ",".join(f"{k}={v}" for k, v in vals.items())
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{payload}"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_brightness(self, data:dict):
        # data['data'] = "r=10,g=20,b=30"
        raw = data.get("data", "")

        r = g = b = None
        for item in raw.split(","):
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            k = k.strip().lower()
            v = v.strip()

            if k == "r": r = v
            if k == "g": g = v
            if k == "b": b = v

        ok = self.le.set_brightness(r=r, g=g, b=b)

        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{raw};{'OK' if ok else 'NG'}"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_current(self, data:dict):
        raw = data.get("data", "")

        r = g = b = None
        for item in raw.split(","):
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            k = k.strip().lower()
            v = v.strip()

            if k == "r": r = v
            if k == "g": g = v
            if k == "b": b = v

        ok = self.le.set_current(r=r, g=g, b=b)

        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{raw};{'OK' if ok else 'NG'}"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_mirror(self, data:dict):
        ok = self.le.set_mirror(1 if data["data"].strip() == "1" else 0)
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{data['data']};{'OK' if ok else 'NG'}"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_flip(self, data:dict):
        ok = self.le.set_flip(1 if data["data"].strip() == "1" else 0)
        reply = f"src:{data['dst']};dst:{data['src']};cmd:{data['cmd']};data:{data['data']};{'OK' if ok else 'NG'}"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_offset(self, data: dict):
        # data["data"] example:
        # "re=1,rh=10,rv=20,ge=1,gh=11,gv=21,be=0,bh=12,bv=22"

        raw = data.get("data", "").strip().lower()
        result = {}
        error_flag = 0

        # Parse "key=value" pairs into a dict
        try:
            result = dict(item.split("=", 1) for item in raw.split(",") if "=" in item)
            result = {k.strip(): v.strip() for k, v in result.items()}
        except ValueError as e:
            print(f"split error: {e}")
            result = {}
            error_flag = 1

        if error_flag == 0:
            # --------------------------------------------------
            # R offset: if you provide one field, you must provide all (re, rh, rv)
            # --------------------------------------------------
            r_keys = ("re", "rh", "rv")
            r_values = [result.get(k) for k in r_keys]

            if any(r_values): # user provided something
                if all(r_values):  # user provided everything
                    ok = self.le.set_offset("r", *r_values)
                    if not ok:
                        error_flag = 1
                else:
                    error_flag = 1

            # --------------------------------------------------
            # G offset: if you provide one field, you must provide all (ge, gh, gv)
            # --------------------------------------------------
            g_keys = ("ge", "gh", "gv")
            g_values = [result.get(k) for k in g_keys]

            if any(g_values):
                if all(g_values):
                    ok = self.le.set_offset("g", *g_values)
                    if not ok:
                        error_flag = 1
                else:
                    error_flag = 1

            # --------------------------------------------------
            # B offset: if you provide one field, you must provide all (be, bh, bv)
            # --------------------------------------------------
            b_keys = ("be", "bh", "bv")
            b_values = [result.get(k) for k in b_keys]

            if any(b_values):
                if all(b_values):
                    ok = self.le.set_offset("b", *b_values)
                    if not ok:
                        error_flag = 1
                else:
                    error_flag = 1

            # No valid offset group provided at all -> reject
            if not any((
                    any(r_values),
                    any(g_values),
                    any(b_values),
            )):
                error_flag = 1

        reply = (
            f"src:{data['dst']};"
            f"dst:{data['src']};"
            f"cmd:{data['cmd']};"
            f"data:{raw};"
            f"{'OK' if error_flag == 0 else 'NG'}"
        )
        self.unix_data_ready_to_send.emit(reply)

    cmd_function_map = {
        LE_GET_SW_VERSION: le_get_sw_version,
        LE_SET_TEST: le_set_test,

        LE_GET_BRIGHTNESS: le_get_brightness,
        LE_GET_CURRENT: le_get_current,
        LE_GET_TEMPERATURE: le_get_temperature,
        LE_GET_MIRROR: le_get_mirror,
        LE_GET_FLIP: le_get_flip,
        LE_GET_OFFSET: le_get_offset,

        LE_SET_BRIGHTNESS: le_set_brightness,
        LE_SET_CURRENT: le_set_current,
        LE_SET_MIRROR: le_set_mirror,
        LE_SET_FLIP: le_set_flip,
        LE_SET_OFFSET: le_set_offset,
    }
