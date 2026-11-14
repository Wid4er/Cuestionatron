# Cuestionatron

Programa local para practicar preguntas tipo test a partir de archivos Markdown. Permite combinar cuestionarios, limitar las preguntas de cada intento y configurar las opciones y la penalización por fallo.

## Descargar

- [Windows de 64 bits](https://github.com/Wid4er/Cuestionatron/releases/latest/download/Cuestionatron-Windows.zip): extrae todo el ZIP y abre **Cuestionatron.exe**. Conserva las carpetas **_interno** y **Cuestionarios** junto al ejecutable. No necesitas instalar Python.
- [Linux x86-64](https://github.com/Wid4er/Cuestionatron/releases/latest/download/Cuestionatron-Linux.tar.gz): extrae el archivo y abre **Cuestionatron**. El binario está compilado y probado en CachyOS; en otras distribuciones puedes usar el código fuente.

La versión de Windows tiene verificados su formato y contenido; la apertura gráfica todavía está pendiente de comprobar en un Windows real.

## Usar desde el código

Necesitas Python 3.10 o superior, sin paquetes adicionales:

```bash
python3 cuestionatron.py
```

Se abrirá la interfaz en el navegador. Selecciona los cuestionarios, configura el intento y pulsa **Empezar test**. Funciona sin conexión a Internet.

## Añadir cuestionarios

Guarda archivos `.md` en **Cuestionarios**. El nombre del archivo será el del cuestionario. Usa `#` para cada pregunta, `+` para respuestas correctas y `-` para incorrectas:

```markdown
# ¿Cuál es la capital de Portugal?
+ Lisboa
- Oporto
- Coímbra
- Braga

# ¿Cuáles son mamíferos?
+ Delfín
+ Murciélago
- Tiburón
- Pingüino
```

Cada pregunta debe tener al menos una respuesta correcta y una incorrecta. Varios `+` indican selección múltiple: hay que marcar todas las correctas y ninguna incorrecta. Pulsa actualizar en la biblioteca después de editar los archivos.

## Opciones y nota

- Preguntas por intento: 20 por defecto, configurable o todas. Se seleccionan al azar entre los cuestionarios elegidos.
- Opciones por pregunta: de 2 a 21. Siempre se incluyen las correctas y se sortean las incorrectas. Si faltan opciones, se muestran las disponibles; si hay muchas correctas, se amplía el número para incluirlas junto a una incorrecta.
- Penalización personalizada por fallo, de 0 a 10 aciertos. Las preguntas en blanco no restan.
- Nota sobre 10 y revisión de cada pregunta. La selección múltiple no tiene puntuación parcial.

```text
nota = máximo(0, (aciertos − fallos × penalización) / preguntas del intento × 10)
```

Al sacar 9 o más aparecen globitos y suena la música incluida. También hay una pequeña visita sorpresa del ganso bailón, con un 0,1 % de probabilidad por pregunta.

Para compilar los ejecutables, ver las comprobaciones y consultar los detalles de funcionamiento: [guía local y compilación](ENTORNO_LOCAL.md).
