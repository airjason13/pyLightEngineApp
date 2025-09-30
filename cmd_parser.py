from global_def import *
from PyQt5.QtCore import QObject, pyqtSignal
from unix_client import UnixClient


class CmdParser(QObject):
    unix_data_ready_to_send = pyqtSignal(str)
    def __init__(self, msg_unix_client:UnixClient):
        super().__init__()
        self.msg_unix_client = msg_unix_client

    def parse_cmds(self, data):
        log.debug("data : %s", data)

        d = dict(item.split(':', 1) for item in data.split(';'))


        if 'data' not in data:
            d['data'] = 'no_data'
        else:
            pass
        log.debug("%s", d)

        try:
            self.cmd_function_map[d['cmd']](self, d)
            '''if 'get' in d['cmd']:
                log.debug("i : %s, v: %s", 'cmd', d['cmd'])
                self.cmd_function_map[d['cmd']](self, d)'''
        except Exception as e:
            log.error(e)


    def le_get_sw_version(self, data:dict):

        data['src'], data['dst'] = data['dst'], data['src']
        data['data'] = Version
        log.debug("data : %s", data)
        # Dict to Str
        reply = ";".join(f"{k}:{v}" for k, v in data.items())
        self.unix_data_ready_to_send.emit(reply)

    def le_set_test(self, data:dict):
        log.debug("data : %s", data)

    cmd_function_map = {
        LE_GET_SW_VERSION: le_get_sw_version,
        LE_SET_TEST: le_set_test,
    }