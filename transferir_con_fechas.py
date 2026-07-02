"""
Transfiere carpetas al teléfono Android con `adb push` y, a diferencia de un
push normal, corrige la fecha de modificación de cada archivo en el
dispositivo para que coincida con la de la laptop.

Modificado para admitir /sdcard como destino base y auto-detectar la carpeta origen.
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

EXTENSIONES = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".webp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv"
}


def correr(cmd, **kwargs):
    return subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace", **kwargs)


def hacer_push(adb, serial, origen, destino):
    print(f"\n📤 Copiando: {origen}\n   -> {destino}")
    cmd = [adb]
    if serial:
        cmd += ["-s", serial]
    cmd += ["push", origen, destino]
    proceso = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
    for linea in proceso.stdout:
        print(f"\r{linea.strip()}", end="", flush=True)
    proceso.wait()
    print()
    return proceso.returncode == 0


def generar_script_touch(origen_local, destino_remoto, nombre_script_local, debug=False, usar_creacion=False):
    """Genera un script shell con comandos touch -t para cada archivo."""
    total = 0
    ejemplos = []
    
    # --- AQUÍ ESTÁ EL TRUCO ---
    # Extraemos el nombre de la carpeta origen (ej: "Movies", "Pictures", "DCIM")
    nombre_carpeta_origen = os.path.basename(origen_local)
    
    with open(nombre_script_local, "w", newline="\n", encoding="utf-8") as f:
        for raiz, _dirs, archivos in os.walk(origen_local):
            for nombre in archivos:
                ext = os.path.splitext(nombre)[1].lower()
                if ext not in EXTENSIONES:
                    continue
                ruta_local = os.path.join(raiz, nombre)
                rel = os.path.relpath(ruta_local, origen_local).replace("\\", "/")
                
                # Si el destino es exactamente /sdcard o /sdcard/, le sumamos el nombre de la carpeta origen
                if destino_remoto.rstrip('/') == "/sdcard":
                    ruta_remota = f"/sdcard/{nombre_carpeta_origen}/{rel}"
                else:
                    ruta_remota = f"{destino_remoto.rstrip('/')}/{rel}"

                timestamp = os.path.getctime(ruta_local) if usar_creacion else os.path.getmtime(ruta_local)
                fecha = datetime.fromtimestamp(timestamp)
                marca = fecha.strftime("%Y%m%d%H%M.%S")

                ruta_escapada = ruta_remota.replace("'", "'\\''")
                linea = f"touch -t {marca} '{ruta_escapada}'\n"
                f.write(linea)
                if len(ejemplos) < 3:
                    ejemplos.append(linea.strip())
                total += 1

    if debug and ejemplos:
        print("   Ejemplos de comandos de fecha generados (Verificando rutas):")
        for e in ejemplos:
            print(f"     {e}")

    return total


def main():
    parser = argparse.ArgumentParser(description="Transfiere carpetas al teléfono y corrige fechas.")
    parser.add_argument("pares", nargs="+", help="Pares 'origen_local=destino_remoto'")
    parser.add_argument("--serial", help="ID de serie del dispositivo", default=None)
    parser.add_argument("--adb", help="Ruta a adb.exe", default="adb")
    parser.add_argument("--solo-fechas", action="store_true", help="Solo corrige fechas")
    parser.add_argument("--usar-creacion", action="store_true", help="Usa la fecha de creación")
    args = parser.parse_args()

    for par in args.pares:
        if "=" not in par:
            print(f"Formato inválido, debe ser origen=destino: {par}")
            sys.exit(1)
        origen, destino = par.split("=", 1)
        origen = origen.rstrip("\\/")
        destino = destino.rstrip("/")

        if not os.path.isdir(origen):
            print(f"No existe la carpeta local: {origen}")
            continue

        if not args.solo_fechas:
            ok = hacer_push(args.adb, args.serial, origen, destino)
            if not ok:
                print(f"⚠️  El push de {origen} tuvo problemas.")

        print(f"\n🕒 Generando comandos de fecha para: {origen}")
        script_local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_fix_dates_tmp.sh")
        total = generar_script_touch(origen, destino, script_local, debug=True, usar_creacion=args.usar_creacion)
        print(f"   {total} archivo(s) a corregir.")

        if total == 0:
            os.remove(script_local)
            continue

        script_remoto = "/sdcard/_fix_dates_tmp.sh"
        cmd_push_script = [args.adb]
        if args.serial:
            cmd_push_script += ["-s", args.serial]
        cmd_push_script += ["push", script_local, script_remoto]
        r = correr(cmd_push_script)
        if r.returncode != 0:
            print(f"⚠️  No se pudo subir el script de fechas.")
            continue

        print("   Aplicando fechas en el teléfono...")
        cmd_run = [args.adb]
        if args.serial:
            cmd_run += ["-s", args.serial]
        cmd_run += ["shell", "sh", script_remoto]
        inicio = time.time()
        r = correr(cmd_run)
        duracion = time.time() - inicio
        print(f"   Salida completa del script en el teléfono:")
        print(f"   STDOUT: {r.stdout.strip()[:2000] if r.stdout.strip() else '(vacío)'}")
        print(f"   STDERR: {r.stderr.strip()[:2000] if r.stderr.strip() else '(vacío)'}")
        print(f"   Código de salida: {r.returncode}")
        print(f"   ✔ Terminado en {duracion:.1f}s")

        cmd_rm = [args.adb]
        if args.serial:
            cmd_rm += ["-s", args.serial]
        cmd_rm += ["shell", "rm", script_remoto]
        correr(cmd_rm)
        os.remove(script_local)

    print("\n✅ Proceso terminado.")


if __name__ == "__main__":
    main()