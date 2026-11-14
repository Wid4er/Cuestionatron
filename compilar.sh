#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/cuestionatron-build.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

python3 -m venv "$build_dir/venv"
"$build_dir/venv/bin/python" -m pip install -r "$project_dir/requirements-build.txt"
cd -- "$project_dir"
PYINSTALLER_CONFIG_DIR="$build_dir/cache" "$build_dir/venv/bin/python" -m PyInstaller \
    --noconfirm --clean --onefile --name Cuestionatron \
    --distpath "$project_dir" --workpath "$build_dir/work" --specpath "$build_dir" \
    --add-data "$project_dir/web:web" escritorio.py

"$build_dir/venv/bin/python" - "$project_dir" <<'PY'
from pathlib import Path
import sys
folder = Path(sys.argv[1])
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
desktop = folder / 'Cuestionatron.desktop'
desktop.write_text('\n'.join([
    '[Desktop Entry]', 'Version=1.0', 'Type=Application', 'Name=Cuestionatron',
    'Comment=Configura y practica tus cuestionarios tipo test',
    f'Exec={quote(folder / "Cuestionatron")}', f'Path={folder}',
    f'Icon={folder / "web" / "favicon.svg"}', 'Terminal=false',
    'Categories=Education;', 'StartupWMClass=Cuestionatron', '',
]), encoding='utf-8')
desktop.chmod(0o755)
PY
printf '\nEjecutable creado: %s/Cuestionatron\n' "$project_dir"
