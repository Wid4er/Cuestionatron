# Guía local y compilación

Consulta el [README](README.md) para descargar y empezar a usar Cuestionatron.

Aplicación local para practicar tests a partir de archivos Markdown. Combina cuestionarios, limita las preguntas del intento, elige cuántas opciones mostrar y configura cuánto resta cada fallo. Al terminar, obtienes una nota sobre 10 y una revisión con tus respuestas y las correctas.

## Iniciar

En este Linux puedes hacer **doble clic en `Cuestionatron.desktop`** (icono «Cuestionatron») o en el ejecutable **`Cuestionatron`**, ambos en esta carpeta. Si el gestor de archivos pide confirmar la ejecución del lanzador, elige «Ejecutar».

El ejecutable incluye Python y los archivos de la interfaz: **no necesitas terminal ni instalar paquetes**. En este equipo abre una ventana de aplicación de Brave, sin barra de pestañas. Dentro seleccionas los cuestionarios, ajustas las opciones y pulsas **Empezar test**. Cierra la ventana para cerrar el programa. Otro doble clic mientras está abierto reutiliza la misma instancia. Funciona sin conexión a Internet.

Mantén la carpeta **Cuestionarios** junto al ejecutable. Si mueves el proyecto a otra ubicación, puedes abrir directamente el ejecutable; para regenerar las rutas del icono, ejecuta `./compilar.sh` desde la nueva carpeta. El binario está construido para Linux x86-64 en este equipo; no es un `.exe` de Windows. Con Brave, Chromium o Chrome abre una ventana de aplicación; en otros navegadores abre una pestaña y un aviso para cerrar el programa.

También puedes ejecutarlo desde el código con **Python 3.10 o superior**:

```bash
python3 cuestionatron.py
```

Se abre el navegador en **http://127.0.0.1:8765**. Mantén la terminal abierta mientras practicas; pulsa `Ctrl+C` para cerrar el programa. También puedes ejecutar `python3 cuestionatron.py --no-browser` y abrir la dirección manualmente. Si el puerto está ocupado, usa `--port 8766`.

## Windows

Comparte **[Entregables/Cuestionatron-Windows.zip](Entregables/Cuestionatron-Windows.zip)** con los usuarios de Windows de 64 bits. Deben pulsar **Extraer todo**, abrir la carpeta extraída y hacer doble clic en **Cuestionatron.exe**. Incluye Python portable; no necesitan instalar Python ni usar comandos.

Conserva **_interno** y **Cuestionarios** junto al `.exe`: ambas carpetas forman parte de la distribución. Los cuestionarios se pueden añadir o editar sin recompilar. Se detectan Edge, Chrome y Brave en sus ubicaciones habituales para abrir una ventana de aplicación. Si solo hay otro navegador, se abre una pestaña y un aviso que permite cerrar el programa.

La distribución se construyó en Linux: se ha comprobado el formato PE x64 del lanzador, su configuración como aplicación gráfica, la integridad del ZIP y el SHA-256 del [Python oficial incluido](https://www.python.org/downloads/release/python-31410/). Las ramas de detección de navegador y bloqueo para Windows se han probado con simulaciones; **la apertura gráfica todavía no se ha probado en un Windows real**.

Para regenerar el ZIP desde Linux, con Clang, LLD y llvm-dlltool disponibles:

```bash
python3 herramientas/crear_windows.py
```

Descarga el Python portable oficial, verifica su SHA-256, compila el lanzador Win32 y empaqueta el código web y los cuestionarios actuales. No utiliza PyInstaller como compilador cruzado. Si ya tienes la descarga, puedes reutilizarla con `--python-zip /ruta/python-3.14.10-embed-amd64.zip`.

## Añadir cuestionarios

Guarda tus archivos `.md` dentro de **Cuestionarios**, junto al programa. El nombre del archivo es el nombre que aparecerá en la biblioteca. La distribución incluye los cuestionarios presentes en esa carpeta al generarla; puedes editarlos o eliminarlos.

```markdown
# ¿Cuál es la capital de Portugal?
+ Lisboa
- Oporto
- Coímbra
- Braga

# ¿Cuáles de estos animales son mamíferos?
+ Delfín
+ Murciélago
- Tiburón
- Pingüino
- Cocodrilo
```

- `#` inicia una pregunta; el texto siguiente es su enunciado.
- `+` indica una respuesta correcta y `-` una incorrecta. No es obligatorio dejar espacio después del símbolo.
- Varios `+` convierten la pregunta en selección múltiple.
- Cada pregunta debe tener al menos una respuesta correcta y una incorrecta, sin textos de respuesta repetidos.
- Deja las líneas vacías que quieras entre preguntas. Usa archivos UTF-8. El contenido se muestra como texto, sin interpretar HTML ni formato Markdown adicional.
- Pulsa **↻** en la biblioteca tras añadir o editar archivos. Los errores se muestran con su número de línea y no impiden usar otros cuestionarios.

Se leen los `.md` directamente dentro de la carpeta, sin subcarpetas ni enlaces simbólicos. Para usar otra ubicación: `python3 cuestionatron.py --folder /ruta/a/mis/cuestionarios`.

## Opciones y puntuación

1. Selecciona uno o varios cuestionarios. En **Preguntas por intento** indica cuántas quieres hacer: **20 por defecto**. Se elige una muestra aleatoria del conjunto combinado, sin repetir preguntas dentro del intento. Por ejemplo, de un archivo con 100 preguntas puedes hacer solo 15. Si hay menos preguntas que el límite, se incluyen las disponibles. Activa **Hacer todas las preguntas** para desactivar el límite. Preguntas repetidas en archivos distintos cuentan por separado.
2. Elige de **2 a 21 opciones** por pregunta. Siempre se incluyen todas las correctas. Se seleccionan incorrectas al azar y se mezclan las opciones en cada intento; se admiten 20 incorrectas o más en los archivos. Si faltan opciones, se muestran las disponibles. Si hay demasiadas correctas, se amplía el número de opciones para incluirlas todas junto a una incorrecta como mínimo.
3. Escribe tu penalización en **Penalización personalizada por fallo**, en aciertos por pregunta fallada, de 0 a 10. Inicialmente es `0` (sin penalización); se recuerda el último valor que hayas configurado. Por ejemplo, `0,17` resta 0,17 aciertos por fallo. Puedes introducir cualquier decimal válido en el campo del navegador; los botones son sugerencias y no limitan el valor elegido. Desactiva «Mezclar preguntas» para conservar el orden de los archivos seleccionados y sus preguntas.
4. Responde a tu ritmo. Puedes saltar preguntas, volver a ellas o dejarlas en blanco. **En selección múltiple solo cuenta como acierto la combinación exacta**; una combinación parcial o con opciones incorrectas cuenta como un fallo, sin puntuación parcial.
5. Finaliza para ver la nota y revisar todas las preguntas. «Volver a practicar» genera otro intento con los mismos cuestionarios y ajustes, renovando el orden y las opciones aleatorias.

```text
nota = máximo(0, (aciertos − fallos × penalización) / total de preguntas × 10)
```

El total es el número de preguntas del intento, no el de los archivos originales. Las preguntas en blanco no restan y forman parte de ese total. La nota se redondea a dos decimales y queda entre 0 y 10. Ejemplo: 7 aciertos, 2 fallos y 1 en blanco, con penalización 0,5 → **6/10**.

La selección de cuestionarios y los ajustes se recuerdan en ese navegador. El ejecutable guarda su perfil local en `.cuestionatron`, junto al programa. Las respuestas y resultados de un intento se mantienen en memoria: se pierden al recargar o cerrar la página. Las sesiones del servidor caducan a las seis horas o al cerrar el programa. No se guardan historiales ni se envían los cuestionarios a servicios externos. El servidor solo escucha en `127.0.0.1`.

Cada pregunta tiene un **0,1 % de probabilidad (1 entre 1.000)** de mostrar el ganso bailón como fondo semitransparente. El sorteo se hace una sola vez por pregunta e intento: volver a una pregunta mantiene el resultado. Es decorativo y no afecta a las respuestas ni a la nota. El [GIF indicado por el usuario](https://i.pinimg.com/originals/a5/37/08/a5370847bd3907356e543e27bca7efbe.gif) se incluye en `web/ganso-bailon.gif` para funcionar sin conexión.

Con una **nota final de 9 o más** aparecen globitos y se reproduce el archivo aportado `28 Hall of Fame.mp3`, incluido en `web/celebracion.mp3`. Puedes pausar o reanudar la música; se detiene al iniciar otro intento o volver a la biblioteca. Si el navegador requiere un clic para reproducirla, pulsa **Reproducir música**. La celebración funciona sin conexión y los globitos respetan la preferencia de reducir movimiento del sistema.

## Regenerar el ejecutable

```bash
./compilar.sh
```

Solo para compilar se descargan las herramientas de `requirements-build.txt` en un entorno temporal. El script crea el binario y actualiza el lanzador; no instala paquetes en el Python del sistema. Los archivos web van dentro del binario: después de cambiar el código hay que volver a compilar. Los cuestionarios `.md` se leen de la carpeta externa y se pueden modificar sin recompilar. El empaquetado utiliza [PyInstaller](https://pyinstaller.org/en/stable/).

## Comprobar el proyecto

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
```

Las pruebas cubren el formato Markdown, selección de opciones, corrección y la API HTTP local. Node solo es necesario para comprobar la sintaxis JavaScript; no se necesita para utilizar la aplicación.
