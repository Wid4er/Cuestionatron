import errno
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import escritorio
from herramientas.crear_windows import ROOT, validate_pe


class WindowsLauncherTests(unittest.TestCase):
    def test_finds_edge_without_requiring_it_on_path(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / 'Program Files con espacios'
            executable = base / 'Microsoft/Edge/Application/msedge.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.object(escritorio, 'WINDOWS', True), patch.dict(
                    escritorio.os.environ, {'PROGRAMFILES(X86)': str(base)}, clear=True):
                self.assertEqual(escritorio.find_browser(), str(executable))

    def test_windows_falls_back_to_chrome_in_local_app_data(self):
        with TemporaryDirectory() as tmp:
            executable = Path(tmp) / 'Google/Chrome/Application/chrome.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.object(escritorio, 'WINDOWS', True), patch.dict(
                    escritorio.os.environ, {'LOCALAPPDATA': tmp}, clear=True):
                self.assertEqual(escritorio.find_browser(), str(executable))

    def test_windows_lock_uses_first_byte_and_reports_running_instance(self):
        locking = Mock()
        module = SimpleNamespace(locking=locking, LK_NBLCK=2)
        with TemporaryDirectory() as tmp, (Path(tmp) / 'lock').open('a+') as lock:
            with patch.object(escritorio, 'WINDOWS', True), patch.object(escritorio, 'msvcrt', module, create=True):
                escritorio.acquire_instance_lock(lock)
                locking.assert_called_once_with(lock.fileno(), 2, 1)
                lock.seek(0)
                self.assertEqual(lock.read(), '0')
                locking.side_effect = OSError(errno.EACCES, 'locked')
                with self.assertRaises(BlockingIOError):
                    escritorio.acquire_instance_lock(lock)
                locking.side_effect = OSError(errno.EBADF, 'bad file')
                with self.assertRaises(OSError) as caught:
                    escritorio.acquire_instance_lock(lock)
                self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_no_console_does_not_break_http_logging(self):
        with patch('cuestionatron.sys.stderr', None):
            from cuestionatron import QuizHandler
            QuizHandler.log_message(None, 'Respuesta %s', '200')

    def test_browser_arguments_preserve_spaces_and_unicode(self):
        folder = Path('Carpeta con ñ')
        command = escritorio.browser_command('C:/Program Files/msedge.exe', 'http://127.0.0.1:8765', folder)
        self.assertEqual(command[0], 'C:/Program Files/msedge.exe')
        self.assertIn('--app=http://127.0.0.1:8765', command)
        self.assertIn(f'--user-data-dir={folder / "perfil"}', command)

    def test_system_browser_does_not_load_packaged_linux_libraries(self):
        with patch.dict(escritorio.os.environ, {'LD_LIBRARY_PATH': '/bundle', 'LD_LIBRARY_PATH_ORIG': '/system'}, clear=True):
            self.assertEqual(escritorio.system_environment()['LD_LIBRARY_PATH'], '/system')
        with patch.dict(escritorio.os.environ, {'LD_LIBRARY_PATH': '/bundle'}, clear=True):
            self.assertNotIn('LD_LIBRARY_PATH', escritorio.system_environment())


@unittest.skipUnless((ROOT / 'Entregables/Cuestionatron-Windows.zip').is_file(), 'No hay un ZIP Windows construido.')
class WindowsPackageTests(unittest.TestCase):
    def test_zip_contains_current_sources_quizzes_and_runtime(self):
        with zipfile.ZipFile(ROOT / 'Entregables/Cuestionatron-Windows.zip') as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            prefix = 'Cuestionatron-Windows/'
            for name in ('Cuestionatron.exe', 'LEEME.txt', '_interno/python/pythonw.exe',
                         '_interno/python/python314.dll', '_interno/python/python314.zip',
                         '_interno/python/vcruntime140.dll', '_interno/python/LICENSE.txt'):
                self.assertIn(prefix + name, names)
            sources = [ROOT / 'cuestionatron.py', ROOT / 'escritorio.py', *(ROOT / 'web').iterdir()]
            for source in sources:
                if source.is_file():
                    packaged = prefix + '_interno/app/' + str(source.relative_to(ROOT)).replace('\\', '/')
                    self.assertEqual(archive.read(packaged), source.read_bytes())
            current = {path.name: path.read_bytes() for path in (ROOT / 'Cuestionarios').iterdir()
                       if path.suffix.lower() == '.md' and path.is_file() and not path.is_symlink()}
            packaged = {Path(name).name: archive.read(name) for name in names if name.startswith(prefix + 'Cuestionarios/')}
            self.assertEqual(packaged, current)
            self.assertFalse(any('__pycache__' in name or '.cuestionatron/' in name for name in names))
            with TemporaryDirectory() as tmp:
                for name in ('Cuestionatron.exe', '_interno/python/pythonw.exe'):
                    path = Path(tmp) / Path(name).name
                    path.write_bytes(archive.read(prefix + name))
                    validate_pe(path, gui=True)


if __name__ == '__main__':
    unittest.main()
