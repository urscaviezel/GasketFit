from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from gasketfit.driver_profile import configure_profile,profile_ready


class DriverProfile(unittest.TestCase):
    def test_migration_backs_up_and_preserves_user_axes_and_other_apps(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'tmp') as folder:
            root=Path(folder)
            source=b'<AppCfg Default="false"><AppInfo><Signature><Name>GasketFit</Name><ExecutableName>GasketFit.exe</ExecutableName></Signature></AppInfo><CfgProperties><ID>ID_GasketFit</ID><InheritsFromID>ID_Default_KMJ_Cfg</InheritsFromID></CfgProperties><Devices><Device><Axis><Scale>0.34</Scale><Reversed>true</Reversed></Axis></Device></Devices></AppCfg>'
            p=root/'GasketFit-KMJ.xml';p.write_bytes(source)
            other=root/'Blender.xml';other.write_bytes(b'unrelated profile')
            path,backup=configure_profile(root)
            self.assertEqual(backup.read_bytes(),source)
            self.assertTrue(profile_ready(root))
            result=ET.parse(path).getroot()
            self.assertEqual(result.findtext('Devices/Device/Axis/Scale'),'0.34')
            self.assertEqual(result.findtext('Devices/Device/Axis/Reversed'),'true')
            self.assertEqual(other.read_bytes(),b'unrelated profile')
            unchanged=path.read_bytes()
            self.assertEqual(configure_profile(root),(path,None))
            self.assertEqual(path.read_bytes(),unchanged)

    def test_clean_profile(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'tmp') as folder:
            self.assertFalse(profile_ready(folder))
            path,backup=configure_profile(folder)
            self.assertTrue(profile_ready(folder));self.assertIsNone(backup)
