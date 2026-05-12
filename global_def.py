import getpass
import platform
import os
from pathlib import Path

import utils.log_utils
from version import Version
from arglassescmd.cmd_def import *
LOG_FILE_PREFIX = "le_app.log"

log = utils.log_utils.logging_init(__file__, LOG_FILE_PREFIX)

TCP_PORT = 9527
UDP_PORT = 9528


UNIX_MSG_SERVER_URI = '/tmp/ipc_msg_server.sock'
UNIX_DEMO_APP_SERVER_URI = '/tmp/ipc_demo_app_server.sock'
UNIX_SYS_SERVER_URI = '/tmp/ipc_sys_server.sock'
UNIX_LE_SERVER_URI = '/tmp/ipc_le_server.sock'


STR_REPLY_OK = ";OK"
STR_REPLY_NG = ";NG"


current_user = getpass.getuser()

LightEngineDevPathList = [
    '/dev/jbd4020',
    '/dev/jbd4040'
]


def get_LightEngine_Model_AARCH64():
    """
    偵測 LightEngine 型號，回傳偵測到的型號字串。
    若皆未偵測到，則回傳預設值 "JBD4040"。
    """
    # 預設型號
    detected_model = "JBD4040"

    for p in LightEngineDevPathList:
        if os.path.exists(p):
            # 使用更嚴謹的判斷方式
            if 'jbd4020' in p.lower():
                detected_model = "JBD4020"
                break  # 找到就跳出，避免被後續路徑覆蓋
            elif 'jbd4040' in p.lower():
                detected_model = "JBD4040"
                break

    log.debug(f"Detected LightEngineModel: {detected_model}")
    return detected_model

# Media File Uri Path
if  platform.machine() == 'x86_64':
    MEDIAFILE_URI_PATH = f"/home/{current_user}/Videos/"
    SNAPSHOTS_URI_PATH = f"/home/{current_user}/Videos/Snapshots/"
    RECORDINGS_URI_PATH = f"/home/{current_user}/Videos/Recordings/"
    MEDIA_URI_PATH = f"/home/{current_user}/Videos/Media/"
    THUMBNAILS_URI_PATH = f"/home/{current_user}/Videos/thumbnails/"
    PLAYLISTS_URI_PATH = f"/home/{current_user}/Videos/Playlists/"
    PERSIST_CONFIG_URI_PATH = f"/home/{current_user}/Videos/persist/"
    LightEngineModel = "JBD4040"
else:
    MEDIAFILE_URI_PATH = "/root/MediaFiles/"
    SNAPSHOTS_URI_PATH = "/root/MediaFiles/Snapshots/"
    RECORDINGS_URI_PATH = "/root/MediaFiles/Recordings/"
    MEDIA_URI_PATH = "/root/MediaFiles/Media/"
    THUMBNAILS_URI_PATH = "/root/MediaFiles/thumbnails/"
    PLAYLISTS_URI_PATH = "/root/MediaFiles/Playlists/"
    PERSIST_CONFIG_URI_PATH = "/root/persist_config/"
    LightEngineModel = get_LightEngine_Model_AARCH64()
