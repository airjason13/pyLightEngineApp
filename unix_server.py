import asyncio
import os
from typing import Optional

from PyQt5.QtCore import pyqtSignal, QObject
from unix_client import UnixClient
from global_def import *

# ---------------- Unix Socket Server ----------------
class UnixServer(QObject):
    unix_data_received = pyqtSignal(str, int)
    def __init__(self, msg_client: UnixClient, path: str = UNIX_MSG_SERVER_URI):
        super().__init__()
        self.path = path
        self._server: Optional[asyncio.base_events.Server] = None
        self._task: Optional[asyncio.Task] = None
        self.msg_client = msg_client


    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        sock = writer.get_extra_info("socket")
        peer_info = "unknown"
        if sock:
            try:
                uid, gid = sock.getpeereid()
                peer_info = f"uid={uid}, gid={gid}"
            except AttributeError:
                import struct, socket as s
                creds = sock.getsockopt(s.SOL_SOCKET, s.SO_PEERCRED, struct.calcsize('3i'))
                pid, uid, gid = struct.unpack('3i', creds)
                peer_info = f"pid={pid}, uid={uid}, gid={gid}"

        log.debug("[UnixServer] + Connection from %s", peer_info)
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                msg = data.decode(errors="ignore")

                log.debug("[%s] + Received: %s", self.path, msg)
                writer.write(f"{msg}".encode() + f"{STR_REPLY_OK}".encode())
                # writer.write("%s;%s", msg, STR_REPLY_OK)
                await writer.drain()
                self.unix_data_received.emit(msg, peer_info)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # print(f"[UnixServer] ! Error: {e}")
            log.debug(e)
        finally:
            log.debug("[%s] + Close: %s", self.path, pid)
            writer.close()
            await writer.wait_closed()

    async def start(self):
        # 確保不存在舊 socket 檔案
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(self._handle_client, path=self.path)
        # print(f"[UnixServer] Serving at {self.path}")
        log.debug("[Light Engine Unix Server] Serving at %s", self.path)
        self._task = asyncio.create_task(self._server.serve_forever())

    async def stop(self):
        if self._server is not None:
            # print("[UnixServer] Shutting down...")
            log.debug("[Light Engine Unix Server] Shutting down...")
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # 移除 socket 檔案
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass