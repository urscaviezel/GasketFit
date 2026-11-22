import hashlib,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from gasketfit import online,platform_support as ports


class BetaDistribution(unittest.TestCase):
    def test_portable_and_installed_settings_locations(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ports.sys,'platform','win32'), patch.dict(os.environ,{},clear=True):
            root=Path(directory)/'app'; root.mkdir()
            user=Path(directory)/'user'
            with patch.object(ports,'installation_folder',return_value=root),patch.dict(os.environ,{'LOCALAPPDATA':str(user)}):
                self.assertEqual(ports.data_folder(),root)
                (root/'installed.flag').write_text('installed')
                self.assertEqual(ports.data_folder(),user/'GasketFit')
                self.assertEqual(ports.cache_folder(),user/'GasketFit/cache')

    def test_beta_channel_includes_prereleases_but_not_drafts(self):
        releases=[{'tag_name':'v99.1.0','prerelease':True}, {'tag_name':'v99.2.0','draft':True}, {'tag_name':'v99.0.0'}, {'tag_name':'not-a-version'}]
        with patch.object(online,'github_json',return_value=releases),patch.object(online,'RELEASE_CHANNEL','beta'):
            self.assertEqual(online.check_update()['version'],'99.1.0')
        with patch.object(online,'github_json',return_value=releases),patch.object(online,'RELEASE_CHANNEL','stable'):
            self.assertEqual(online.check_update()['version'],'99.0.0')

    def test_installed_windows_selects_and_stages_installer(self):
        name='GasketFit-99.0.0-Windows-x64-Setup.exe'; content=b'MZtest installer'
        package={'name':name,'browser_download_url':'https://github.com/setup'}
        releases=[{'tag_name':'v99.0.0','prerelease':True,'assets':[package,{'name':'checksums.json','browser_download_url':'https://github.com/sums'}]}]
        with tempfile.TemporaryDirectory() as folder,patch.object(ports,'installed_windows',return_value=True),patch.object(ports,'supports_in_app_update',return_value=True),patch.object(ports,'data_folder',return_value=Path(folder)),patch.object(ports,'package_name',return_value='GasketFit-99.0.0-Windows-x64.zip'),patch.object(online,'github_json',return_value=releases):
            release=online.check_update(); self.assertEqual(release['filename'],name)
            with patch.object(online,'request',side_effect=[json.dumps({name:hashlib.sha256(content).hexdigest()}).encode(),content]):
                staged=online.prepare_update(release,Path(folder)/'app')
            self.assertEqual(staged.read_bytes(),content)
            self.assertTrue(staged.is_relative_to(Path(folder)/'updates'))

    def test_second_process_activates_first_process(self):
        helper=Path(__file__).with_name('single_instance_helper.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            owner=subprocess.Popen([sys.executable,str(helper),'owner',directory])
            try:
                deadline=time.monotonic()+12
                while not (root/'ready').exists() and time.monotonic()<deadline:
                    self.assertIsNone(owner.poll());time.sleep(.05)
                self.assertTrue((root/'ready').exists())
                client=subprocess.run([sys.executable,str(helper),'client',directory],timeout=10)
                self.assertEqual(client.returncode,0)
                self.assertEqual(owner.wait(timeout=8),0)
                self.assertEqual((root/'activated').read_text(),'yes')
            finally:
                if owner.poll() is None:owner.terminate();owner.wait(timeout=5)
