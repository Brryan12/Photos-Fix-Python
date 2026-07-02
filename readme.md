# Guía completa: corregir fechas de fotos y videos, y pasarlas al teléfono

## El problema de fondo

Al pasar fotos/videos del teléfono a la laptop, Windows les pone como "fecha de creación" el momento de la copia, no la fecha real. La fecha real queda guardada en la **fecha de modificación** (o, en casos especiales como descargas de apps, en el **nombre del archivo**).

El objetivo de todo este proceso es:
1. Corregir esa fecha en la laptop (a nivel de sistema de archivos y a nivel de metadata interna EXIF).
2. Pasar los archivos de regreso al teléfono **sin que se vuelva a perder la fecha correcta**.

---

## Orden general del proceso

```
1. corregir_fecha_creacion.py   → arregla la fecha de "creación" en Windows
2. corregir_metadata.py         → graba la fecha correcta DENTRO del archivo (EXIF/metadata)
3. reparar_errores.py           → repara los archivos que fallaron en el paso 2
4. transferir_con_fechas.py     → copia todo al teléfono y corrige la fecha ahí también
5. Forzar reescaneo de medios   → para que Google Fotos/Galería se entere
```

Cada script tiene su razón de ser porque **cada capa del sistema (Windows, el archivo mismo, Android) guarda la fecha por separado**, y hay que corregirlas todas para que el resultado final sea consistente en todos lados.

---

## 1. `corregir_fecha_creacion.py` — Arregla la fecha de creación en Windows

**Qué hace:** en Windows, cada archivo tiene una fecha de "creación" (cuándo llegó a ese disco) y una de "modificación" (cuándo se editó por última vez). Cuando copiaste tus fotos del celular, Windows le puso como creación el momento de la copia — pero la fecha de modificación sí sobrevivió intacta con el dato real. Este script iguala la creación a la modificación.

**Requisito:**
```
pip install pywin32
```

**Uso:**
```
python corregir_fecha_creacion.py "C:\ruta\a\tu\carpeta" --simular
python corregir_fecha_creacion.py "C:\ruta\a\tu\carpeta"
```
- `--simular`: solo muestra qué cambiaría, no toca nada (recomendado correr primero).
- `--no-recursivo`: si no quieres que entre a subcarpetas.

---

## 2. `corregir_metadata.py` — Graba la fecha dentro del archivo (EXIF)

**Por qué es necesario:** la fecha de "modificación" de Windows es un dato externo al archivo — si mandas la foto por WhatsApp, la subes a una nube, o la pasas al teléfono, ese dato se puede perder o resetear. En cambio, la fecha guardada **dentro** del archivo (EXIF en fotos, metadata de contenedor en videos) viaja con el archivo a donde sea. Y lo más importante: **Google Fotos y la Galería de Android leen esta fecha interna primero**, no la del sistema de archivos.

**Requisito:** ExifTool (https://exiftool.org) — descomprime el zip y renombra `exiftool(-k).exe` a `exiftool.exe`.

**Uso:**
```
python corregir_metadata.py "C:\ruta\a\tu\carpeta" --exiftool "C:\ruta\exiftool.exe" --simular
python corregir_metadata.py "C:\ruta\a\tu\carpeta" --exiftool "C:\ruta\exiftool.exe" --silencioso
```

**Qué hace exactamente:** toma la fecha de modificación de cada archivo (ya corregida en el paso 1) y la escribe en todos los campos de fecha internos (`DateTimeOriginal`, `CreateDate`, metadata de video, etc.), usando `-AllDates<FileModifyDate`.

**Al terminar**, si hubo archivos que fallaron, genera automáticamente `errores_metadata.log` en la misma carpeta — ahí es donde entra el siguiente script.

---

## 3. `reparar_errores.py` — Repara los archivos que fallaron

Algunos archivos no se dejan escribir con el método normal. Este script lee `errores_metadata.log` y aplica una solución distinta según el tipo de error:

| Error en el log | Causa real | Cómo lo repara |
|---|---|---|
| `looks more like a RIFF` | Es un WebP guardado con extensión `.png`/`.jpg` | Renombra a `.webp` real, luego escribe la fecha |
| `Not a valid JPG (looks more like a PNG)` | Es un PNG guardado con extensión `.jpg` | Renombra a `.png` real, luego escribe la fecha |
| `Error reading OtherImageStart data in IFD0` | EXIF corrupto — muy común en fotos guardadas con **Paint.NET** | Prueba 3 métodos en cascada: (1) quitar el thumbnail interno dañado, (2) quitar el bloque EXIF completo a nivel de bytes crudos **sin recomprimir la imagen** (cero pérdida de calidad), (3) como último recurso, reconstruir con Pillow (esto sí recomprime un poco) |
| Cualquier archivo no soportado (ej. PDF) | No es foto/video | Se ignora automáticamente |

**Requisito adicional:**
```
pip install Pillow
```

**Uso:**
```
python reparar_errores.py "C:\ruta\errores_metadata.log" --exiftool "C:\ruta\exiftool.exe"
```

Al final imprime qué método reparó cada archivo, y un resumen: `X reparados, Y ignorados, Z fallidos`.

---

## 4. `transferir_con_fechas.py` — Copia al teléfono y corrige la fecha ahí también

**Por qué es necesario:** ni `adb push` ni la transferencia por cable USB (MTP) preservan la fecha de modificación original — el teléfono le pone la fecha del momento de la transferencia. Este script copia los archivos y **además** corrige la fecha directamente en el dispositivo usando `touch -t` vía `adb shell`.

**Requisito:** Android Platform Tools (`adb`) — https://developer.android.com/tools/releases/platform-tools

### Preparar el teléfono (una sola vez)
1. Activa Opciones de desarrollador: Ajustes > Acerca del teléfono > toca 7 veces "Número de compilación".
2. Dentro de Opciones de desarrollador, activa **Depuración USB**.
3. Conecta el cable y acepta el permiso que aparece en el teléfono.
4. Verifica la conexión:
```
adb devices -l
```
Si aparece tu teléfono en la lista (con su ID de serie), ya estás listo — no hace falta `adb connect` (eso es solo para conexión inalámbrica, y más lenta).

Si tienes **más de un dispositivo conectado**, usa `-s ID_DE_SERIE` en todos los comandos para especificar cuál.

### Uso básico
**Almacenamiento interno:**
```
python transferir_con_fechas.py --serial TU_ID "C:\ruta\local\DCIM=/sdcard/DCIM"
```
**Tarjeta SD** (reemplaza `0643-E789` por el identificador real de tu SD, ver sección C más abajo):
```
python transferir_con_fechas.py --serial TU_ID "C:\ruta\local\DCIM=/storage/0643-E789/DCIM"
```
Puedes pasar varias carpetas de una vez, separadas por espacio, cada una en formato `origen=destino` — y puedes mezclar destinos internos y de SD en la misma llamada si quieres.

### Banderas importantes
| Bandera | Para qué sirve |
|---|---|
| `--usar-creacion` | Usa la fecha de **creación** del archivo en vez de la de modificación (ver sección de InstaPrime más abajo) |
| `--solo-fechas` | No vuelve a copiar el archivo, solo aplica el `touch` de fecha (usar solo si el contenido ya está bien en el teléfono y nada más falta corregir la fecha) |

⚠️ **Ojo con `--solo-fechas`:** si corriges el EXIF en la laptop *después* de haber hecho el push, `--solo-fechas` NO vuelve a subir el archivo corregido — solo toca la fecha externa. En ese caso necesitas correr sin esa bandera para que se re-suba el contenido actualizado.

---

## Casos especiales

### A) Carpetas que no son de tu cámara (ej. `InstaPrime`, descargas de apps)

En estas carpetas, la fecha de **modificación** no es la real (refleja cuándo se descargó/sincronizó el archivo), sino que la fecha correcta está en la **fecha de creación** (o en el nombre del archivo, ej. `usuario-20260504-0001.jpg` = 4 de mayo 2026).

**Antes de transferir**, graba la fecha de creación en el EXIF de esa carpeta específica:
```
& "C:\ruta\exiftool.exe" "-AllDates<FileCreateDate" -overwrite_original -m -r -ext jpg -ext jpeg -ext png -ext mp4 -ext mov "C:\ruta\InstaPrime"
```

Y al transferir, usa la bandera `--usar-creacion`:

**Almacenamiento interno:**
```
python transferir_con_fechas.py --serial TU_ID --usar-creacion "C:\ruta\InstaPrime=/sdcard/InstaPrime"
```
**Tarjeta SD:**
```
python transferir_con_fechas.py --serial TU_ID --usar-creacion "C:\ruta\InstaPrime=/storage/0643-E789/InstaPrime"
```

### B) `adb push` duplica la carpeta si el destino ya existe

Si el destino (ej. `/sdcard/DCIM`) **ya existe** en el teléfono, `adb push` no fusiona el contenido — mete tu carpeta completa adentro, creando un anidado tipo `/sdcard/DCIM/DCIM/...`. Pasa igual con `Pictures`, `Movies`, o cualquier carpeta que el teléfono ya tenga creada de antes.

**Cómo evitarlo / arreglarlo:**
- Si ya pasó, hay que mover manualmente el contenido de la carpeta duplicada al nivel correcto y borrar la vacía, vía `adb shell`.
- Para prevenirlo, revisa primero si la carpeta destino ya existe (`adb shell ls /sdcard/`) antes de decidir la ruta exacta a usar.

### C) Tarjeta SD en vez de almacenamiento interno

Si tu teléfono tiene microSD y quieres guardar ahí en vez de en `/sdcard` interno:

**Paso 1 — Encuentra la ruta de la SD:**
```
adb -s TU_ID shell ls /storage
```
(vas a ver algo como `0643-E789`, ese es el identificador de tu tarjeta)

**Paso 2 — Usa esa ruta como destino:**
```
python transferir_con_fechas.py --serial TU_ID --usar-creacion "C:\ruta\local\Carpeta=/storage/0643-E789/Pictures"
```

**Paso 3 — Fuerza el reescaneo** 

Para una carpeta específica:

**Almacenamiento interno:**
```
adb -s TU_ID shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/Pictures"
```
**Tarjeta SD:**
```
adb -s TU_ID shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///storage/0643-E789/Pictures"
```

### D) Pasar archivos ZIP (sin descomprimir)

Para un ZIP no hace falta el script de fechas, un `push` directo basta:
```
adb -s TU_ID push "C:\ruta\archivo.zip" /sdcard/DCIM/
```
o a la SD:
```
adb -s TU_ID push "C:\ruta\archivo.zip" /storage/0643-E789/DCIM/
```

⚠️ **Nota importante sobre las fotos dentro de un ZIP:** el `push` solo interactúa con el archivo contenedor (`.zip`), no con lo que hay adentro. Si luego descomprimes el ZIP directamente en el teléfono, la mayoría de apps de Android van a crear las fotos con la fecha **del momento de la descompresión**, no la fecha real — provocando desorden en la Galería si esos archivos no tienen metadatos EXIF reales grabados de antemano. Si quieres que se organicen bien, mejor no las mandes comprimidas: pásalas sueltas con `transferir_con_fechas.py` para que conserven la fecha correcta.


---

## Forzar que Google Fotos/Galería vean el contenido nuevo

Después de copiar, Android no siempre se entera automáticamente de los archivos nuevos (a diferencia de MTP, `adb push` no dispara el aviso al escáner de medios).

**Opción rápida:** reinicia el teléfono — vuelve a escanear todo el almacenamiento al encender.

**Sin reiniciar,** fuerza el escaneo completo por comando (aplica a todo el almacenamiento, interno y SD, en un solo comando):
```
adb -s TU_ID shell content call --uri content://media/external/file --method scan_volume --arg external
```
O solo de una carpeta específica:
**Almacenamiento interno:**
```
adb -s TU_ID shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/Pictures"
```
**Tarjeta SD:**
```
adb -s TU_ID shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///storage/0643-E789/Pictures"
```

### Caso especial: Samsung Galaxy (One UI reciente, ej. A56)

En modelos recientes de Samsung, el menú "Almacenamiten de medios" para borrar caché ya no está disponible directamente por razones de seguridad de One UI. Si ya transferiste los archivos y las fechas están bien pero la Galería sigue sin mostrarlas bien, se puede forzar desde la terminal:

**Almacenamiento interno:**
```
adb -s TU_ID shell
cd /sdcard/DCIM/
touch -a *
find . -type f -exec touch -a {} +
exit
```
**Tarjeta SD:**
```
adb -s TU_ID shell
cd /storage/0643-E789/DCIM/
touch -a *
find . -type f -exec touch -a {} +
exit
```
(`find ... -exec touch -a {} +` recorre la carpeta y todas sus subcarpetas, igualando la fecha de "último acceso" a la de modificación de cada archivo, uno por uno)

Luego, en el teléfono:
1. Ajustes > Apps > Galería > Almacenamiento > **Borrar caché** > **Forzar detención**.
2. **Reinicia el teléfono** — al encender, One UI reindexa todo con las fechas correctas.

---

## Checklist final

- [ ] Corriste `corregir_fecha_creacion.py` sobre la carpeta completa
- [ ] Corriste `corregir_metadata.py` y revisaste `errores_metadata.log` si salió
- [ ] Corriste `reparar_errores.py` si hubo errores pendientes
- [ ] Para carpetas de apps (no-cámara), corriste el `exiftool -AllDates<FileCreateDate` aparte
- [ ] Transferiste con `transferir_con_fechas.py`, usando `--usar-creacion` donde corresponde
- [ ] Verificaste que el destino no duplicara carpetas (`adb shell ls`)
- [ ] Forzaste el reescaneo de medios (o reiniciaste el teléfono)
- [ ] Confirmaste en Google Fotos/Galería que la fecha ya sale bien
