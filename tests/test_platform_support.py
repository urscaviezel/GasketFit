import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gasketfit import platform_support as ports
from gasketfit import online, driver_profile
from gasketfit.meshio import Mesh
from gasketfit.printmesh import prepare_print_mesh
import numpy as np


class PlatformSupport(unittest.TestCase):
    def test_native_package_names(self):
        self.assertEqual(ports.package_name('1.2.3','linux','x86_64'),'GasketFit-1.2.3-Linux-x64.zip')
        self.assertEqual(ports.package_name('1.2.3','darwin','arm64'),'GasketFit-1.2.3-macOS-arm64.zip')
        self.assertEqual(ports.package_name('1.2.3','win32','AMD64'),'GasketFit-1.2.3-Windows-x64.zip')
        self.assertIsNone(ports.package_name('1.2.3','linux','unknown'))

    def test_linux_and_mac_data_do_not_write_to_installation(self):
        with patch.dict(os.environ,{},clear=True):
            for system in ('linux','darwin'):
                with patch.object(ports.sys,'platform',system), patch.object(ports.QStandardPaths,'writableLocation',return_value='/user/data'):
                    self.assertEqual(ports.data_folder(),Path('/user/data/GasketFit'))
                    self.assertEqual(ports.cache_folder(),Path('/user/data/GasketFit'))

    def test_isolated_data_override(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'GASKETFIT_DATA_DIR':directory}):
            self.assertEqual(ports.data_folder(),Path(directory).resolve())
            self.assertEqual(ports.cache_folder(),Path(directory).resolve()/'cache')

    def test_windows_installer_and_driver_cannot_run_on_unix(self):
        with patch.object(ports.sys,'platform','linux'), patch('subprocess.Popen') as launch:
            with self.assertRaises(RuntimeError): online.prepare_update({},Path('/unused'))
            with self.assertRaises(RuntimeError): online.install_update(Path('/unused'),Path('/unused'))
            with self.assertRaises(RuntimeError): driver_profile.profile_folder()
            launch.assert_not_called()

    def test_native_release_selection(self):
        release={'tag_name':'v99.0.0','assets':[{'name':'GasketFit-99.0.0-Linux-x64.zip'},{'name':'GasketFit-99.0.0-Windows-x64.zip'},{'name':'checksums.json'}]}
        with patch.object(ports.sys,'platform','linux'), patch.object(ports.platform,'machine',return_value='x86_64'), patch.object(online,'github_json',return_value=[release]):
            self.assertEqual(online.check_update()['package']['name'],'GasketFit-99.0.0-Linux-x64.zip')

    def test_unix_invalid_mesh_never_launches_windows_repair(self):
        mesh=Mesh(np.array([[0.,0,0],[1,0,0],[0,1,0]]),np.array([[0,1,2]]),'open')
        with patch.object(ports.sys,'platform','linux'), patch('subprocess.run') as launch:
            with self.assertRaises(RuntimeError): prepare_print_mesh(mesh)
            launch.assert_not_called()
