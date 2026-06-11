import streamlit as st
import pandas as pd
import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import time

# --- 1. CONFIGURACIÓN DEL ENTORNO Y CONSTANTES ---
# Se agregó initial_sidebar_state="collapsed" para que el menú inicie cerrado
st.set_page_config(page_title="Gestor de Pedidos - COMPARADOR", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
st.title("📊 Control Consolidado - Unidades y Valores NY")

LISTA_SEDES = ["OLIVOS", "BAZAR", "SAN JACINTO", "HATICOS", "CUMBRES", "COROMOTO"]
# Reemplaza la línea que tienes por esta:
ORDEN_COLUMNAS = ["Droguería", "Total Compra", "Total Artículos", "Total Unidades", "% Part. Dólares", "% Part. Unidades"]

# MEMORIA DEL PERFIL (Recordar la Sede)
if "sede_seleccionada" not in st.session_state:
    st.session_state.sede_seleccionada = LISTA_SEDES[0]

def actualizar_sede():
    st.session_state.sede_seleccionada = st.session_state.sede_widget

# --- 2. INICIALIZACIÓN DE FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

try:
    db = init_firebase()
except Exception as e:
    st.error(f"Error de conexión con Firebase: {e}")
    db = None

# --- CONTROL AVANZADO DE LABORATORIOS (AÑADIR / OCULTAR / ELIMINAR) ---
def obtener_laboratorios(solo_visibles=False):
    if db:
        try:
            docs = db.collection("configuracion_laboratorios").stream()
            labs = []
            for doc in docs:
                data = doc.to_dict()
                es_visible = data.get("visible", True)
                if solo_visibles:
                    if es_visible:
                        labs.append(data["nombre"])
                else:
                    labs.append(data["nombre"])
            if labs:
                return sorted(list(set(labs)))
        except:
            pass
    return []

def guardar_laboratorio(nombre):
    if db and nombre:
        doc_id = nombre.strip().lower().replace(" ", "_")
        db.collection("configuracion_laboratorios").document(doc_id).set({
            "nombre": nombre.strip().upper(),
            "visible": True
        })

def cambiar_visibilidad_laboratorio(nombre, visible):
    if db and nombre:
        doc_id = nombre.strip().lower().replace(" ", "_")
        db.collection("configuracion_laboratorios").document(doc_id).update({"visible": visible})

def eliminar_laboratorio_db(nombre):
    if db and nombre:
        doc_id = nombre.strip().lower().replace(" ", "_")
        db.collection("configuracion_laboratorios").document(doc_id).delete()


# --- FORMATO VENEZOLANO ---
def formato_ve(valor, es_porcentaje=False, es_unidad=False):
    if pd.isna(valor) or valor == "": 
        return "0" if es_unidad else "0,00"
    try:
        v = float(valor)
        if es_porcentaje:
            # Se eliminó la multiplicación extra por 100 para evitar que se disparen los números
            texto = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{texto} %"
        elif es_unidad:
            return f"{int(round(v)):,}".replace(",", ".")
        else:
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

# --- ESTILOS OSCUROS Y RESALTADO DE FILA ---
def estilar_tabla_oscura(df_datos, formatters):
    df_styled = df_datos.style.format(formatters).set_properties(**{
        'border': '1px solid #3a3a3a', 
        'color': '#ffffff',
        'background-color': '#111111'
    })
    
    # Efecto visual para que la fila completa brille al pasar el mouse
    df_styled = df_styled.set_table_styles([
        {'selector': 'tr:hover td', 'props': [('background-color', '#2c3e50')]}
    ], overwrite=False)

    def destacar_ganador_oscuro(s):
        is_max = s == s.max()
        return ['background-color: #0e3a1d; color: #52d681; font-weight: bold; border: 1px solid #10b981;' if v else '' for v in is_max]
    
    columnas_part = [c for c in df_datos.columns if '% Part.' in str(c)]
    if columnas_part:
        df_styled = df_styled.apply(destacar_ganador_oscuro, subset=columnas_part)
    return df_styled

# --- 3. MENÚ DE NAVEGACIÓN ---
opcion = st.sidebar.radio("Seleccione una opción:", ["Cargar Excel", "Ver Reportes", "Consolidado Total"])

# ==========================================
# VISTA: CARGAR EXCEL
# ==========================================
if opcion == "Cargar Excel":
    st.header("📥 Carga de Pedidos desde EXCEL")
    
    # Aquí solo mostramos los laboratorios que están "Visibles"
    labs_disponibles = obtener_laboratorios(solo_visibles=True)

    col1, col2 = st.columns(2)
    with col1:
        sede_input = st.selectbox(
            "Seleccione la Sede / Sucursal:", 
            LISTA_SEDES,
            index=LISTA_SEDES.index(st.session_state.sede_seleccionada),
            key="sede_widget",
            on_change=actualizar_sede
        )
    with col2:
        if not labs_disponibles:
            st.info("No hay laboratorios activos. Habilita o crea uno en 'Ver Reportes'.")
            laboratorio_input = ""
        else:
            laboratorio_input = st.selectbox("Seleccione el Laboratorio:", labs_disponibles)

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    uploaded_file = st.file_uploader("Seleccionar archivo (.xlsm / .xlsx)", type=["xlsx", "xlsm"], key=f"uploader_{st.session_state.uploader_key}")

    if uploaded_file is not None and laboratorio_input != "":
        doc_id_verificar = f"{sede_input.lower().replace(' ', '_')}_{laboratorio_input.lower().replace(' ', '_')}"
        esta_bloqueado = False
        if db:
            esta_bloqueado = db.collection("reportes_comparador").document(doc_id_verificar).get().exists

        if esta_bloqueado:
            st.error(f"🚫 **Acceso Denegado:** Los datos de **{sede_input}** para **{laboratorio_input}** ya fueron cargados. Elimínalos en 'Ver Reportes' para volver a cargar.")
        else:
            try:
                progreso = st.progress(0, text="Iniciando lectura...")
                xls = pd.ExcelFile(uploaded_file, engine='openpyxl')
                
                hoja_objetivo = next((h for h in xls.sheet_names if "TABLA" in h.strip().upper()), None)
                if not hoja_objetivo:
                    st.error("❌ No se encontró ninguna hoja llamada 'TABLA'.")
                    progreso.empty()
                    st.stop()

                df_full = pd.read_excel(uploaded_file, sheet_name=hoja_objetivo, engine='openpyxl')
                df_full.dropna(how='all', inplace=True)
                df_full.dropna(axis=1, how='all', inplace=True) 

                # --- 1. RECORTE DE TOTALES (MÁS PRECISO) ---
                idx_recorte = len(df_full)
                for idx, row in df_full.iterrows():
                    # Escanea las primeras 3 columnas de la fila por si la palabra TOTAL está movida
                    row_str = " ".join([str(val).upper() for val in row.values[:3]])
                    if "TOTAL" in row_str:
                        idx_recorte = idx
                        break

                df_tabla = df_full.iloc[:idx_recorte].copy()
                df_tabla.dropna(how='all', inplace=True)

                # --- 2. IDENTIFICACIÓN ESTRICTA DE LAS 4 COLUMNAS ---
                c_usd, c_und, c_art = None, None, None
                for col in df_tabla.columns[1:]:
                    c_lower = str(col).lower().strip()
                    if 'compra' in c_lower or 'dolar' in c_lower or '$' in c_lower: c_usd = col
                    elif 'art' in c_lower: c_art = col
                    elif 'unid' in c_lower: c_und = col

                # Si el Excel tiene nombres extraños, forzamos por posición (Col 1=Compra, Col 2=Artículos, Col 3=Unidades)
                if not c_usd and len(df_tabla.columns) > 1: c_usd = df_tabla.columns[1]
                if not c_art and len(df_tabla.columns) > 2: c_art = df_tabla.columns[2]
                if not c_und and len(df_tabla.columns) > 3: c_und = df_tabla.columns[3]

                rename_dict = {df_tabla.columns[0]: "Droguería"}
                if c_usd: rename_dict[c_usd] = "Total Compra"
                if c_art: rename_dict[c_art] = "Total Artículos"
                if c_und: rename_dict[c_und] = "Total Unidades"
                
                df_tabla.rename(columns=rename_dict, inplace=True)
                df_tabla = df_tabla.loc[:, ~df_tabla.columns.duplicated(keep='last')]

                # --- 3. LIMPIEZA BLINDADA DE NÚMEROS ---
                # Elimina símbolos y convierte el formato "1.500,50" a un número real matemático
                def limpiar_numero(x):
                    if isinstance(x, str): 
                        x = x.replace('$', '').replace('USD', '').strip()
                        return x.replace('.', '').replace(',', '.')
                    return x

                # Conversión INDEPENDIENTE (Eliminamos la regla que copiaba artículos en unidades)
                for col_req in ["Total Compra", "Total Artículos", "Total Unidades"]:
                    if col_req not in df_tabla.columns:
                        df_tabla[col_req] = 0
                    df_tabla[col_req] = pd.to_numeric(df_tabla[col_req].apply(limpiar_numero), errors='coerce').fillna(0)

                # --- 4. FILTRO FINAL ---
                df_tabla = df_tabla[df_tabla["Total Unidades"] > 0]

                if df_tabla.empty:
                    st.info("💡 Archivo vacío: No hay artículos con cantidades mayores a 0.")
                    progreso.empty()
                    st.stop()

                suma_real_dolares = df_tabla["Total Compra"].sum()
                suma_real_unidades = df_tabla["Total Unidades"].sum()

                df_tabla['% Part. Dólares'] = (df_tabla["Total Compra"] / suma_real_dolares * 100) if suma_real_dolares > 0 else 0
                df_tabla['% Part. Unidades'] = (df_tabla["Total Unidades"] / suma_real_unidades * 100) if suma_real_unidades > 0 else 0
                
                for col in ["Total Artículos", "Total Unidades"]:
                    df_tabla[col] = np.floor(df_tabla[col] + 0.5).astype(int)

                # Filtro estricto: Elimina cualquier columna basura que no esté en la lista oficial
                columnas_finales = [c for c in ORDEN_COLUMNAS if c in df_tabla.columns]
                df_tabla = df_tabla[columnas_finales]
                
                formatters = {}
                for col in df_tabla.columns:
                    col_str = str(col).lower()
                    if col == "Droguería": continue
                    elif 'part.' in col_str or '%' in col_str: formatters[col] = lambda x: formato_ve(x, es_porcentaje=True)
                    elif 'unidades' in col_str or 'artículos' in col_str: formatters[col] = lambda x: formato_ve(x, es_unidad=True)
                    else: formatters[col] = lambda x: formato_ve(x)

                df_styled = estilar_tabla_oscura(df_tabla, formatters)
                progreso.empty()

                st.subheader(f"📋 Vista Operativa: {laboratorio_input}")
                
                # selection_mode="multi-row" permite dar clic para seleccionar la fila completa
                try:
                    st.dataframe(df_styled, use_container_width=True, selection_mode="multi-row")
                except:
                    st.dataframe(df_styled, use_container_width=True)

                st.divider()
                st.markdown("### 📌 Totales de la Orden Cargada")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown(f"""<div style="background-color:#14231c; padding:20px; border-radius:10px; border-left:6px solid #10b981; text-align:center;"><span style="color:#a3cfbb; font-size:14px; font-weight:bold;">💵 Total Compra</span><br><span style="color:#52d681; font-size:36px; font-weight:900;">$ {formato_ve(suma_real_dolares)}</span></div>""", unsafe_allow_html=True)
                with col_c2:
                    st.markdown(f"""<div style="background-color:#101f30; padding:20px; border-radius:10px; border-left:6px solid #0d6efd; text-align:center;"><span style="color:#9ec5fe; font-size:14px; font-weight:bold;">📦 Total Unidades</span><br><span style="color:#6ea8fe; font-size:36px; font-weight:900;">{formato_ve(suma_real_unidades, es_unidad=True)}</span></div>""", unsafe_allow_html=True)

                st.write("")
                
                lab_limpio = laboratorio_input.lower().replace(" ", "")
                archivo_limpio = uploaded_file.name.lower().replace(" ", "")
                
                permitir_guardado = True
                if lab_limpio not in archivo_limpio:
                    st.warning(f"⚠️ **Advertencia:** El nombre del archivo (`{uploaded_file.name}`) no parece coincidir con el laboratorio elegido (`{laboratorio_input}`).")
                    confirmar = st.checkbox(f"Sí, estoy seguro que deseo cargar estos datos como **{laboratorio_input}**", value=False)
                    if not confirmar:
                        permitir_guardado = False

                if permitir_guardado:
                    if st.button("Guardar", type="primary"):
                        if db is not None:
                            with st.spinner("Sincronizando..."):    
                                detalles_cuadro = df_tabla.to_dict(orient="records")
                                payload = {
                                    "sede": st.session_state.sede_seleccionada,
                                    "laboratorio": laboratorio_input,
                                    "total_dolares": float(suma_real_dolares),
                                    "total_unidades": int(round(suma_real_unidades)),
                                    "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "datos_cuadro": detalles_cuadro
                                }
                                db.collection("reportes_comparador").document(doc_id_verificar).set(payload)
                                st.success(f"🚀 ¡Estructura de {st.session_state.sede_seleccionada} sincronizada con éxito!")
                                time.sleep(1)
                                
                                st.session_state.uploader_key += 1
                                
                                st.rerun()
            except Exception as e:
                st.error(f"Error al procesar archivo: {e}")

# ==========================================
# VISTA: VER REPORTES
# ==========================================
elif opcion == "Ver Reportes":
    st.header("📊 Panel de Visualización Histórica")
    
    with st.expander("⚙️ Panel de Administración de Laboratorios"):
        c_alt1, c_alt2, c_alt3 = st.columns(3)
        with c_alt1:
            nuevo_lab = st.text_input("Añadir nuevo laboratorio:", placeholder="Ej. LA SANTE")
            if st.button("Añadir", type="primary"):
                if nuevo_lab.strip():
                    guardar_laboratorio(nuevo_lab.strip())
                    st.success(f"✅ Laboratorio guardado.")
                    time.sleep(0.5)
                    st.rerun()
        with c_alt2:
            labs_todos = obtener_laboratorios(solo_visibles=False)
            labs_visibles = obtener_laboratorios(solo_visibles=True)
            if labs_todos:
                lab_accion = st.selectbox("Ocultar / Mostrar en Cargas:", labs_todos)
                es_visible = lab_accion in labs_visibles
                
                if es_visible:
                    if st.button("Ocultar Laboratorio", type="secondary"):
                        cambiar_visibilidad_laboratorio(lab_accion, False)
                        st.rerun()
                else:
                    if st.button("Hacer Visible", type="primary"):
                        cambiar_visibilidad_laboratorio(lab_accion, True)
                        st.rerun()
        with c_alt3:
            if labs_todos:
                lab_a_eliminar = st.selectbox("Eliminar permanentemente:", labs_todos)
                if st.button("Eliminar del Sistema"):
                    eliminar_laboratorio_db(lab_a_eliminar)
                    st.warning(f"🗑️ Laboratorio eliminado.")
                    time.sleep(0.5)
                    st.rerun()

    st.divider()

    if db is not None:
        docs = db.collection("reportes_comparador").stream()
        lista_reportes = [doc.to_dict() for doc in docs]
        
        # En Ver Reportes mostramos absolutamente todos los laboratorios, ocultos o no
        labs_sistema = obtener_laboratorios(solo_visibles=False)

        if labs_sistema:
            lab_seleccionado = st.selectbox("Seleccione el Laboratorio a evaluar en tiempo real:", labs_sistema)
            
            # Filtro blindado: asegura una coincidencia exacta y limpia
            lab_limpio = str(lab_seleccionado).strip().upper()
            reportes_filtrados = [r for r in lista_reportes if str(r.get("laboratorio", "")).strip().upper() == lab_limpio]
            sedes_con_carga = [r["sede"] for r in reportes_filtrados]
            sedes_faltantes = [s for s in LISTA_SEDES if s not in sedes_con_carga]

            st.markdown(f"### 🗺️ Estatus de Envío — `{lab_seleccionado}`")
            c_cargadas, c_faltantes = st.columns(2)
            with c_cargadas:
                st.markdown("#### 🟢 Reportes Listos")
                if sedes_con_carga:
                    for s in sedes_con_carga: st.markdown(f"✅ **{s}**")
                else:
                    st.write("*Ninguna sede ha cargado este laboratorio.*")
            with c_faltantes:
                st.markdown("#### 🔴 Reportes Pendientes")
                if sedes_faltantes:
                    for s in sedes_faltantes: st.markdown(f"❌ <span style='color:#ff4b4b; font-weight:bold;'>{s}</span>", unsafe_allow_html=True)
                else:
                    st.write("*¡Todas las sedes están al día!*")

            st.divider()

            st.markdown(f"### 📦 Consolidado General Unificado — `{lab_seleccionado}`")
            
            tablas_sedes_limpias = []
            for r in reportes_filtrados:
                df_tmp = pd.DataFrame(r["datos_cuadro"])
                if not df_tmp.empty:
                    # 1. Identificar columnas dinámicamente
                    c_usd, c_und, c_art = None, None, None
                    for col in df_tmp.columns[1:]:
                        c_lower = str(col).lower()
                        if 'compra' in c_lower or 'dolar' in c_lower or '$' in c_lower: c_usd = col
                        elif 'unid' in c_lower: c_und = col
                        elif 'art' in c_lower or 'cant' in c_lower or 'pedir' in c_lower: c_art = col

                    if c_usd is None and len(df_tmp.columns) > 1: c_usd = df_tmp.columns[1]
                    if c_und is None and len(df_tmp.columns) > 2: c_und = df_tmp.columns[-1]

                    # 2. Renombrar con seguro anti-duplicados
                    rename_dict = {df_tmp.columns[0]: "Droguería"}
                    if c_usd: rename_dict[c_usd] = "Total Compra"
                    if c_art and c_art != c_usd: rename_dict[c_art] = "Total Artículos"
                    if c_und and c_und != c_usd and c_und != c_art: rename_dict[c_und] = "Total Unidades"
                    elif c_und and c_und == c_art: rename_dict[c_und] = "Total Unidades"
                    
                    df_tmp.rename(columns=rename_dict, inplace=True)
                    df_tmp = df_tmp.loc[:, ~df_tmp.columns.duplicated(keep='last')]
                    
                    def limpiar_numero_tmp(x):
                        if isinstance(x, str): return x.replace('.', '').replace(',', '.')
                        return x

                    for req in ["Total Compra", "Total Unidades", "Total Artículos"]:
                        if req not in df_tmp.columns:
                            if req == "Total Artículos" and "Total Unidades" in df_tmp.columns:
                                df_tmp[req] = df_tmp["Total Unidades"]
                            elif req == "Total Unidades" and "Total Artículos" in df_tmp.columns:
                                df_tmp[req] = df_tmp["Total Artículos"]
                            else:
                                df_tmp[req] = 0
                        df_tmp[req] = pd.to_numeric(df_tmp[req].apply(limpiar_numero_tmp), errors='coerce').fillna(0)
                        
                    cols_to_keep = [c for c in ORDEN_COLUMNAS if c in df_tmp.columns]
                    df_tmp = df_tmp[cols_to_keep]
                    tablas_sedes_limpias.append(df_tmp)
            
            if tablas_sedes_limpias:
                df_unificado = pd.concat(tablas_sedes_limpias, ignore_index=True)
                
                columnas_calculo = ["Total Compra", "Total Artículos", "Total Unidades"]
                df_consolidado = df_unificado.groupby("Droguería")[columnas_calculo].sum().reset_index()

                total_usd_global = df_consolidado["Total Compra"].sum()
                total_und_global = df_consolidado["Total Unidades"].sum()

                df_consolidado['% Part. Dólares'] = (df_consolidado["Total Compra"] / total_usd_global * 100) if total_usd_global > 0 else 0
                df_consolidado['% Part. Unidades'] = (df_consolidado["Total Unidades"] / total_und_global * 100) if total_und_global > 0 else 0
                columnas_finales_global = [c for c in ORDEN_COLUMNAS if c in df_consolidado.columns]
                df_consolidado = df_consolidado[columnas_finales_global]

                formatters_global = {}
                for col in df_consolidado.columns:
                    col_str = str(col).lower()
                    if col == "Droguería": continue
                    elif 'part.' in col_str or '%' in col_str: formatters_global[col] = lambda x: formato_ve(x, es_porcentaje=True)
                    elif 'unidades' in col_str or 'artículos' in col_str: formatters_global[col] = lambda x: formato_ve(x, es_unidad=True)
                    else: formatters_global[col] = lambda x: formato_ve(x)

                try:
                    st.dataframe(estilar_tabla_oscura(df_consolidado, formatters_global), use_container_width=True, selection_mode="multi-row")
                except:
                    st.dataframe(estilar_tabla_oscura(df_consolidado, formatters_global), use_container_width=True)

                st.markdown("### ➕ Desglose Detallado por Sucursal")
                for i, r in enumerate(reportes_filtrados):
                    
                    # El texto que pediste en el título antes del "(Ver Tabla)"
                    titulo_expander = f"🔹 {r['sede']} | 📦 Unidades: {formato_ve(r['total_unidades'], es_unidad=True)} | 💵 Compra: $ {formato_ve(r['total_dolares'])} (Ver Detallado)"
                    
                    with st.expander(titulo_expander):
                        col_acc1, col_acc2 = st.columns([5, 1])
                        with col_acc1:
                            st.write(f"**Registrado el:** {r['fecha_registro']}")
                        with col_acc2:
                            id_borrar = f"{r['sede'].lower().replace(' ', '_')}_{r['laboratorio'].lower().replace(' ', '_')}"
                            if st.button("🗑️ Eliminar datos", key=f"del_{id_borrar}", type="secondary"):
                                db.collection("reportes_comparador").document(id_borrar).delete()
                                st.warning(f"Datos de {r['sede']} eliminados.")
                                time.sleep(0.5)
                                st.rerun()
                                
                        df_sede_det = tablas_sedes_limpias[i]
                        df_sede_det = df_sede_det[[c for c in ORDEN_COLUMNAS if c in df_sede_det.columns]]
                        try:
                            st.dataframe(estilar_tabla_oscura(df_sede_det, formatters_global), use_container_width=True, selection_mode="multi-row")
                        except:
                            st.dataframe(estilar_tabla_oscura(df_sede_det, formatters_global), use_container_width=True)

                st.divider()
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown(f"""<div style="background-color:#14231c; padding:25px; border-radius:12px; border-left:6px solid #10b981; text-align:center; border:1px solid #1f3a2b;"><span style="color:#a3cfbb; font-size:16px; font-weight:bold; text-transform:uppercase;">💵 Total Compra Consolidada</span><br><span style="color:#52d681; font-size:52px; font-weight:900;">$ {formato_ve(total_usd_global)}</span></div>""", unsafe_allow_html=True)
                with col_m2:
                    st.markdown(f"""<div style="background-color:#101f30; padding:25px; border-radius:12px; border-left:6px solid #0d6efd; text-align:center; border:1px solid #16325c;"><span style="color:#9ec5fe; font-size:16px; font-weight:bold; text-transform:uppercase;">📦 Total Unidades Consolidado</span><br><span style="color:#6ea8fe; font-size:52px; font-weight:900;">{formato_ve(total_und_global, es_unidad=True)}</span></div>""", unsafe_allow_html=True)
            else:
                st.info("No existen reportes cargados para este laboratorio.")
        else:
            st.info("Registra tu primer laboratorio en el panel superior para habilitar los reportes.")
    else:
        st.error("No hay conexión con Firebase.")
# ==========================================
# VISTA: CONSOLIDADO TOTAL
# ==========================================
elif opcion == "Consolidado Total":
    st.header("🌍 Consolidado Total NY-COMPRAS")
    
    if db is not None:
        with st.spinner("Procesando información de todas las sedes..."):
            docs = db.collection("reportes_comparador").stream()
            lista_reportes = [doc.to_dict() for doc in docs]
            
            if lista_reportes:
                df_master = pd.DataFrame(lista_reportes)
                
                # 1. Agrupar la sumatoria por Sede
                df_sedes = df_master.groupby("sede")[["total_dolares", "total_unidades"]].sum().reset_index()
                df_sedes.rename(columns={"sede": "Sede", "total_dolares": "Total Compra", "total_unidades": "Total Unidades"}, inplace=True)
                
                # 2. Calcular Totales Globales Exactos
                gran_total_usd = df_sedes["Total Compra"].sum()
                gran_total_und = df_sedes["Total Unidades"].sum()
                
                # 3. Calcular Porcentajes de Participación (100% garantizado)
                df_sedes['% Part. Dólares'] = (df_sedes["Total Compra"] / gran_total_usd * 100) if gran_total_usd > 0 else 0
                df_sedes['% Part. Unidades'] = (df_sedes["Total Unidades"] / gran_total_und * 100) if gran_total_und > 0 else 0
                
                # 4. Ordenar de Mayor a Menor según ventas
                df_sedes = df_sedes.sort_values(by="Total Compra", ascending=False)
                
                # 5. Formateadores Visuales (Cantidades sin decimales, Dinero con decimales)
                formatters_cons = {
                    "Total Compra": lambda x: formato_ve(x),
                    "Total Unidades": lambda x: formato_ve(x, es_unidad=True),
                    "% Part. Dólares": lambda x: formato_ve(x, es_porcentaje=True),
                    "% Part. Unidades": lambda x: formato_ve(x, es_porcentaje=True)
                }
                
                # --- TARJETAS KPI (TOTALES GLOBALES) ---
                st.markdown("### 📌 Resumen Global (Suma de todas las Sedes)")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown(f"""<div style="background-color:#14231c; padding:25px; border-radius:12px; border-left:6px solid #10b981; text-align:center; border:1px solid #1f3a2b;"><span style="color:#a3cfbb; font-size:16px; font-weight:bold; text-transform:uppercase;">💵 Gran Total Compras</span><br><span style="color:#52d681; font-size:52px; font-weight:900;">$ {formato_ve(gran_total_usd)}</span></div>""", unsafe_allow_html=True)
                with col_m2:
                    st.markdown(f"""<div style="background-color:#101f30; padding:25px; border-radius:12px; border-left:6px solid #0d6efd; text-align:center; border:1px solid #16325c;"><span style="color:#9ec5fe; font-size:16px; font-weight:bold; text-transform:uppercase;">📦 Gran Total Unidades</span><br><span style="color:#6ea8fe; font-size:52px; font-weight:900;">{formato_ve(gran_total_und, es_unidad=True)}</span></div>""", unsafe_allow_html=True)

                st.divider()
                
                # --- TABLA 1: RANKING POR SEDES ---
                st.markdown("### 🏆 Ranking de Consolidado por Sedes")
                try:
                    st.dataframe(estilar_tabla_oscura(df_sedes, formatters_cons), use_container_width=True, selection_mode="multi-row")
                except:
                    st.dataframe(estilar_tabla_oscura(df_sedes, formatters_cons), use_container_width=True)
                
                st.divider()
                # --- DESGLOSE DETALLADO POR SUCURSAL ---
                st.markdown("### ➕ Detalle de Compras (Laboratorios por Sede)")
                
                for idx, row in df_sedes.iterrows():
                    sede_nombre = row["Sede"]
                    compra_sede = row["Total Compra"]
                    und_sede = row["Total Unidades"]
                    
                    # Filtramos la base de datos maestra solo para esta Sede
                    df_filtro_sede = df_master[df_master["sede"] == sede_nombre].copy()
                    
                    if not df_filtro_sede.empty:
                        # Agrupamos los laboratorios que compró esta sede en específico
                        df_filtro_sede = df_filtro_sede.groupby("laboratorio")[["total_dolares", "total_unidades"]].sum().reset_index()
                        df_filtro_sede.rename(columns={"laboratorio": "Laboratorio", "total_dolares": "Total Compra", "total_unidades": "Total Unidades"}, inplace=True)
                        
                        # Calculamos la participación en base al total local de la SEDE
                        df_filtro_sede['% Part. Dólares'] = (df_filtro_sede["Total Compra"] / compra_sede * 100) if compra_sede > 0 else 0
                        df_filtro_sede['% Part. Unidades'] = (df_filtro_sede["Total Unidades"] / und_sede * 100) if und_sede > 0 else 0
                        # Ordenamos quién se llevó la mayor compra
                        df_filtro_sede = df_filtro_sede.sort_values(by="Total Compra", ascending=False)
                        
                        titulo_sede = f"🔹 {sede_nombre} | 📦 Unidades Totales: {formato_ve(und_sede, es_unidad=True)} | 💵 Compra: $ {formato_ve(compra_sede)} (Ver Detallado)"
                        
                        with st.expander(titulo_sede):
                            st.dataframe(estilar_tabla_oscura(df_filtro_sede, formatters_cons), use_container_width=True)
                
                st.divider()
                
                # --- TABLA 2: RANKING POR LABORATORIOS ---
                st.markdown("### 🔬 Aporte Detallado por Laboratorio")
                df_labs = df_master.groupby("laboratorio")[["total_dolares", "total_unidades"]].sum().reset_index()
                df_labs.rename(columns={"laboratorio": "Laboratorio", "total_dolares": "Total Compra", "total_unidades": "Total Unidades"}, inplace=True)
                
                df_labs['% Part. Dólares'] = (df_labs["Total Compra"] / gran_total_usd * 100) if gran_total_usd > 0 else 0
                df_labs['% Part. Unidades'] = (df_labs["Total Unidades"] / gran_total_und * 100) if gran_total_und > 0 else 0
                df_labs = df_labs.sort_values(by="Total Compra", ascending=False)
                
                try:
                    st.dataframe(estilar_tabla_oscura(df_labs, formatters_cons), use_container_width=True, selection_mode="multi-row")
                except:
                    st.dataframe(estilar_tabla_oscura(df_labs, formatters_cons), use_container_width=True)
                
            else:
                st.info("No hay datos registrados en el sistema aún. Carga un Excel para comenzar.")
    else:
        st.error("Error de conexión con Firebase.")        
