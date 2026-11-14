#!/usr/bin/env python3
"""Construye el ZIP portable Windows x64 desde Linux con LLVM y CPython oficial."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VERSION = '3.14.10'
PYTHON_URL = f'https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip'
# Publicado en https://www.python.org/downloads/release/python-31410/
PYTHON_SHA256 = '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
PACKAGE = 'Cuestionatron-Windows'


def validate_pe(path: Path, *, gui: bool = False) -> None:
    data = path.read_bytes()
    if data[:2] != b'MZ':
        raise ValueError(f'{path.name} no es un ejecutable Windows.')
    offset = struct.unpack_from('<I', data, 0x3C)[0]
    if data[offset:offset + 4] != b'PE\0\0' or struct.unpack_from('<H', data, offset + 4)[0] != 0x8664:
        raise ValueError(f'{path.name} no es PE x64.')
    if gui and struct.unpack_from('<H', data, offset + 24 + 68)[0] != 2:
        raise ValueError(f'{path.name} no está configurado como aplicación gráfica.')


def build_launcher(destination: Path, work: Path) -> None:
    exports = {
        'kernel32': ['GetModuleFileNameW', 'GetFileAttributesW', 'SetEnvironmentVariableW',
                     'CreateProcessW', 'WaitForSingleObject', 'GetExitCodeProcess', 'CloseHandle', 'ExitProcess'],
        'user32': ['MessageBoxW'],
    }
    for library, names in exports.items():
        definitions = work / f'{library}.def'
        definitions.write_text(f'LIBRARY {library}.dll\nEXPORTS\n' + '\n'.join(names) + '\n', encoding='ascii')
        subprocess.run(['llvm-dlltool', '-m', 'i386:x86-64', '-d', str(definitions),
                        '-l', str(work / f'{library}.lib')], check=True)
    obj = work / 'launcher.obj'
    subprocess.run(['clang', '--target=x86_64-pc-windows-msvc', '-O2', '-ffreestanding',
                    '-fno-builtin', '-fno-stack-protector', '-Wall', '-Wextra', '-Werror',
                    '-c', str(ROOT / 'herramientas/windows_launcher.c'), '-o', str(obj)], check=True)
    subprocess.run(['lld-link', '/subsystem:windows', '/entry:entry', '/nodefaultlib', '/machine:x64',
                    '/dynamicbase', '/nxcompat', '/highentropyva', '/timestamp:0', f'/out:{destination}',
                    str(obj), str(work / 'kernel32.lib'), str(work / 'user32.lib')], check=True)
    validate_pe(destination, gui=True)


def build(runtime: Path | None, output: Path) -> Path:
    for tool in ('clang', 'lld-link', 'llvm-dlltool'):
        if not shutil.which(tool):
            raise RuntimeError(f'Falta {tool}; instala las herramientas LLVM para compilar desde Linux.')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cuestionatron-windows-') as tmp:
        work = Path(tmp)
        if runtime is None:
            runtime = work / 'python.zip'
            with urllib.request.urlopen(PYTHON_URL, timeout=60) as response, runtime.open('wb') as target:
                shutil.copyfileobj(response, target)
        if hashlib.sha256(runtime.read_bytes()).hexdigest() != PYTHON_SHA256:
            raise ValueError('El SHA-256 de Python no coincide con la descarga oficial esperada.')
        folder = work / PACKAGE
        python_dir = folder / '_interno/python'
        python_dir.mkdir(parents=True)
        with zipfile.ZipFile(runtime) as archive:
            for name in archive.namelist():
                path = Path(name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('La descarga de Python contiene una ruta no válida.')
            archive.extractall(python_dir)
        (python_dir / 'python314._pth').write_text('python314.zip\n.\n../app\n', encoding='ascii')
        validate_pe(python_dir / 'pythonw.exe', gui=True)
        app = folder / '_interno/app'
        app.mkdir()
        for name in ('cuestionatron.py', 'escritorio.py'):
            shutil.copy2(ROOT / name, app / name)
        shutil.copytree(ROOT / 'web', app / 'web')
        quizzes = folder / 'Cuestionarios'
        quizzes.mkdir()
        for source in sorted((ROOT / 'Cuestionarios').iterdir()):
            if source.suffix.lower() == '.md' and source.is_file() and not source.is_symlink():
                shutil.copy2(source, quizzes / source.name)
        build_launcher(folder / 'Cuestionatron.exe', work)
        (folder / 'LEEME.txt').write_text(
            'CUESTIONATRON PARA WINDOWS (64 BITS)\n\n'
            '1. Extrae TODO el ZIP con la opcion "Extraer todo" de Windows.\n'
            '2. Abre la carpeta extraida y haz doble clic en Cuestionatron.exe.\n'
            '3. Selecciona cuestionarios, preguntas por intento, opciones y penalizacion.\n'
            '4. Pulsa "Empezar test". Cierra las ventanas del test para salir.\n\n'
            'No requiere instalar Python. Mantiene la carpeta Cuestionarios junto al EXE.\n'
            'Puedes editar los .md y pulsar actualizar sin recompilar.\n'
            'Conserva _interno: contiene Python y la interfaz. No abras el EXE dentro del ZIP.\n'
            'Abre Edge, Chrome o Brave como ventana de aplicacion; con otro navegador\n'
            'abre una pestana y un aviso que debes mantener abierto mientras practicas.\n'
            'Guarda el programa en una carpeta donde tengas permiso para escribir.\n'
            'La configuracion local se guarda en .cuestionatron, junto al EXE.\n\n'
            f'Python portable oficial {VERSION}: {PYTHON_URL}\n'
            f'SHA-256 de la descarga: {PYTHON_SHA256}\n'
            'Su licencia y las licencias de terceros estan en _interno/python.\n\n'
            'Construido en Linux; formato PE x64 y contenido del ZIP verificados.\n'
            'La apertura grafica en Windows todavia requiere validacion en ese sistema.\n',
            encoding='utf-8', newline='\r\n')
        archive_path = output / f'{PACKAGE}.zip'
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(work))
        with zipfile.ZipFile(archive_path) as archive:
            error = archive.testzip()
            if error:
                raise ValueError(f'Archivo dañado en el ZIP: {error}')
        print(f'Creado: {archive_path} ({archive_path.stat().st_size / 1024**2:.1f} MiB)')
        return archive_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-zip', type=Path, help='Descarga oficial existente; se verifica su SHA-256.')
    parser.add_argument('--output', type=Path, default=ROOT / 'Entregables')
    args = parser.parse_args()
    build(args.python_zip, args.output.resolve())
