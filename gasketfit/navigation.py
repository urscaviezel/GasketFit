"""Local camera controls and focused Windows multi-axis HID input.

Windows registration follows keyboard focus (no background/exclusive capture).
Protocol: translation report 1, rotation 2, combined report 1 with 13 bytes.
See Microsoft Raw Input docs and FreeCAD's GuiNativeEventWin32 implementation.
"""
import ctypes as C
from ctypes import wintypes as T
import struct
import sys
import time
import weakref
from PySide6 import QtCore, QtGui, QtWidgets as W
from .localization import current

DEFAULTS = dict(rotate_button='left', pan_button='right', invert_wheel=False,
                space_enabled=True, space_pan=True, space_rotate=True,
                space_translation_gain=1., space_rotation_gain=1.,
                space_invert=[False]*6)


def controls():
    raw=current().settings.get('navigation',{})
    p={**DEFAULTS}
    if isinstance(raw,dict):
        for key in ('rotate_button','pan_button'):
            if raw.get(key) in ('left','middle','right'):p[key]=raw[key]
        for key in ('invert_wheel','space_enabled','space_pan','space_rotate'):
            if isinstance(raw.get(key),bool):p[key]=raw[key]
        for key in ('space_translation_gain','space_rotation_gain'):
            v=raw.get(key)
            if isinstance(v,(int,float)) and .1<=v<=5:p[key]=float(v)
        v=raw.get('space_invert')
        if isinstance(v,list) and len(v)==6 and all(isinstance(x,bool) for x in v):p['space_invert']=v.copy()
    if p['rotate_button']==p['pan_button']:p['pan_button']='middle' if p['rotate_button']!='middle' else 'right'
    if sys.platform != 'win32':
        p['space_enabled'] = False
    return p


def save_controls(p):
    current().settings['navigation']=dict(p)
    current().save_settings()
    current().navigation_changed.emit()


def decode_report(payload):
    """Return a group offset and three/six signed axes; reject short reports."""
    if not payload:return None
    if payload[0]==1 and len(payload)>=13:return 0,struct.unpack_from('<6h',payload,1)
    if payload[0] in (1,2) and len(payload)>=7:return (0 if payload[0]==1 else 3),struct.unpack_from('<3h',payload,1)
    return None


class RawDevice(C.Structure):
    _fields_=[('page',T.USHORT),('usage',T.USHORT),('flags',T.DWORD),('target',T.HWND)]


class RawHeader(C.Structure):
    _fields_=[('kind',T.DWORD),('size',T.DWORD),('device',T.HANDLE),('wparam',T.WPARAM)]


class RawList(C.Structure):
    _fields_=[('device',T.HANDLE),('kind',T.DWORD)]


class SpaceMouse(QtCore.QAbstractNativeEventFilter):
    def __init__(self):
        super().__init__()
        self.axes=[0.]*6
        self.updated=[0.,0.]
        self.views=[]
        self.packets=0
        self.last_motion=0.
        self.pause_until=0.
        self.devices=[]
        self.device_handles=set()
        self.registered=False
        self.error=''
        self.user32=None
        app=W.QApplication.instance()
        self.timer=QtCore.QTimer(app)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.device_timer=QtCore.QTimer(app)
        self.device_timer.setInterval(3000)
        self.device_timer.timeout.connect(self.enumerate)
        if sys.platform=='win32':
            try:
                self.user32=C.WinDLL('user32',use_last_error=True)
                self.user32.RegisterRawInputDevices.argtypes=[C.POINTER(RawDevice),T.UINT,T.UINT]
                self.user32.RegisterRawInputDevices.restype=T.BOOL
                self.user32.GetRawInputDeviceList.argtypes=[C.POINTER(RawList),C.POINTER(T.UINT),T.UINT]
                self.user32.GetRawInputDeviceList.restype=T.UINT
                self.user32.GetRawInputDeviceInfoW.argtypes=[T.HANDLE,T.UINT,C.c_void_p,C.POINTER(T.UINT)]
                self.user32.GetRawInputDeviceInfoW.restype=T.UINT
                self.user32.GetRawInputData.argtypes=[T.HANDLE,T.UINT,C.c_void_p,C.POINTER(T.UINT),T.UINT]
                self.user32.GetRawInputData.restype=T.UINT
                device=RawDevice(1,8,0,None)
                self.registered=bool(self.user32.RegisterRawInputDevices(C.byref(device),1,C.sizeof(device)))
                if not self.registered:self.error=str(C.get_last_error())
                app.installNativeEventFilter(self)
                self.enumerate();self.device_timer.start()
            except (OSError,AttributeError) as exc:self.error=str(exc)

    def enumerate(self):
        if self.user32 is None:return
        count=T.UINT()
        if self.user32.GetRawInputDeviceList(None,C.byref(count),C.sizeof(RawList))==0xffffffff:return
        if count.value>1024:return
        items=(RawList*count.value)()
        if self.user32.GetRawInputDeviceList(items,C.byref(count),C.sizeof(RawList))==0xffffffff:return
        devices=[];handles=set()
        for item in items[:count.value]:
            if item.kind!=2:continue
            # RID_DEVICE_INFO: cbSize, dwType, HID vendor/product/version/page/usage.
            info=C.create_string_buffer(32);struct.pack_into('<I',info,0,32)
            size=T.UINT(32)
            if self.user32.GetRawInputDeviceInfoW(item.device,0x2000000b,info,C.byref(size))==0xffffffff:continue
            vendor,product,version,page,usage=struct.unpack_from('<IIIHH',info.raw,8)
            if vendor not in (0x046d,0x256f) or (page,usage)!=(1,8):continue
            handles.add(int(item.device));devices.append(f'3Dconnexion HID {vendor:04X}:{product:04X}')
        self.device_handles=handles;self.devices=devices

    def nativeEventFilter(self,event_type,message):
        if self.user32 is None or not self.registered:return False,0
        try:
            msg=T.MSG.from_address(int(message))
            if msg.message!=0xff:return False,0
            size=T.UINT()
            if self.user32.GetRawInputData(msg.lParam,0x10000003,None,C.byref(size),C.sizeof(RawHeader))==0xffffffff:return False,0
            if not C.sizeof(RawHeader)+8<=size.value<=65536:return False,0
            data=C.create_string_buffer(size.value)
            result=self.user32.GetRawInputData(msg.lParam,0x10000003,data,C.byref(size),C.sizeof(RawHeader))
            if result==0xffffffff:return False,0
            header=RawHeader.from_buffer(data)
            if header.kind!=2 or int(header.device or 0) not in self.device_handles:return False,0
            stride,count=struct.unpack_from('<II',data.raw,C.sizeof(RawHeader))
            begin=C.sizeof(RawHeader)+8
            if not 1<=stride<=256 or begin+stride*count>result:return False,0
            for i in range(count):
                report=decode_report(data.raw[begin+i*stride:begin+(i+1)*stride])
                if report:
                    start,axes=report;self.axes[start:start+len(axes)]=axes
                    now=time.monotonic();self.updated[start//3]=now
                    if len(axes)==6:self.updated[1]=now
                    self.packets+=1;self.last_motion=now
        except (ValueError,TypeError,OverflowError,struct.error):pass
        # Let Qt/DefWindowProc clean up foreground WM_INPUT resources.
        return False,0

    def tick(self):
        settings=controls()
        if not settings['space_enabled']:return
        active=W.QApplication.activeWindow()
        if active is None:return
        now=time.monotonic()
        if now<self.pause_until:return
        values=self.axes.copy()
        for group in (0,1):
            if now-self.updated[group]>.18:values[group*3:group*3+3]=[0.,0.,0.]
        values=[(0 if abs(x)<12 else x)*(-1 if settings['space_invert'][i] else 1) for i,x in enumerate(values)]
        if not any(values):return
        self.views=[v for v in self.views if v() is not None]
        for ref in reversed(self.views):
            view=ref()
            try:
                if view.window() is active and view.isVisible() and view.isEnabled():
                    view.space_motion(values,settings);break
            except RuntimeError:continue

    def reset_motion(self):
        self.axes=[0.]*6
        self.updated=[0.,0.]
        self.pause_until=time.monotonic()+.35


_manager=None
def manager():
    global _manager
    if _manager is None:_manager=SpaceMouse()
    return _manager
