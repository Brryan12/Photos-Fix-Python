"""
Repara los archivos que quedaron en errores_metadata.log:
  - WebP guardado como .png/.jpg  -> renombra a .webp y escribe la fecha
  - PNG guardado como .jpg        -> renombra a .png y escribe la fecha
  - JPG con thumbnail interno corrupto (OtherImageStart) -> quita el thumbnail dañado y escribe la fecha
  - Cualquier archivo que no sea foto/video (ej. PDF) -> se ignora

Uso:
    python reparar_errores.py "C:\\ruta\\errores_metadata.log" --exiftool "C:\\ruta\\exiftool.exe"
"""

import argparse
import os
import re
import subprocess
import sys


def leer_log(log_path):
    entradas = []
    with open(log_path, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea.startswith("Error:"):
                continue
            m = re.match(r"Error: (.+?) - (.+)$", linea)
            if m:
                entradas.append((m.group(1), m.group(2)))
    return entradas


def firma_real(ruta):
    """Detecta el formato real del archivo por sus primeros bytes (firma mágica)."""
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(12)
    except Exception:
        return None
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "webp"
    if cabecera[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if cabecera[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def renombrar_segun_formato_real(ruta):
    real = firma_real(ruta)
    if not real:
        return None
    base, ext_actual = os.path.splitext(ruta)
    ext_actual = ext_actual.lower().lstrip(".")
    if real == ext_actual or (real == "jpg" and ext_actual in ("jpg", "jpeg")):
        return None  # ya coincide, no era un problema de extensión
    nueva_ruta = f"{base}.{real}"
    contador = 1
    while os.path.exists(nueva_ruta):
        nueva_ruta = f"{base}_{contador}.{real}"
        contador += 1
    os.rename(ruta, nueva_ruta)
    return nueva_ruta


def escribir_fecha(exiftool_path, ruta, quitar_thumbnail=False):
    comando = [exiftool_path, "-m", "-overwrite_original", "-AllDates<FileModifyDate"]
    if quitar_thumbnail:
        comando += ["-ThumbnailImage=", "-PreviewImage=", "-OtherImage="]
    comando.append(ruta)
    resultado = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = "1 image files updated" in resultado.stdout or "1 video files updated" in resultado.stdout
    return ok, (resultado.stdout + resultado.stderr).strip()


def quitar_exif_sin_perdida(ruta):
    """
    Elimina el segmento APP1 (EXIF) de un JPG directamente a nivel de bytes,
    sin decodificar ni recomprimir la imagen. Preserva el resto de la fecha
    de modificación original. Calidad 100% intacta porque nunca se toca
    la parte de datos de imagen comprimida (después del marcador SOS).
    """
    try:
        mtime_original = os.path.getmtime(ruta)
        atime_original = os.path.getatime(ruta)

        with open(ruta, "rb") as f:
            data = f.read()

        if data[:2] != b"\xff\xd8":
            return False, "No es un JPG válido (falta el marcador SOI)"

        resultado = bytearray(data[:2])  # SOI
        i = 2
        quitado = False

        while i < len(data) - 1:
            if data[i] != 0xFF:
                # Ya no estamos en zona de marcadores; copiar el resto tal cual
                resultado += data[i:]
                break

            marcador = data[i + 1]

            # SOS (inicio de datos de imagen): copiar todo lo que sigue sin tocar
            if marcador == 0xDA:
                resultado += data[i:]
                break

            # Marcadores sin longitud (SOI ya procesado, RST, TEM, EOI)
            if marcador in (0xD8, 0xD9) or (0xD0 <= marcador <= 0xD7) or marcador == 0x01:
                resultado += data[i:i + 2]
                i += 2
                continue

            # Marcador con longitud
            largo = int.from_bytes(data[i + 2:i + 4], "big")
            segmento = data[i:i + 2 + largo]

            # APP1 con cabecera "Exif" -> lo omitimos (esta es la parte dañada)
            if marcador == 0xE1 and segmento[4:10] == b"Exif\x00\x00":
                quitado = True
            else:
                resultado += segmento

            i += 2 + largo

        if not quitado:
            return False, "No se encontró un segmento EXIF que quitar"

        with open(ruta, "wb") as f:
            f.write(resultado)

        os.utime(ruta, (atime_original, mtime_original))
        return True, "EXIF corrupto eliminado sin recomprimir (calidad intacta)"

    except Exception as e:
        return False, str(e)


def reparar_con_pillow(ruta):
    """Reconstruye el JPG descartando el EXIF corrupto, preservando la fecha de modificación original."""
    try:
        from PIL import Image
    except ImportError:
        return False, "Falta instalar Pillow: pip install Pillow"

    try:
        mtime_original = os.path.getmtime(ruta)
        atime_original = os.path.getatime(ruta)

        img = Image.open(ruta)
        img.load()
        img.save(ruta, format="JPEG", quality=95, exif=b"")

        os.utime(ruta, (atime_original, mtime_original))
        return True, "Imagen reconstruida sin el EXIF dañado"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Repara archivos listados en errores_metadata.log")
    parser.add_argument("log", help="Ruta al archivo errores_metadata.log")
    parser.add_argument("--exiftool", required=True, help="Ruta completa a exiftool.exe")
    args = parser.parse_args()

    if not os.path.isfile(args.log):
        print("No se encontró el archivo de log.")
        sys.exit(1)
    if not os.path.isfile(args.exiftool):
        print("No se encontró exiftool en la ruta indicada.")
        sys.exit(1)

    entradas = leer_log(args.log)
    print(f"Archivos a intentar reparar: {len(entradas)}\n")

    reparados, ignorados, fallidos = 0, 0, 0

    for motivo, ruta in entradas:
        ruta = ruta.strip()
        if not os.path.isfile(ruta):
            print(f"[Omitido] No existe: {ruta}")
            ignorados += 1
            continue

        ext = os.path.splitext(ruta)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            # No es un formato de imagen que sepamos reparar (ej. PDF) -> se ignora
            print(f"[Ignorado - no es imagen soportada] {ruta}")
            ignorados += 1
            continue

        metodo = None
        if "RIFF" in motivo or "looks more like a PNG" in motivo or "looks more like a JPG" in motivo:
            metodo = "renombrado a extensión real"
            nueva_ruta = renombrar_segun_formato_real(ruta)
            if nueva_ruta:
                print(f"Renombrado: {ruta}\n         -> {nueva_ruta}")
                ruta = nueva_ruta
            ok, salida = escribir_fecha(args.exiftool, ruta)
        elif "OtherImageStart" in motivo:
            metodo = "quitar thumbnail interno"
            ok, salida = escribir_fecha(args.exiftool, ruta, quitar_thumbnail=True)
            if not ok:
                metodo = "quitar EXIF completo sin pérdida (bytes crudos)"
                ok_sp, salida_sp = quitar_exif_sin_perdida(ruta)
                if ok_sp:
                    ok, salida = escribir_fecha(args.exiftool, ruta)
                if not ok:
                    metodo = "reconstrucción con Pillow (recomprimido)"
                    ok_pillow, salida_pillow = reparar_con_pillow(ruta)
                    if ok_pillow:
                        ok, salida = escribir_fecha(args.exiftool, ruta)
                        salida = "(recomprimido con Pillow) " + salida
                    else:
                        salida = salida_pillow
        else:
            print(f"[Ignorado - error no reconocido: {motivo}] {ruta}")
            ignorados += 1
            continue

        if ok:
            extra = f" [método: {metodo}]" if metodo else ""
            print(f"✔ Reparado: {ruta}{extra}")
            reparados += 1
        else:
            print(f"✘ No se pudo reparar: {ruta}\n   {salida}")
            fallidos += 1

    print(f"\nResumen: {reparados} reparados, {ignorados} ignorados, {fallidos} fallidos.")


if __name__ == "__main__":
    main()
