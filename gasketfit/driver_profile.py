"""3DxWare RawInput app profile, preserving per-app user axis settings."""
from pathlib import Path
import os
import sys
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime


def profile_folder():
    if sys.platform != "win32":
        raise RuntimeError("3DxWare RawInput profiles are only supported on Windows")
    return Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'3Dconnexion/3DxWare/Cfg'


def find_profile(folder=None):
    folder=Path(folder) if folder else profile_folder()
    found=[]
    for name in ('GasketFit-KMJ.xml','GasketFit.xml'):
        path=folder/name
        if path.exists():
            root=ET.parse(path).getroot()
            executable=root.findtext('AppInfo/Signature/ExecutableName','')
            if executable.lower()=='gasketfit.exe':found.append(path)
    if len(found)>1:raise ValueError('Multiple GasketFit driver profiles; select one in 3DxWare first.')
    return found[0] if found else folder/'GasketFit.xml'


def profile_ready(folder=None):
    path=find_profile(folder)
    if not path.exists():return False
    root=ET.parse(path).getroot()
    return root.findtext('AppInfo/Signature/Transport')=='RawInput' and root.findtext('CfgProperties/InheritsFromID')=='ID_Default_Cfg'


def configure_profile(folder=None):
    path=find_profile(folder)
    path.parent.mkdir(parents=True,exist_ok=True)
    if profile_ready(path.parent):return path,None
    backup=None
    if path.exists():
        root=ET.parse(path).getroot()
        backup=path.with_name(path.name+'.before-rawinput-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.bak')
        shutil.copy2(path,backup)
    else:
        root=ET.Element('AppCfg',Default='false',CfgFormatVersion='1.3',ThisFileVersion='2.0')
    def node(parent,name):
        value=parent.find(name)
        if value is None:value=ET.SubElement(parent,name)
        return value
    props=node(root,'CfgProperties')
    if props.find('ID') is None:node(props,'ID').text='ID_GasketFit'
    node(props,'Name').text='GasketFit'
    node(props,'InheritsFromID').text='ID_Default_Cfg'
    signature=node(node(root,'AppInfo'),'Signature')
    node(signature,'Name').text='GasketFit'
    node(signature,'ExecutableName').text='GasketFit.exe'
    node(signature,'Transport').text='RawInput'
    options=node(node(root,'AppInfo'),'Options')
    node(options,'IgnoreMouseWheelInertia').text='true'
    temp=path.with_name(path.name+'.gasketfit-new')
    ET.ElementTree(root).write(temp,encoding='utf-8',xml_declaration=True)
    os.replace(temp,path)
    return path,backup
