"""Build the inbox Windows API bridge; no downloads or execution-policy changes."""
from pathlib import Path
import os
import subprocess


def build():
    root = Path(__file__).resolve().parents[1]
    windows = Path(os.environ.get('WINDIR', r'C:\Windows'))
    compiler = windows/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    gac = windows/'Microsoft.NET/assembly/GAC_MSIL'
    runtime = next((gac/'System.Runtime.WindowsRuntime').glob('*/System.Runtime.WindowsRuntime.dll'))
    facade = next((gac/'System.Runtime').glob('*/System.Runtime.dll'))
    sdk = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))/'Windows Kits/10/UnionMetadata'
    metadata = sorted(p for p in sdk.glob('*/Windows.winmd') if p.parent.name[0].isdigit())[-1]
    output = root/'gasketfit/GasketRepair.exe'
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/out:'+str(output),
                    '/r:'+str(runtime), '/r:'+str(facade), '/r:'+str(metadata),
                    str(root/'native/GasketRepair.cs')], check=True)
    return output


if __name__ == '__main__':
    print(build())
