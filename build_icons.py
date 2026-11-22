"""Render the editable SVG brand to PNG, Windows ICO and macOS ICNS."""
from pathlib import Path
import struct
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter, QGuiApplication
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent/'gasketfit/assets'


def render(source, size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    QSvgRenderer(str(source)).render(painter)
    painter.end()
    data = QByteArray(); buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert img.save(buffer, 'PNG')
    return bytes(data)


def main():
    sizes = (16,24,32,48,64,128,256)
    frames = [render(ROOT/'icon.svg', s) for s in sizes]
    header = struct.pack('<HHH',0,1,len(frames)); offset = 6+16*len(frames)
    directory = b''
    for size, frame in zip(sizes,frames):
        directory += struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(frame),offset)
        offset += len(frame)
    (ROOT/'icon.ico').write_bytes(header+directory+b''.join(frames))
    chunks = b''
    for size, tag in ((16,b'icp4'),(32,b'icp5'),(64,b'icp6'),(128,b'ic07'),(256,b'ic08'),(512,b'ic09'),(1024,b'ic10')):
        frame = render(ROOT/'icon.svg',size)
        chunks += tag+struct.pack('>I',8+len(frame))+frame
    (ROOT/'icon.icns').write_bytes(b'icns'+struct.pack('>I',8+len(chunks))+chunks)
    (ROOT/'icon.png').write_bytes(render(ROOT/'icon.svg',512))
    svg = (ROOT/'icon.svg').read_text()
    mark = svg[svg.index('<defs>'):svg.rindex('</svg>')]
    logo = '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="240" viewBox="0 0 960 240"><rect width="960" height="240" rx="30" fill="#070b1a"/><g transform="translate(32 32) scale(.34375)">'+mark+'</g><text x="246" y="131" fill="#ffffff" font-family="Segoe UI,Arial,sans-serif" font-size="80" font-weight="600">GasketFit</text><text x="250" y="178" fill="#22d3ff" font-family="Segoe UI,Arial,sans-serif" font-size="25" letter-spacing="7">BETA · PFDMR</text></svg>'
    (ROOT/'logo.svg').write_text(logo,encoding='utf8')
    img = QImage(960,240,QImage.Format.Format_ARGB32); img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img); QSvgRenderer(str(ROOT/'logo.svg')).render(painter); painter.end()
    assert img.save(str(ROOT/'logo.png'))


if __name__ == '__main__':
    app = QGuiApplication.instance() or QGuiApplication([])
    main()
