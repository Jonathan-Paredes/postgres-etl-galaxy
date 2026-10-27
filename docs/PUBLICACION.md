# Preparación para GitHub

## Qué publicar

Código Python revisado, README, docs, archivos de dependencias, plantilla de variables sin valores privados y, cuando exista, un ejemplo sintético mínimo.

## Qué excluir

Entornos virtuales, .env real, claves API, contraseñas, logs, caches, dumps, archivos Excel/CSV completos sin revisar y salidas de notebooks. `.gitignore` no elimina secretos ya incluidos en commits anteriores.

Se creó un paquete separado de publicación mediante lista explícita de archivos. No es una copia de toda la carpeta. Los originales y sus entornos se conservan. No se incluyeron .env.example.txt ni .gitignore.txt originales: se generaron plantillas nuevas.

## Antes de subir

1. Revisar el paquete y seleccionar nombre y visibilidad del repositorio.
2. Elegir licencia si se desea permitir reutilización.
3. Revisar git status y git diff --cached antes del commit.
4. Incorporar DDL, demo y resultados de pruebas cuando estén disponibles.
5. Publicar manteniendo visible el estado de desarrollo y las limitaciones.

La publicación inicial contiene el código y documentación de esta carpeta. Los resultados de ejecución y las pruebas pendientes se describen en VALIDACION.md. Si se descubre un secreto publicado anteriormente, revocarlo en el proveedor; borrarlo del archivo no basta.
