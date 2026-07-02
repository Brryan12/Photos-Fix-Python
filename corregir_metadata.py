"""
Corrige las fechas internas (EXIF / metadata) de fotos y videos usando ExifTool,
copiando la fecha de modificación del archivo hacia todos los campos de fecha
(DateTimeOriginal, CreateDate, QuickTime CreationDate, etc.).

Esto asegura que la fecha correcta se mantenga aunque luego transfieras
los archivos a tu teléfono (Google Fotos y la Galería leen estos metadatos,
no la fecha de creación del sistema de archivos).

Requisitos:
    1. Descargar ExifTool: https://exiftool.org
       - Descomprime el zip
       - Renombra "exiftool(-k).exe" a "exiftool.exe"
    2. Ya sea:
       a) Colocar exiftool.exe en el PATH del sistema, o
       b) Pasar la ruta completa con --exiftool "C:\\ruta\\exiftool.exe"

Uso:
    python corregir_metadata.py "C:\\ruta\\a\\tu\\carpeta"
    python corregir_metadata.py "C:\\ruta\\a\\tu\\carpeta" --exiftool "C:\\Tools\\exiftool.exe"
    python corregir_metadata.py "C:\\ruta\\a\\tu\\carpeta" --simular
"""

import argparse
import os
import shutil
import subprocess
import sys


def encontrar_exiftool(ruta_manual):
    if ruta_manual:
        if os.path.isfile(ruta_manual):
            return ruta_manual
        print(f"No se encontró exiftool en: {ruta_manual}")
        sys.exit(1)

    encontrado = shutil.which("exiftool") or shutil.which("exiftool.exe")
    if encontrado:
        return encontrado

    print("No se encontró 'exiftool' en el PATH.\n"
          "Descárgalo de https://exiftool.org, renómbralo a exiftool.exe,\n"
          "y vuelve a correr el script pasando --exiftool \"C:\\ruta\\exiftool.exe\"")
    sys.exit(1)


def contar_archivos(carpeta):
    total = 0
    extensiones = {
        ".jpg", ".jpeg", ".png", ".heic", ".webp", ".tiff", ".tif",
        ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv"
    }
    for _raiz, _dirs, archivos in os.walk(carpeta):
        for nombre in archivos:
            if os.path.splitext(nombre)[1].lower() in extensiones:
                total += 1
    return total


def limpiar_temporales(carpeta):
    """Borra archivos temporales que ExifTool deja si una corrida anterior se canceló a la mitad."""
    eliminados = 0
    for raiz, _dirs, archivos in os.walk(carpeta):
        for nombre in archivos:
            if nombre.endswith("_exiftool_tmp") or nombre.endswith("_original"):
                ruta = os.path.join(raiz, nombre)
                try:
                    os.remove(ruta)
                    eliminados += 1
                except Exception as e:
                    print(f"⚠️  No se pudo borrar {ruta}: {e}")
    if eliminados:
        print(f"Se limpiaron {eliminados} archivo(s) temporal(es) de una corrida anterior.\n")


def corregir_metadata(exiftool_path, carpeta, simular=False, silencioso=False):
    total = contar_archivos(carpeta)
    print(f"Archivos de foto/video encontrados: {total}\n")

    if total == 0:
        print("No hay archivos para procesar.")
        return

    extensiones_soportadas = [
        "jpg", "jpeg", "png", "heic", "webp", "tiff", "tif",
        "mp4", "mov", "avi", "mkv", "3gp", "m4v", "wmv"
    ]

    comando = [exiftool_path]
    for ext in extensiones_soportadas:
        comando += ["-ext", ext]
    comando += [
        "-AllDates<FileModifyDate",
        "-overwrite_original",
        "-m",
        "-r",
        "-progress",
        carpeta
    ]

    if silencioso:
        # -q oculta advertencias menores; -q -q también oculta errores no fatales
        comando.insert(1, "-q")
        comando.insert(1, "-q")

    if simular:
        print("[SIMULACIÓN] No se aplicarán cambios reales.\n")
        comando.remove("-overwrite_original")
        comando.insert(1, "-P")  # preserva fecha de modificación del archivo (no relevante en simulación real)
        # ExifTool no tiene un modo "dry run" nativo simple; para simular usamos -csv para previsualizar
        comando = [exiftool_path, "-csv", "-FileModifyDate", "-AllDates", "-r", carpeta]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        print(resultado.stdout)
        if resultado.stderr:
            print(resultado.stderr)
        print("\n(Simulación: arriba ves las fechas actuales. Corre sin --simular para aplicar los cambios.)")
        return

    print("Procesando con ExifTool...\n")
    proceso = subprocess.Popen(
        comando,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace"
    )

    errores = []
    for linea in proceso.stdout:
        linea = linea.strip()
        if not linea:
            continue
        if linea.startswith("Error:"):
            errores.append(linea)
            print(linea)  # siempre se muestra un error, aunque esté en modo silencioso
        elif not silencioso:
            print(f"\r{linea}", end="", flush=True)

    proceso.wait()
    print("\n\n¡Listo! Se corrigieron las fechas internas de los archivos.")

    if errores:
        log_path = os.path.join(carpeta, "errores_metadata.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Total de archivos con error: {len(errores)}\n\n")
            for linea in errores:
                f.write(linea + "\n")
        print(f"\n⚠️  {len(errores)} archivo(s) con error. Detalle guardado en:\n   {log_path}")

    if proceso.returncode != 0:
        print(f"\nNota: ExifTool terminó con código {proceso.returncode}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corrige fechas EXIF/metadata de fotos y videos con ExifTool.")
    parser.add_argument("carpeta", help="Ruta de la carpeta a procesar")
    parser.add_argument("--exiftool", help="Ruta completa a exiftool.exe (si no está en el PATH)", default=None)
    parser.add_argument("--simular", action="store_true", help="Solo mostrar las fechas actuales, sin modificar nada")
    parser.add_argument("--silencioso", action="store_true", help="Oculta advertencias y errores menores, solo muestra el progreso")
    args = parser.parse_args()

    if not os.path.isdir(args.carpeta):
        print("La carpeta indicada no existe.")
        sys.exit(1)

    exiftool_path = encontrar_exiftool(args.exiftool)
    limpiar_temporales(args.carpeta)
    corregir_metadata(exiftool_path, args.carpeta, simular=args.simular, silencioso=args.silencioso)
