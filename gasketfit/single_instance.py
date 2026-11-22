"""One GUI per OS user; portable and installed copies activate the same window."""
import hashlib
import os
import sys
import time
from pathlib import Path
from PySide6 import QtCore, QtNetwork
from shiboken6 import isValid


class SingleInstance(QtCore.QObject):
    activated = QtCore.Signal()

    def __init__(self, parent=None, directory=None):
        super().__init__(parent)
        home = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.GenericDataLocation)
        directory = Path(directory) if directory else Path(home)/'GasketFit'
        directory.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(str(directory).encode()).hexdigest()[:24]
        self.name = 'GasketFit-' + identity
        self.lock = QtCore.QLockFile(str(directory/'instance.lock'))
        self.lock.setStaleLockTime(0)
        self.server = QtNetwork.QLocalServer(self)
        self.server.setSocketOptions(QtNetwork.QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.connection)
        self.sockets = set()
        self.window = None
        self.pending = False
        self.activated.connect(self.activate)

    def start(self):
        if self.lock.tryLock(0):
            # Only the lock owner may remove a stale socket from a crashed app.
            QtNetwork.QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise RuntimeError(self.server.errorString())
            return True
        for attempt in range(25):
            socket = QtNetwork.QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                if socket.waitForReadyRead(1000):
                    try:
                        pid = int(bytes(socket.readAll()).strip())
                        if sys.platform == 'win32' and pid > 0:
                            import ctypes
                            ctypes.windll.user32.AllowSetForegroundWindow(pid)
                    except ValueError:
                        pass
                socket.write(b'activate\n')
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
                return False
            time.sleep(.1)
        raise RuntimeError('GasketFit is already running but is not responding. Please wait and try again.')

    def connection(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.sockets.add(socket)
            socket.write(str(os.getpid()).encode()+b'\n')
            socket.readyRead.connect(lambda s=socket: self.read(s))
            socket.disconnected.connect(lambda s=socket: self.release(s))
            if socket.bytesAvailable():
                self.read(socket)

    def read(self, socket):
        if socket.bytesAvailable() > 128:
            socket.abort()
            return
        if socket.canReadLine() and bytes(socket.readLine()).strip() == b'activate':
            self.activated.emit()

    def release(self, socket):
        self.sockets.discard(socket)
        if isValid(socket):
            socket.deleteLater()

    def set_window(self, window):
        self.window = window
        if self.pending:
            self.activate()

    def activate(self):
        if self.window is None:
            self.pending = True
            return
        self.pending = False
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def close(self):
        self.server.close()
        self.lock.unlock()
