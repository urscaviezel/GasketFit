"""Package the tested Windows build as a per-user Inno Setup installer."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess
from gasketfit import __version__

ROOT = Path(__file__).resolve().parent

def main():
    compiler = shutil.which('ISCC') or str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))/'Inno Setup 6/ISCC.exe')
    if not Path(compiler).is_file():
        raise RuntimeError('Install Inno Setup 6 or add ISCC to PATH')
    output = ROOT/'dist'/('v'+__version__)/'GasketFit'
    if not (output/'GasketFit.exe').is_file():
        raise RuntimeError('Build and test the portable Windows package first')
    subprocess.run([compiler, '/Qp', '/DAppVersion='+__version__, '/DAppSource='+str(output), str(ROOT/'installer/GasketFit.iss')], check=True)
    target = ROOT/'dist'/f'GasketFit-{__version__}-Windows-x64-Setup.exe'
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.exe.sha256').write_text(digest+'  '+target.name+'\n')
    sums = json.loads((ROOT/'dist/checksums.json').read_text())
    sums[target.name] = digest
    (ROOT/'dist/checksums.json').write_text(json.dumps(sums,indent=2))
    print(target)

if __name__ == '__main__':
    main()
