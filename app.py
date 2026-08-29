"""Aplicación Streamlit para análisis exploratorio automático de archivos tabulares."""

from __future__ import annotations

from io import BytesIO
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)

st.set_page_config(
    page_title="Explorador automático de datos",
    page_icon="📊",
    layout="wide",
)

PALABRAS_FECHA = ("fecha", "date")


@st.cache_data(show_spinner="Procesando archivo...")
def cargar_archivo(contenido: bytes, nombre_archivo: str) -> pd.DataFrame:
    """Lee el archivo en memoria y realiza normalizaciones estructurales mínimas."""
    extension = nombre_archivo.lower().rsplit(".", 1)[-1]
    buffer = BytesIO(contenido)

    if extension == "csv":
        try:
            df = pd.read_csv(buffer, sep=None, engine="python")
        except UnicodeDecodeError:
            buffer.seek(0)
            df = pd.read_csv(buffer, sep=None, engine="python", encoding="latin-1")
    elif extension == "xlsx":
        df = pd.read_excel(buffer, engine="openpyxl")
    elif extension == "xls":
        df = pd.read_excel(buffer, engine="xlrd")
    else:
        raise ValueError("Formato no admitido. Carga un archivo CSV, XLSX o XLS.")

    df.columns = [str(columna).strip() for columna in df.columns]
    for columna in df.columns:
        nombre = columna.casefold()
        if any(palabra in nombre for palabra in PALABRAS_FECHA):
            convertida = pd.to_datetime(df[columna], errors="coerce")
            valores_originales = int(df[columna].notna().sum())
            valores_convertidos = int(convertida.notna().sum())
            # Evita convertir una columna si la mayoría de sus valores válidos no parecen fechas.
            if valores_originales == 0 or valores_convertidos / valores_originales >= 0.6:
                df[columna] = convertida
    return df


def tipo_analitico(serie: pd.Series) -> str:
    """Interpreta el propósito analítico sin alterar los datos."""
    if is_bool_dtype(serie):
        return "Booleana"
    if is_datetime64_any_dtype(serie):
        return "Fecha/hora"
    if is_numeric_dtype(serie):
        return "Numérica"
    no_nulos = serie.dropna()
    unicos = no_nulos.nunique()
    umbral = max(30, int(len(no_nulos) * 0.05))
    return "Categórica" if unicos <= umbral else "Texto"


def clasificar_columnas(df: pd.DataFrame) -> dict[str, list[str]]:
    grupos = {tipo: [] for tipo in ["Numérica", "Categórica", "Texto", "Booleana", "Fecha/hora"]}
    for columna in df.columns:
        grupos[tipo_analitico(df[columna])].append(columna)
    return grupos


def resumen_tipos(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Variable": df.columns,
            "Tipo Pandas": [str(df[c].dtype) for c in df.columns],
            "Tipo analítico": [tipo_analitico(df[c]) for c in df.columns],
            "Valores no nulos": [int(df[c].notna().sum()) for c in df.columns],
            "Valores únicos": [int(df[c].nunique(dropna=True)) for c in df.columns],
        }
    )


def csv_descargable(df: pd.DataFrame) -> bytes:
    """Genera un CSV UTF-8 con BOM directamente en memoria."""
    return df.to_csv(index=False).encode("utf-8-sig")


def aplicar_filtros(df: pd.DataFrame, grupos: dict[str, list[str]]) -> pd.DataFrame:
    """Construye controles laterales y devuelve una copia filtrada."""
    filtrado = df.copy()
    st.sidebar.divider()
    st.sidebar.header("Filtros interactivos")
    st.sidebar.caption("Los valores faltantes se conservan en filtros numéricos y de fecha.")

    if grupos["Fecha/hora"]:
        with st.sidebar.expander("Filtros por fecha"):
            for columna in grupos["Fecha/hora"]:
                serie = df[columna]
                validas = serie.dropna()
                if validas.empty:
                    st.caption(f"{columna}: sin fechas válidas.")
                    continue
                minimo, maximo = validas.min().date(), validas.max().date()
                rango = st.date_input(
                    f"Rango de {columna}",
                    value=(minimo, maximo),
                    min_value=minimo,
                    max_value=maximo,
                    key=f"fecha_{columna}",
                )
                if isinstance(rango, (tuple, list)) and len(rango) == 2:
                    inicio = pd.Timestamp(rango[0])
                    fin = pd.Timestamp(rango[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
                    actual = filtrado[columna]
                    filtrado = filtrado[actual.isna() | actual.between(inicio, fin)]

    candidatas_cat = grupos["Categórica"] + grupos["Booleana"]
    seleccion_cat = st.sidebar.multiselect(
        "Variables categóricas para filtrar", candidatas_cat, key="seleccion_cat"
    )
    for columna in seleccion_cat:
        opciones = df[columna].dropna().unique().tolist()
        opciones = sorted(opciones, key=lambda valor: str(valor))
        elegidas = st.sidebar.multiselect(
            f"Categorías de {columna}", opciones, default=opciones, key=f"cat_{columna}"
        )
        if elegidas:
            filtrado = filtrado[filtrado[columna].isin(elegidas)]
        else:
            filtrado = filtrado.iloc[0:0]

    seleccion_num = st.sidebar.multiselect(
        "Variables numéricas para filtrar", grupos["Numérica"], key="seleccion_num"
    )
    for columna in seleccion_num:
        validos = pd.to_numeric(df[columna], errors="coerce").dropna()
        if validos.empty:
            st.sidebar.caption(f"{columna}: sin valores numéricos válidos.")
            continue
        minimo, maximo = float(validos.min()), float(validos.max())
        if np.isclose(minimo, maximo):
            st.sidebar.caption(f"{columna}: valor constante ({minimo:g}).")
            continue
        rango = st.sidebar.slider(
            f"Rango de {columna}",
            min_value=minimo,
            max_value=maximo,
            value=(minimo, maximo),
            key=f"num_{columna}",
        )
        serie = pd.to_numeric(filtrado[columna], errors="coerce")
        filtrado = filtrado[serie.isna() | serie.between(rango[0], rango[1])]

    st.sidebar.metric("Registros resultantes", f"{len(filtrado):,}")
    return filtrado


def detectar_atipicos(
    df: pd.DataFrame, columnas: list[str], factor: float
) -> pd.DataFrame:
    """Devuelve una fila por cada detección de atípico mediante IQR."""
    resultados: list[pd.DataFrame] = []
    for columna in columnas:
        serie = pd.to_numeric(df[columna], errors="coerce")
        validos = serie.dropna()
        if validos.empty:
            continue
        q1, q3 = validos.quantile([0.25, 0.75])
        iqr = q3 - q1
        inferior = q1 - factor * iqr
        superior = q3 + factor * iqr
        mascara = serie.notna() & ((serie < inferior) | (serie > superior))
        if mascara.any():
            detalle = df.loc[mascara].copy()
            detalle.insert(0, "Fila original", df.index[mascara])
            detalle.insert(1, "Variable atípica", columna)
            detalle.insert(2, "Valor detectado", serie.loc[mascara].to_numpy())
            detalle.insert(3, "Límite inferior", inferior)
            detalle.insert(4, "Límite superior", superior)
            resultados.append(detalle)
    if resultados:
        return pd.concat(resultados, ignore_index=True)
    columnas_salida = [
        "Fila original", "Variable atípica", "Valor detectado",
        "Límite inferior", "Límite superior", *df.columns.tolist()
    ]
    return pd.DataFrame(columns=columnas_salida)


st.title("📊 Explorador automático de datos")
st.write(
    "Carga un archivo tabular para explorar su estructura, calidad, estadísticas, "
    "distribuciones, correlaciones y posibles valores atípicos sin modificar los datos originales."
)

st.sidebar.title("Carga y configuración")
archivo = st.sidebar.file_uploader(
    "Carga tu conjunto de datos", type=["csv", "xlsx", "xls"],
    help="Formatos admitidos: CSV, XLSX y XLS.",
)

if archivo is None:
    st.info("Para comenzar, carga un archivo desde la barra lateral.")
    col1, col2, col3 = st.columns(3)
    col1.markdown("### 1. Cargar\nSelecciona un archivo **CSV, XLSX o XLS** desde tu computador.")
    col2.markdown("### 2. Explorar\nAplica filtros y revisa los análisis generados automáticamente.")
    col3.markdown("### 3. Descargar\nExporta los datos filtrados y los valores atípicos detectados.")
    st.subheader("Análisis disponibles")
    st.markdown(
        "- Estructura, dimensiones y tipos de variables\n"
        "- Duplicados y valores faltantes\n"
        "- Estadísticas descriptivas\n"
        "- Distribuciones y diagramas de caja\n"
        "- Correlaciones\n"
        "- Detección de valores atípicos mediante IQR\n"
        "- Filtros y descarga de resultados"
    )
    st.warning(
        "Privacidad: evita cargar información personal, confidencial o sensible. "
        "Los datos se procesan durante la sesión de la aplicación."
    )
    st.stop()

try:
    datos = cargar_archivo(archivo.getvalue(), archivo.name)
except Exception as error:
    st.error(f"No fue posible procesar el archivo. Verifica su formato y contenido. Detalle: {error}")
    st.stop()

if datos.empty or len(datos.columns) == 0:
    st.warning("El archivo está vacío o no contiene una tabla utilizable.")
    st.stop()

st.sidebar.success(f"Archivo cargado: {archivo.name}")
grupos_originales = clasificar_columnas(datos)
df = aplicar_filtros(datos, grupos_originales)

if df.empty:
    st.warning("Los filtros no producen registros. Ajusta los filtros de la barra lateral.")
    st.stop()

grupos = clasificar_columnas(df)

st.subheader("Indicadores generales")
metrica1, metrica2, metrica3, metrica4 = st.columns(4)
metrica1.metric("Filas", f"{df.shape[0]:,}")
metrica2.metric("Columnas", f"{df.shape[1]:,}")
metrica3.metric("Duplicados completos", f"{int(df.duplicated().sum()):,}")
metrica4.metric("Celdas faltantes", f"{int(df.isna().sum().sum()):,}")

st.caption(f"Archivo: **{archivo.name}** | Dimensiones filtradas: **{df.shape[0]} filas × {df.shape[1]} columnas**")

pestanas = st.tabs([
    "Resumen y tipos", "Calidad de datos", "Estadísticas", "Distribuciones",
    "Correlaciones", "Valores atípicos", "Tabla ordenable",
])

with pestanas[0]:
    st.subheader("Dimensiones y tipos de variables")
    c1, c2, c3 = st.columns(3)
    c1.metric("Cantidad de filas", df.shape[0])
    c2.metric("Cantidad de columnas", df.shape[1])
    c3.metric("Archivo", archivo.name)
    st.dataframe(resumen_tipos(df), use_container_width=True, hide_index=True)
    st.caption(
        "La clasificación analítica distingue variables numéricas, categóricas, de texto, "
        "booleanas y de fecha/hora; no modifica el contenido original."
    )

with pestanas[1]:
    st.subheader("Registros duplicados")
    cantidad_duplicados = int(df.duplicated().sum())
    st.metric("Filas duplicadas adicionales", cantidad_duplicados)
    involucrados = df[df.duplicated(keep=False)]
    if involucrados.empty:
        st.success("No se encontraron registros completamente duplicados.")
    else:
        st.write(f"Registros involucrados en grupos duplicados: {len(involucrados):,}")
        st.dataframe(involucrados, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Valores faltantes")
    faltantes = pd.DataFrame({
        "Variable": df.columns,
        "Valores faltantes": df.isna().sum().values,
        "Porcentaje faltante": (df.isna().mean().values * 100),
    }).sort_values("Valores faltantes", ascending=False)
    st.dataframe(
        faltantes.style.format({"Porcentaje faltante": "{:.2f}%"}),
        use_container_width=True, hide_index=True,
    )
    grafico_faltantes = px.bar(
        faltantes, x="Variable", y="Porcentaje faltante",
        title="Porcentaje de valores faltantes por variable",
        labels={"Porcentaje faltante": "Porcentaje (%)"},
    )
    st.plotly_chart(grafico_faltantes, use_container_width=True)

with pestanas[2]:
    st.subheader("Estadísticas descriptivas")
    alcance = st.radio(
        "Variables a incluir",
        ["Todas las variables", "Solo variables numéricas", "Solo variables categóricas"],
        horizontal=True,
    )
    try:
        if alcance in ("Todas las variables", "Solo variables numéricas"):
            st.markdown("#### Variables numéricas")
            if not grupos["Numérica"]:
                st.info("El dataset filtrado no contiene variables numéricas.")
            else:
                numericas = df[grupos["Numérica"]].describe().T
                numericas = numericas.rename(columns={
                    "count": "Conteo", "mean": "Media", "std": "Desviación estándar",
                    "min": "Mínimo", "25%": "Primer cuartil", "50%": "Mediana",
                    "75%": "Tercer cuartil", "max": "Máximo",
                })
                st.dataframe(numericas, use_container_width=True)
        if alcance in ("Todas las variables", "Solo variables categóricas"):
            st.markdown("#### Variables categóricas")
            categoricas = grupos["Categórica"] + grupos["Texto"] + grupos["Booleana"]
            if not categoricas:
                st.info("El dataset filtrado no contiene variables categóricas o de texto.")
            else:
                resumen_cat = df[categoricas].describe(include="all").T
                disponibles = [c for c in ["count", "unique", "top", "freq"] if c in resumen_cat.columns]
                resumen_cat = resumen_cat[disponibles].rename(columns={
                    "count": "Conteo", "unique": "Valores únicos",
                    "top": "Categoría más frecuente", "freq": "Frecuencia dominante",
                })
                st.dataframe(resumen_cat, use_container_width=True)
    except Exception as error:
        st.error(f"No fue posible calcular las estadísticas seleccionadas: {error}")

with pestanas[3]:
    st.subheader("Distribuciones")
    variables_distribucion = grupos["Numérica"] + grupos["Categórica"] + grupos["Texto"] + grupos["Booleana"]
    if not variables_distribucion:
        st.info("No hay variables compatibles para visualizar distribuciones.")
    else:
        variable = st.selectbox("Selecciona una variable", variables_distribucion)
        if variable in grupos["Numérica"]:
            intervalos = st.slider("Número de intervalos", 5, 100, 30)
            histograma = px.histogram(df, x=variable, nbins=intervalos, title=f"Histograma de {variable}")
            st.plotly_chart(histograma, use_container_width=True)
            candidatas_grupo = [None] + grupos["Categórica"] + grupos["Booleana"]
            grupo = st.selectbox(
                "Agrupar diagrama de caja por", candidatas_grupo,
                format_func=lambda x: "Sin agrupación" if x is None else x,
            )
            caja = px.box(
                df, x=grupo, y=variable, points="outliers",
                title=f"Diagrama de caja de {variable}",
            )
            st.plotly_chart(caja, use_container_width=True)
        else:
            etiquetas = df[variable].astype("string").fillna("(Faltante)")
            frecuencias = etiquetas.value_counts(dropna=False).head(30).rename_axis("Categoría").reset_index(name="Frecuencia")
            if etiquetas.nunique(dropna=False) > 30:
                st.info("Se muestran únicamente las 30 categorías más frecuentes.")
            barras = px.bar(
                frecuencias, x="Categoría", y="Frecuencia",
                title=f"Frecuencia de categorías en {variable}",
            )
            st.plotly_chart(barras, use_container_width=True)

with pestanas[4]:
    st.subheader("Correlaciones")
    if len(grupos["Numérica"]) < 2:
        st.info("Se requieren al menos dos variables numéricas para calcular correlaciones.")
    else:
        seleccion = st.multiselect(
            "Variables numéricas", grupos["Numérica"], default=grupos["Numérica"]
        )
        metodo_nombre = st.selectbox("Método", ["Pearson", "Spearman", "Kendall"])
        if len(seleccion) < 2:
            st.warning("Selecciona al menos dos variables numéricas.")
        else:
            matriz = df[seleccion].corr(method=metodo_nombre.lower())
            mapa = go.Figure(data=go.Heatmap(
                z=matriz.values, x=matriz.columns, y=matriz.index,
                zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
                text=np.round(matriz.values, 2), texttemplate="%{text}",
                hovertemplate="X: %{x}<br>Y: %{y}<br>Correlación: %{z:.3f}<extra></extra>",
            ))
            mapa.update_layout(title=f"Matriz de correlación de {metodo_nombre}")
            st.plotly_chart(mapa, use_container_width=True)
            st.dataframe(matriz.style.format("{:.3f}"), use_container_width=True)
            st.caption("Una correlación no implica causalidad.")

with pestanas[5]:
    st.subheader("Detección de valores atípicos por rango intercuartílico")
    if not grupos["Numérica"]:
        st.info("No hay variables numéricas para analizar.")
        atipicos = detectar_atipicos(df, [], 1.5)
    else:
        seleccion_atipicos = st.multiselect(
            "Variables numéricas", grupos["Numérica"], default=grupos["Numérica"]
        )
        factor = st.slider("Factor IQR", 1.0, 3.0, 1.5, 0.1)
        atipicos = detectar_atipicos(df, seleccion_atipicos, factor)
        st.metric("Detecciones de valores atípicos", len(atipicos))
        if atipicos.empty:
            st.success("No se detectaron valores atípicos con la configuración actual.")
        else:
            conteo = atipicos["Variable atípica"].value_counts().rename_axis("Variable").reset_index(name="Cantidad")
            figura_atipicos = px.bar(
                conteo, x="Variable", y="Cantidad", title="Valores atípicos por variable"
            )
            st.plotly_chart(figura_atipicos, use_container_width=True)
            st.dataframe(atipicos, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar valores atípicos", data=csv_descargable(atipicos),
            file_name="valores_atipicos.csv", mime="text/csv",
        )
        st.caption("Un valor atípico no necesariamente representa un error.")

with pestanas[6]:
    st.subheader("Tabla interactiva y ordenable")
    columnas_visibles = st.multiselect(
        "Selecciona las columnas visibles", df.columns.tolist(), default=df.columns.tolist()
    )
    if not columnas_visibles:
        st.info("Selecciona al menos una columna para mostrar la tabla.")
    else:
        st.dataframe(
            df[columnas_visibles], use_container_width=True, hide_index=True,
            height=520,
        )
    st.download_button(
        "Descargar datos filtrados", data=csv_descargable(df),
        file_name="datos_filtrados.csv", mime="text/csv",
    )

st.divider()
st.warning(
    "Tratamiento responsable: los datos se procesan durante la sesión. Evita cargar información "
    "personal, confidencial o sensible. Este análisis exploratorio no reemplaza la interpretación "
    "experta. Una correlación no implica causalidad y un valor atípico no necesariamente es un error."
)
