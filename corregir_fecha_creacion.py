"""
Corrige la fecha de creación de fotos y videos en Windows,
poniéndola igual a la fecha de última modificación.

Requisitos:
    pip install pywin32

Uso:
    python corregir_fecha_creacion.py "C:\\ruta\\a\\tu\\carpeta"

Por defecto recorre subcarpetas también (recursivo).
"""

import os
import sys
import argparse
from datetime import datetime

try:
    import win32file
    import win32con
    import pywintypes
except ImportError:
    print("Falta la librería 'pywin32'. Instálala con:\n    pip install pywin32")
    sys.exit(1)

# Extensiones de fotos y videos que se procesarán
EXTENSIONES = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".webp", ".tiff",
    ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv"
}


def set_creation_time(path, new_datetime):
    """Cambia la fecha de creación de un archivo en Windows."""
    wintime = pywintypes.Time(new_datetime)
    handle = win32file.CreateFile(
        path,
        win32con.GENERIC_WRITE,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_ATTRIBUTE_NORMAL,
        None
    )
    try:
        win32file.SetFileTime(handle, wintime, None, None)  # solo creación
    finally:
        handle.close()


def procesar_carpeta(carpeta, recursivo=True, solo_simular=False):
    total = 0
    corregidos = 0

    if recursivo:
        caminador = os.walk(carpeta)
    else:
        caminador = [(carpeta, [], os.listdir(carpeta))]

    for raiz, _dirs, archivos in caminador:
        for nombre in archivos:
            ext = os.path.splitext(nombre)[1].lower()
            if ext not in EXTENSIONES:
                continue

            ruta = os.path.join(raiz, nombre)
            total += 1

            try:
                stats = os.stat(ruta)
                fecha_mod = datetime.fromtimestamp(stats.st_mtime)
                fecha_creacion_actual = datetime.fromtimestamp(stats.st_ctime)

                # Solo cambia si son distintas (con margen de 2 segundos)
                if abs((fecha_creacion_actual - fecha_mod).total_seconds()) > 2:
                    print(f"{'[SIMULACIÓN] ' if solo_simular else ''}"
                          f"{ruta}\n   Creación actual: {fecha_creacion_actual}"
                          f"\n   Nueva creación:  {fecha_mod}\n")
                    if not solo_simular:
                        set_creation_time(ruta, fecha_mod)
                    corregidos += 1
            except Exception as e:
                print(f"⚠️  Error con {ruta}: {e}")

    print(f"\nListo. Archivos revisados: {total}. Corregidos: {corregidos}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Iguala la fecha de creación a la de modificación en fotos/videos.")
    parser.add_argument("carpeta", help="Ruta de la carpeta a procesar")
    parser.add_argument("--no-recursivo", action="store_true", help="No entrar a subcarpetas")
    parser.add_argument("--simular", action="store_true", help="Solo mostrar qué cambiaría, sin modificar nada")
    args = parser.parse_args()

    if not os.path.isdir(args.carpeta):
        print("La carpeta indicada no existe.")
        sys.exit(1)

    procesar_carpeta(args.carpeta, recursivo=not args.no_recursivo, solo_simular=args.simular)
