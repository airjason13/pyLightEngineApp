import asyncio
import signal
import sys
import threading
from unix_server import UnixServer
from unix_client import UnixClient
from cmd_parser import CmdParser
from PyQt5.QtCore import QCoreApplication, QTimer, QObject, pyqtSignal
from qasync import QEventLoop, asyncSlot
from global_def import *

class AsyncWorker(QObject):
    """一個在獨立 Thread 中運行 asyncio 事件迴圈的類別"""
    def __init__(self,async_loop,
               unix_server_path=UNIX_LE_SERVER_URI):
        super().__init__()
        self.loop = async_loop

        self.unix_server_path = unix_server_path
        self.tcp_server = None
        self.udp_server = None
        self.unix_server = None
        self.msg_app_unix_client = None
        self.cmd_parser = None


    async def custom_parser(data: bytes, addr):

        return 0

    def get_version(self):
        return Version

    def unix_data_recv_handler(self, msg:str, pid):
        log.debug(f"got {msg} from {pid}")
        self.cmd_parser.parse_cmds(msg)


    def send_to_msg_server(self, send_data:str):
        log.debug("send_data:%s", send_data)
        self._periodic_unix_msg(send_data.encode())

    async def start_all_server_client(self):
        log.debug("")

        self.msg_app_unix_client = UnixClient(UNIX_MSG_SERVER_URI)
        self.unix_server = UnixServer(self.msg_app_unix_client, self.unix_server_path)
        self.unix_server.unix_data_received.connect(self.unix_data_recv_handler)
        self.cmd_parser = CmdParser(self.msg_app_unix_client)
        self.cmd_parser.unix_data_ready_to_send.connect(self.send_to_msg_server)
        await self.unix_server.start()
        await self.msg_app_unix_client.connect()

        ''''# === 測試用 新增：每 5 秒觸發一次 test_send_unix_msg ===
        self.timer = QTimer(self)
        self.timer.setInterval(5000)  # 5 秒
        self.timer.timeout.connect(self._periodic_unix_msg)
        self.timer.start()'''

    def _periodic_unix_msg(self, data:bytes):
        """
        QTimer 觸發時呼叫，安排 coroutine 到 asyncio 事件迴圈
        """
        log.debug("")
        # 例如傳送字串 "Hello from QTimer"
        asyncio.run_coroutine_threadsafe(
            self.test_send_unix_msg(data.decode()),
            self.loop
        )

    async def test_send_unix_msg(self, unix_msg):
        log.debug("test_unix_loop")
        if unix_msg is not None:
            await self.msg_app_unix_client.send(unix_msg)

    async def async_job(self, cmd:str, data=None):

        log.debug("[%s] start", cmd)
        if "initial" in cmd:
            await self.start_all_server_client()
        elif "test_unix_loop" in cmd:
            await self.test_send_unix_msg(data)
        log.debug("[%s] end", cmd)


    def run(self):
        """Thread 進入點：設定並啟動事件迴圈"""
        asyncio.set_event_loop(self.loop)
        # 在啟動時排程一個 coroutine
        self.loop.create_task(self.async_job("initial",))
        log.debug("[AsyncWorker] event loop running ...")
        self.loop.run_forever()

    def add_task(self, name, data):
        """從主線程安排新的 coroutine"""
        asyncio.run_coroutine_threadsafe(self.async_job(name, data), self.loop)

    def stop(self):
        """安全關閉事件迴圈"""
        self.loop.call_soon_threadsafe(self.loop.stop)


def main():
    # 使用 QCoreApplication 取代 QApplication，不需要 GUI 子系統
    app = QCoreApplication(sys.argv)
    # 用 qasync 把 Qt 事件迴圈包裝成 asyncio 事件迴圈
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    worker = AsyncWorker(loop)


    # 友善的 Ctrl+C 結束
    def handle_sigint(*_):
        print("\n[Main] SIGINT received, quitting ...")
        app.quit()

    # Unix 下可用 add_signal_handler，跨平台保險也掛一個 signal.signal
    try:
        loop.add_signal_handler(signal.SIGINT, handle_sigint)
    except NotImplementedError:
        pass
    signal.signal(signal.SIGINT, handle_sigint)

    log.debug("Run AsyncWorker")
    worker.run()


if __name__ == "__main__":
    main()