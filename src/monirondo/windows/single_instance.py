import ctypes as C
import getpass
import hashlib
import time
from ctypes import wintypes as W

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from monirondo import COMPAT_ID
from monirondo.windows.native import bind, close_handle, kernel32, process_session


class SingleInstance(QObject):
    show_requested = Signal()

    def __init__(self, namespace: str = COMPAT_ID) -> None:
        super().__init__()
        import os
        session = W.DWORD()
        if not process_session(os.getpid(), C.byref(session)):
            raise C.WinError()
        identity = hashlib.sha256(f"{getpass.getuser()}:{session.value}".encode()).hexdigest()[:24]
        self.name = namespace + "-" + identity
        create = bind(kernel32, "CreateMutexW", W.HANDLE, C.c_void_p, W.BOOL, W.LPCWSTR)
        self.handle = create(None, True, "Local\\" + self.name)
        if not self.handle:
            raise C.WinError()
        self.primary = C.get_last_error() != 183
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if self.primary:
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                raise OSError("Local instance communication could not be started")
            self.server.newConnection.connect(self._receive)

    def _receive(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket:
                socket.close()
                socket.deleteLater()
                self.show_requested.emit()

    def notify(self) -> bool:
        for _ in range(20):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(150):
                socket.disconnectFromServer()
                return True
            time.sleep(0.05)
        return False

    def close(self) -> None:
        self.server.close()
        if self.handle:
            if self.primary:
                bind(kernel32, "ReleaseMutex", W.BOOL, W.HANDLE)(self.handle)
            close_handle(self.handle)
            self.handle = None
