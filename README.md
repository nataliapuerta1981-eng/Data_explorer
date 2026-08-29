# Explorador automático de datos

Aplicación web desarrollada con Streamlit para cargar archivos tabulares y ejecutar automáticamente un análisis exploratorio de datos. No utiliza datasets predeterminados, rutas fijas ni almacenamiento permanente de los archivos cargados.

## Funcionalidades

- Carga de archivos desde el navegador.
- Limpieza de espacios en nombres de columnas y reconocimiento prudente de fechas.
- Filtros por fecha, categoría y rango numérico.
- Indicadores de filas, columnas, duplicados y celdas faltantes.
- Clasificación de variables por tipo Pandas y tipo analítico.
- Revisión de duplicados, faltantes y estadísticas descriptivas.
- Histogramas, diagramas de caja y gráficos de frecuencia con Plotly.
- Correlaciones de Pearson, Spearman y Kendall.
- Detección de valores atípicos con el método IQR.
- Tabla interactiva y selección de columnas visibles.
- Descarga en CSV UTF-8 con BOM de datos filtrados y valores atípicos.

## Formatos admitidos

- CSV
- XLSX, leído con `openpyxl`
- XLS, leído con `xlrd`

## Estructura del repositorio

```text
explorador-automatico-datos/
├── app.py
├── requirements.txt
└── README.md
```

No se incluye ningún dataset.

## Instalación

Se recomienda Python 3.12.

```bash
python -m venv .venv
```

En Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

En macOS o Linux:

```bash
source .venv/bin/activate
```

Instala las dependencias:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecución local

Desde la raíz del proyecto:

```bash
streamlit run app.py
```

Streamlit abrirá la aplicación en el navegador. Si no lo hace, visita la URL local que aparezca en la terminal, normalmente `http://localhost:8501`.

## Despliegue en Streamlit Community Cloud

1. Crea un repositorio en GitHub.
2. Sube `app.py`, `requirements.txt` y `README.md` a la raíz.
3. Accede a `https://share.streamlit.io/` y conecta tu cuenta de GitHub.
4. Selecciona **Create app**.
5. Elige el repositorio, la rama y `app.py` como archivo de entrada.
6. En configuración avanzada, selecciona Python 3.12.
7. Pulsa **Deploy** y revisa los registros si ocurre un error.

La aplicación no requiere secretos ni variables de entorno.

## Privacidad y uso responsable

Los archivos se procesan en memoria durante la sesión. Evita cargar datos personales, confidenciales, regulados o sensibles. El análisis es exploratorio y no sustituye el criterio de una persona experta. Una correlación no implica causalidad y un valor atípico no necesariamente representa un error.

## Limitaciones conocidas

- Los archivos y análisis muy grandes pueden superar la memoria o los límites de recursos del servidor.
- La lectura de CSV intenta detectar automáticamente el delimitador; archivos irregulares pueden requerir una normalización previa.
- Solo se analiza la primera hoja de un archivo Excel.
- Las columnas cuyo nombre contiene `fecha` o `date` se convierten únicamente si al menos el 60 % de sus valores no nulos puede interpretarse como fecha.
- La clasificación entre categórica y texto usa una regla de cardinalidad y puede no coincidir con la semántica de todos los dominios.
- Kendall puede tardar más que Pearson o Spearman en datasets grandes.
- Un IQR igual a cero puede marcar como atípico cualquier valor distinto de los cuartiles.
