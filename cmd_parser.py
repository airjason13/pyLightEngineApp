from global_def import *
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from unix_client import UnixClient
from pathlib import Path

import re
import gpiod
from gpiod.line import Direction, Value

class CmdParser(QObject):
    unix_data_ready_to_send = pyqtSignal(str)

    sysfs_luminance = Path("/sys/bus/i2c/devices/2-0059/luminance")
    sysfs_current = Path("/sys/bus/i2c/devices/2-0059/current")
    sysfs_temperature = Path("/sys/bus/i2c/devices/2-0059/temperature")
    sysfs_flip = Path("/sys/bus/i2c/devices/2-0059/flip")
    sysfs_mirror = Path("/sys/bus/i2c/devices/2-0059/mirror")
    sysfs_offset = Path("/sys/bus/i2c/devices/2-0059/offset")

    path_persist = Path("/root/persist_config")
    path_lumin_r = Path("/root/persist_config/persis_le_lumin_r")
    path_lumin_g = Path("/root/persist_config/persis_le_lumin_g")
    path_lumin_b = Path("/root/persist_config/persis_le_lumin_b")
    path_current_r = Path("/root/persist_config/persis_le_current_r")
    path_current_g = Path("/root/persist_config/persis_le_current_g")
    path_current_b = Path("/root/persist_config/persis_le_current_b")
    path_flip = Path("/root/persist_config/persis_le_flip")
    path_mirror = Path("/root/persist_config/persis_le_mirror")
    path_offset_r = Path("/root/persist_config/persis_le_offset_r")
    path_offset_g = Path("/root/persist_config/persis_le_offset_g")
    path_offset_b = Path("/root/persist_config/persis_le_offset_b")

    temp_protecting = 1
    temp_limit_hi = 55
    temp_limit_lo = 45

    # GPIOD for controlling -2V of JBD4020
    gpio_chip = gpiod.Chip("/dev/gpiochip0")
    gpio_offset = 4

    gpio_settings = gpiod.LineSettings()
    gpio_settings.direction=Direction.OUTPUT

    # gpio_req = gpio_chip.request_lines(
    #     config={gpio_offset: gpio_settings},
    #     consumer="JBD_N2V"
    # )

    def __init__(self, msg_unix_client:UnixClient):
        super().__init__()
        self.msg_unix_client = msg_unix_client

        # CC: Temperature protection
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._temperature_protection)
        try:
            self.timer.start()
        except Exception as e:
            print(f"Timer error: {e}")

        self.path_persist.mkdir(parents=True, exist_ok=True)

        if not self.path_lumin_r.exists():
            self.path_lumin_r.touch()
        else:
            try:
                value = self.path_lumin_r.read_text().strip()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                self.sysfs_luminance.write_text(f"r {value}")

        if not self.path_lumin_g.exists():
            self.path_lumin_g.touch()
        else:
            try:
                value = self.path_lumin_g.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                self.sysfs_luminance.write_text(f"g {value}")

        if not self.path_lumin_b.exists():
            self.path_lumin_b.touch()
        else:
            try:
                value = self.path_lumin_b.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                self.sysfs_luminance.write_text(f"b {value}")

        if not self.path_current_r.exists():
            self.path_current_r.touch()
        else:
            try:
                value = self.path_current_r.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                self.sysfs_current.write_text(f"r {value}")

        if not self.path_current_g.exists():
            self.path_current_g.touch()
        else:
            try:
                value = self.path_current_g.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                self.sysfs_current.write_text(f"g {value}")

        if not self.path_current_b.exists():
            self.path_current_b.touch()
        else:
            try:
                value = self.path_current_b.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                self.sysfs_current.write_text(f"b {value}")

        if not self.path_mirror.exists():
            self.path_mirror.touch()
        else:
            try:
                value = self.path_mirror.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                if value == "1":
                    self.sysfs_mirror.write_text(f"r 1")
                else:
                    self.sysfs_mirror.write_text(f"r 0")

        if not self.path_flip.exists():
            self.path_flip.touch()
        else:
            try:
                value = self.path_flip.read_text()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                if value == "1":
                    self.sysfs_flip.write_text(f"r 1")
                else:
                    self.sysfs_flip.write_text(f"r 0")

        if not self.path_offset_r.exists():
            self.path_offset_r.touch()
        else:
            try:
                value = self.path_offset_r.read_text().strip()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                en, h, v = value.split(',', 2)
                en, h, v = en.strip(), h.strip(), v.strip()
            else:
                en, h, v = None, None, None

            if en and h and v:
                self.sysfs_offset.write_text(f"r {en} {h} {v}")

        if not self.path_offset_g.exists():
            self.path_offset_g.touch()
        else:
            try:
                value = self.path_offset_g.read_text().strip()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                en, h, v = value.split(',', 2)
                en, h, v = en.strip(), h.strip(), v.strip()
            else:
                en, h, v = None, None, None

            if en and h and v:
                self.sysfs_offset.write_text(f"g {en} {h} {v}")

        if not self.path_offset_b.exists():
            self.path_offset_b.touch()
        else:
            try:
                value = self.path_offset_b.read_text().strip()
            except Exception as e:
                print(f"read failed: {e}")
                value = None

            if value:
                en, h, v = value.split(',', 2)
                en, h, v = en.strip(), h.strip(), v.strip()
            else:
                en, h, v = None, None, None

            if en and h and v:
                self.sysfs_offset.write_text(f"b {en} {h} {v}")

    def _n2v_on_off(self, on) -> None:
        gpio_req = self.gpio_chip.request_lines(
            config={self.gpio_offset: self.gpio_settings},
            consumer="JBD_N2V"
        )
        if on:
            gpio_req.set_values({self.gpio_offset: Value.ACTIVE})
        else:
            gpio_req.set_values({self.gpio_offset: Value.INACTIVE})
        gpio_req.release()
        return None

    def _info_temp_protection(self, enable) -> None:
        data = {}
        data['src'] = "le"
        data['dst'] = "mobile"
        data['cmd'] = LE_SPEC_TEMP_PROTECTION
        data['data'] = "1" if enable == True else "0"
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def _temperature_protection(self):
        try:
            temp = self.sysfs_temperature.read_text().strip()
        except Exception as e:
            print(f"Read temperature error: {e}")
            return None

        values = dict(line.strip().split(':') for line in temp.strip().splitlines())

        temp_r = int(values['R'])
        temp_g = int(values['G'])
        temp_b = int(values['B'])

        if self.temp_protecting == 1:
            if temp_r <= self.temp_limit_lo and temp_g <= self.temp_limit_lo and temp_b <= self.temp_limit_lo:
                self.temp_protecting = 0
                self._n2v_on_off(True)
                self._info_temp_protection(False)
                log.debug(f"R: {temp_r}, G: {temp_g}, B: {temp_b}")
                log.debug("Temp protection recovered")
        else:
            if temp_r >= self.temp_limit_hi or temp_g >= self.temp_limit_hi or temp_b >= self.temp_limit_hi:
                self.temp_protecting = 1
                self._n2v_on_off(False)
                self._info_temp_protection(True)
                log.debug(f"R: {temp_r}, G: {temp_g}, B: {temp_b}")
                log.debug("Temp protecting")

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
        try:
            value = self.sysfs_luminance.read_text().strip()
        except Exception as e:
            print(f"Read error: {e}")
            return None

        print(f"{value}")
        d = {}
        for line in value.strip().splitlines():
            if ':' in line:
                key, val = line.split(':', 1)
                key, val = key.strip(), val.strip()
                d[key] = val
        result = ",".join(f"{k}={v}" for k, v in d.items())
        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = result
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_get_current(self, data:dict):
        try:
            value = self.sysfs_current.read_text().strip()
        except Exception as e:
            print(f"Read error: {e}")
            return None

        print(f"{value}")
        d = {}
        for line in value.strip().splitlines():
            if ':' in line:
                key, val = line.split(':', 1)
                key, val = key.strip(), val.strip()
                d[key] = int(val)

        result = ",".join(f"{k}={v}" for k, v in d.items())
        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = result
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_get_temperature(self, data:dict):
        try:
            value = self.sysfs_temperature.read_text().strip()
        except Exception as e:
            print(f"Read error: {e}")
            return None

        print(f"{value}")
        d = {}
        for line in value.strip().splitlines():
            if ':' in line:
                key, val = line.split(':', 1)
                key, val = key.strip(), val.strip()
                d[key] = int(val)

        result = ",".join(f"{k}={v}" for k, v in d.items())
        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = result
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_get_mirror(self, data:dict):
        try:
            value = self.sysfs_mirror.read_text().strip()
        except Exception as e:
            print(f"Read error: {e}")
            return None

        print(f"{value}")
        if "enable" in value.lower():
            en = 1
        else:
            en = 0

        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = str(en)
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_get_flip(self, data:dict):
        try:
            value = self.sysfs_flip.read_text().strip()
        except Exception as e:
            print(f"Read error: {e}")
            return None

        print(f"{value}")
        if "enable" in value.lower():
            en = 1
        else:
            en = 0

        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = str(en)
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_get_offset(self, data:dict):
        try:
            value = self.sysfs_offset.read_text().strip()
        except Exception as e:
            print(f"Read error: {e}")

        print(f"{value}")

        offset = {}
        pattern = re.compile(r"([RGB])\((enabled|disabled)\)H:\s*(\d+),\s*V:(\d+)")
        for line in value.strip().splitlines():
            match = pattern.match(line)
            if not match:
                continue

            color, en, h, v = match.groups()
            offset[f'{color}E'] = "1" if en == "enabled" else "0"
            offset[f"{color}H"] = h
            offset[f"{color}V"] = v

        result = ",".join(f"{k}={v}" for k, v in offset.items())
        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = result

        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_set_brightness(self, data:dict):
        error_flag = 0
        settings = {}

        for item in data['data'].split(','):
            item = item.strip()
            if not item:
                continue
            if '=' in item:
                key, val = item.split('=', 1)
                key, val = key.strip(), val.strip()
                settings[key] = val

        if not settings:
            error_flag = 1
        else:
            for key, val in settings.items():
                s = f"{key} {val}"
                self.sysfs_luminance.write_text(s)
                if key.lower() == "r":
                    self.path_lumin_r.write_text(f"{val}")
                if key.lower() == "g":
                    self.path_lumin_g.write_text(f"{val}")
                if key.lower() == "b":
                    self.path_lumin_b.write_text(f"{val}")

        data['src'], data['dst'] = data['dst'], data['src']
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        if error_flag == 0:
            reply += ";OK"
        else:
            reply += ";NG"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_current(self, data:dict):
        error_flag = 0
        settings = {}

        for item in data['data'].split(','):
            item = item.strip()
            if not item:
                continue
            if '=' in item:
                key, val = item.split('=', 1)
                key, val = key.strip(), val.strip()
                settings[key] = val

        if not settings:
            error_flag = 1
        else:
            for key, val in settings.items():
                s = f"{key} {val}"
                try:
                    self.sysfs_current.write_text(s)
                except Exception as e:
                    print(f"Error: {e}")
                if key.lower() == "r":
                    self.path_current_r.write_text(f"{val}")
                if key.lower() == "g":
                    self.path_current_g.write_text(f"{val}")
                if key.lower() == "b":
                    self.path_current_b.write_text(f"{val}")

        data['src'], data['dst'] = data['dst'], data['src']
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        if error_flag == 0:
            reply += ";OK"
        else:
            reply += ";NG"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_mirror(self, data:dict):
        error_flag = 0

        if '1' == data['data'].strip():
            set = "r 1"
            self.path_mirror.write_text("1")
        elif '0' == data['data'].strip():
            set = "r 0"
            self.path_mirror.write_text("0")
        else:
            error_flag = 1

        if error_flag == 0:
            try:
                self.sysfs_mirror.write_text(set)
            except Exception as e:
                print(f"Error: {e}")
                error_flag = 1

        data['src'], data['dst'] = data['dst'], data['src']
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        if error_flag == 0:
            reply += ";OK"
        else:
            reply += ";NG"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_flip(self, data:dict):
        error_flag = 0

        if '1' == data['data'].strip():
            set = "r 1"
            self.path_flip.write_text("1")
        elif '0' == data['data'].strip():
            set = "r 0"
            self.path_flip.write_text("0")
        else:
            error_flag = 1

        if error_flag == 0:
            try:
                self.sysfs_flip.write_text(set)
            except Exception as e:
                print(f"Error: {e}")

        data['src'], data['dst'] = data['dst'], data['src']
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        if error_flag == 0:
            reply += ";OK"
        else:
            reply += ";NG"
        self.unix_data_ready_to_send.emit(reply)

    def le_set_offset(self, data:dict):
        error_flag = 0
        settings = data['data'].lower()

        try:
            result = dict(item.split('=') for item in settings.split(',') if '=' in item)
        except ValueError as e:
            print(f"split error: {e}")
            result = {}
            error_flag = 1

        if error_flag == 0:
            if all(result.get(k) for k in ('re', 'rh', 'rv')):
                self.sysfs_offset.write_text(f"r {result['re']} {result['rh']} {result['rv']}")
                self.path_offset_r.write_text(f"{result['re']},{result['rh']},{result['rv']}")

            if all(result.get(k) for k in ('ge', 'gh', 'gv')):
                self.sysfs_offset.write_text(f"g {result['ge']} {result['gh']} {result['gv']}")
                self.path_offset_g.write_text(f"{result['ge']},{result['gh']},{result['gv']}")

            if all(result.get(k) for k in ('be', 'bh', 'bv')):
                self.sysfs_offset.write_text(f"b {result['be']} {result['bh']} {result['bv']}")
                self.path_offset_b.write_text(f"{result['be']},{result['bh']},{result['bv']}")

        data['src'], data['dst'] = data['dst'], data['src']
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        if error_flag == 0:
            reply += ";OK"
        else:
            reply += ";NG"
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
