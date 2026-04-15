import os
import asyncio
import socket
import logging
from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal

from global_def import UNIX_MSG_SERVER_URI

log = logging.getLogger(__name__)

STR_REPLY_OK = "OK"
STR_REPLY_NG = "NG"
UNIX_SOCKET_BUFFER_SIZE = 4 * 1024 * 1024


class UnixServer(QObject):
    unix_data_received = pyqtSignal(str, str)

    def __init__(self, path: str = UNIX_MSG_SERVER_URI):
        super().__init__()
        self.path = path
        self._server: Optional[asyncio.base_events.Server] = None
        self._task: Optional[asyncio.Task] = None
        self.snd_size = UNIX_SOCKET_BUFFER_SIZE
        self.rcv_size = UNIX_SOCKET_BUFFER_SIZE

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        sock = writer.get_extra_info("socket")
        peer_info = "unknown"

        if sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.snd_size)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.rcv_size)
                uid, gid = sock.getpeereid()
                peer_info = f"uid={uid}, gid={gid}"
            except AttributeError:
                import struct
                creds = sock.getsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_PEERCRED,
                    struct.calcsize("3i")
                )
                pid, uid, gid = struct.unpack("3i", creds)
                peer_info = f"pid={pid}, uid={uid}, gid={gid}"

        log.debug("[%s] + Connection from %s", self.path, peer_info)

        buffer = b""

        try:
            while True:
                chunk = await reader.read(4096)

                if not chunk:
                    if buffer:
                        log.warning(
                            "[%s] Incomplete trailing data from %s: len=%d head=%r tail=%r",
                            self.path, peer_info, len(buffer), buffer[:80], buffer[-80:]
                        )
                    break

                buffer += chunk

                while b"\n" in buffer:
                    raw_msg, buffer = buffer.split(b"\n", 1)

                    if not raw_msg.strip():
                        continue

                    try:
                        msg = raw_msg.decode(errors="ignore").strip()
                    except Exception as e:
                        log.error("[%s] Decode failed: %s", self.path, e)
                        writer.write((STR_REPLY_NG + "\n").encode())
                        await writer.drain()
                        continue

                    log.debug("[%s] + Received: %s", self.path, msg)

                    reply = f"{msg} {STR_REPLY_OK}\n"
                    writer.write(reply.encode())
                    await writer.drain()

                    self.unix_data_received.emit(msg, peer_info)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("[%s] Error: %s", self.path, e)
        finally:
            log.debug("[%s] + Close: %s", self.path, peer_info)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.path
        )
        log.debug("[UnixServer] Serving at %s", self.path)
        self._task = asyncio.create_task(self._server.serve_forever())

    async def stop(self):
        if self._server is not None:
            log.debug("[UnixServer] Shutting down...")
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

        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass