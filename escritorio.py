#!/usr/bin/env python3
"""Entrada del ejecutable: una ventana de aplicación y cierre del servidor al salir."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    import msvcrt
else:
    import fcntl

from cuestionatron import APP_FOLDER, DEFAULT_QUIZ_FOLDER, QuizServer, main as terminal_main


def system_environment() -> dict[str, str]:
    """El navegador usa las bibliotecas del sistema, no las del ejecutable empaquetado."""
    env = os.environ.copy()
    original = env.get('LD_LIBRARY_PATH_ORIG')
    if original is None:
        env.pop('LD_LIBRARY_PATH', None)
    else:
        env['LD_LIBRARY_PATH'] = original
    return env


def find_browser() -> str | None:
    if WINDOWS:
        for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
            if base := os.environ.get(variable):
                for relative in ('Microsoft/Edge/Application/msedge.exe',
                                 'Google/Chrome/Application/chrome.exe',
                                 'BraveSoftware/Brave-Browser/Application/brave.exe',
                                 'Chromium/Application/chrome.exe'):
                    path = Path(base) / relative
                    if path.is_file():
                        return str(path)
        for command in ('msedge.exe', 'chrome.exe', 'brave.exe'):
            if path := shutil.which(command):
                return path
        return None
    for command in ('brave', 'brave-browser', 'brave-origin', 'chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'microsoft-edge'):
        if path := shutil.which(command):
            return path
    # Instalación de Brave presente en este equipo.
    path = Path('/opt/brave-origin-bin/brave')
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def browser_command(browser: str, url: str, storage: Path) -> list[str]:
    return [browser, f'--app={url}', f'--user-data-dir={storage / "perfil"}',
            '--no-first-run', '--no-default-browser-check', '--disable-background-mode',
            '--window-size=1360,920', '--class=Cuestionatron']


def dialog(message: str, *, error: bool = False) -> None:
    if WINDOWS:
        import ctypes
        message_box = ctypes.windll.user32.MessageBoxW
        message_box.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        message_box.restype = ctypes.c_int
        message_box(None, message, 'Cuestionatron', 0x10 if error else 0x40)
        return
    env = system_environment()
    if command := shutil.which('kdialog'):
        subprocess.run([command, '--title', 'Cuestionatron', '--error' if error else '--msgbox', message,
                        '--ok-label', 'Aceptar' if error else 'Cerrar Cuestionatron'], env=env, check=False)
    elif command := shutil.which('zenity'):
        subprocess.run([command, '--error' if error else '--info', '--title=Cuestionatron',
                        f'--text={message}', '--ok-label=Aceptar' if error else '--ok-label=Cerrar Cuestionatron'],
                       env=env, check=False)
    else:
        print(message, file=sys.stderr)


def create_server() -> QuizServer:
    DEFAULT_QUIZ_FOLDER.mkdir(parents=True, exist_ok=True)
    # Conserva la dirección habitual para recordar ajustes; evita colisiones con otros programas.
    try:
        return QuizServer(('127.0.0.1', 8765), DEFAULT_QUIZ_FOLDER)
    except OSError:
        return QuizServer(('127.0.0.1', 0), DEFAULT_QUIZ_FOLDER)


def acquire_instance_lock(lock) -> None:
    if WINDOWS:
        lock.seek(0)
        if not lock.read(1):
            lock.write('0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise BlockingIOError('Cuestionatron ya está abierto.') from exc
            raise
    else:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def desktop_main() -> int:
    storage = APP_FOLDER / '.cuestionatron'
    storage.mkdir(exist_ok=True)
    browser = find_browser()
    env = system_environment()
    with (storage / 'instancia.lock').open('a+') as lock:
        try:
            acquire_instance_lock(lock)
        except BlockingIOError:
            # Otro doble clic vuelve a abrir la misma instancia, sin otro servidor.
            for _ in range(20):
                try:
                    url = json.loads((storage / 'instancia.json').read_text(encoding='utf-8'))['url']
                    break
                except (OSError, ValueError, KeyError):
                    time.sleep(.05)
            else:
                raise RuntimeError('Cuestionatron está iniciándose. Vuelve a abrirlo en unos segundos.')
            if browser:
                subprocess.run(browser_command(browser, url, storage), env=env, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(url)
            return 0

        server = create_server()
        url = f'http://127.0.0.1:{server.server_port}'
        instance_file = storage / 'instancia.json'
        instance_file.write_text(json.dumps({'url': url}), encoding='utf-8')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            if browser:
                result = subprocess.run(browser_command(browser, url, storage), env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if result.returncode != 0:
                    raise RuntimeError('No se pudo abrir la ventana de Cuestionatron. Comprueba que tu navegador funciona.')
            else:
                webbrowser.open(url)
                dialog('Cuestionatron está abierto en tu navegador.\n\nSelecciona los cuestionarios, configura las opciones y pulsa «Empezar test».\n\nMantén este aviso abierto mientras practicas. Al pulsar «Cerrar Cuestionatron» se cerrará el programa.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            instance_file.unlink(missing_ok=True)
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        terminal_main()
        return 0
    try:
        return desktop_main()
    except (OSError, RuntimeError) as exc:
        dialog(f'No se pudo iniciar Cuestionatron.\n\n{exc}', error=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
