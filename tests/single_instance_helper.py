from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication,QTimer
from gasketfit.single_instance import SingleInstance
app=QCoreApplication([])
folder=Path(sys.argv[2])
guard=SingleInstance(app,directory=folder)
primary=guard.start()
if sys.argv[1]=='client':
    raise SystemExit(1 if primary else 0)
if sys.argv[1]=='claim':
    guard.close()
    raise SystemExit(0 if primary else 1)
assert primary
guard.activated.connect(lambda:(folder.joinpath('activated').write_text('yes'),app.quit()))
app.aboutToQuit.connect(guard.close)
folder.joinpath('ready').write_text('yes')
QTimer.singleShot(20000,app.quit)
raise SystemExit(app.exec())
