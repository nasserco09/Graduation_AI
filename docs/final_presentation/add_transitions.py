"""Add standard click-advanced fade transitions without changing slide content."""
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
ET.register_namespace('p', P)
ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')


def add_transitions(source: Path, target: Path) -> int:
    if source.resolve() == target.resolve():
        raise ValueError('Use a separate output file')
    count = 0
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            data = zin.read(entry.filename)
            if entry.filename.startswith('ppt/slides/slide') and entry.filename.endswith('.xml'):
                root = ET.fromstring(data)
                for old in list(root.findall(f'{{{P}}}transition')):
                    root.remove(old)
                transition = ET.Element(f'{{{P}}}transition', {'spd': 'fast', 'advClick': '1'})
                ET.SubElement(transition, f'{{{P}}}fade')
                index = next((i for i, child in enumerate(root) if child.tag in {f'{{{P}}}timing', f'{{{P}}}extLst'}), len(root))
                root.insert(index, transition)
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                count += 1
            zout.writestr(entry, data)
    return count


if __name__ == '__main__':
    print(f'Fade transitions: {add_transitions(Path(sys.argv[1]), Path(sys.argv[2]))}')
