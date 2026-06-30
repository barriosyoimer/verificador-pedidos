import streamlit as st
import pandas as pd
import numpy as np
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime, date, timedelta, timezone
import calendar
import time
import base64
from PIL import Image
import io

# ... (Tus importaciones)

# --- 1. CONFIGURACIÓN DEL ENTORNO Y CONSTANTES ---
st.set_page_config(page_title="Gestor de Pedidos - COMPARADOR", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
st.title("📊 Control Consolidado - Unidades y Valores NY")

@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'gestor-de-pedidos-52c82.firebasestorage.app' 
        })
    return firestore.client()

db = init_firebase()

# --- 3. CONTROL DE CALENDARIO (AHORA DB SÍ EXISTE) ---
st.sidebar.markdown("### ⚙️ Control de Calendario")
try:
    doc_config_cal = db.collection("app_config").document("calendario").get()
    estado_mes_siguiente = doc_config_cal.to_dict().get("forzar_mes_siguiente", False) if doc_config_cal.exists else False
except:
    estado_mes_siguiente = False

def toggle_mes_siguiente():
    nuevo_estado = st.session_state.chk_mes_siguiente
    if db is not None:
        db.collection("app_config").document("calendario").set({"forzar_mes_siguiente": nuevo_estado}, merge=True)

st.sidebar.checkbox("⏭️ Forzar Mes Siguiente", value=estado_mes_siguiente, key="chk_mes_siguiente", on_change=toggle_mes_siguiente, help="Activa esto para empezar a leer el mes que viene.")
st.sidebar.markdown("---")

LISTA_SEDES = ["OLIVOS", "BAZAR", "SAN JACINTO", "HATICOS", "CUMBRES", "COROMOTO"]
ORDEN_COLUMNAS = ["Droguería", "Total Compra", "Total Artículos", "Total Unidades", "% Part. Dólares", "% Part. Unidades"]
# --- INYECCIÓN DE CSS PARA LIMITAR LAS BARRAS DE SELECCIÓN ---
st.markdown("""
<style>
    /* Limitar la altura de los menús desplegables globales */
    div[data-baseweb="popover"] ul {
        max-height: 200px !important; /* Ajusta la altura a unos 5 elementos */
        overflow-y: auto !important; /* Fuerza la barra de desplazamiento */
    }
</style>
""", unsafe_allow_html=True)

if "sede_seleccionada" not in st.session_state:
    st.session_state.sede_seleccionada = LISTA_SEDES[0]
if "dia_seleccionado" not in st.session_state:
    st.session_state.dia_seleccionado = datetime.now().day

def actualizar_sede():
    st.session_state.sede_seleccionada = st.session_state.sede_widget

# --- 2. INICIALIZACIÓN DE FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_dict)
        
        # Aquí colocamos tu Storage exacto
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'gestor-de-pedidos-52c82.firebasestorage.app' 
        })
    return firestore.client()

db = init_firebase()
# --- NUEVO: CARGA DINÁMICA DE SEDES DESDE LOS PERFILES DEL ESCRITORIO ---
@st.cache_data(ttl=600) # Cache de 10 minutos para ahorrar lecturas a Firebase
def obtener_sedes():
    if db is not None:
        try:
            docs = db.collection("perfiles_cloud").stream()
            sedes_nube = [doc.id.upper() for doc in docs]
            if sedes_nube:
                return sorted(sedes_nube)
        except: pass
    return ["OLIVOS", "BAZAR", "SAN JACINTO", "HATICOS", "CUMBRES", "COROMOTO"]

LISTA_SEDES = obtener_sedes()
# --- 3. FUNCIONES PARA LOGOS EN FIREBASE CON COMPRESIÓN ---
def guardar_logo_firebase(nombre_lab, file_bytes):
    if db:
        try:
            # Comprimir la imagen para que JAMÁS sobrepase el límite de memoria de Firebase
            img = Image.open(io.BytesIO(file_bytes))
            # Convertir a RGBA primero por si es un formato sin transparencia, y luego asegurar compatibilidad
            if img.mode in ("RGBA", "P"): img = img.convert("RGBA")
            img.thumbnail((150, 150))
            
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_compressed = buffered.getvalue()
            
            b64_img = base64.b64encode(img_compressed).decode()
            doc_id = nombre_lab.strip().upper().replace(" ", "_")
            db.collection("configuracion_logos").document(doc_id).set({"logo_b64": b64_img})
        except Exception as e:
            st.error(f"Error al procesar la imagen: {e}")

def obtener_logos_firebase():
    logos = {}
    if db:
        try:
            docs = db.collection("configuracion_logos").stream()
            for doc in docs:
                logos[doc.id] = doc.to_dict().get("logo_b64", "")
        except:
            pass
    return logos

# --- 4. LÓGICA DE GENERACIÓN AUTOMÁTICA DEL CALENDARIO (En blanco desde cero) ---
def generar_calendario_dinamico(year, month, labs_semana=None, labs_sabados=None):
    num_days = calendar.monthrange(year, month)[1]
    calendario = []
    dias_es = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    
    # Contadores para recorrer las listas de carga heredadas del mes pasado
    idx_semana = 0
    idx_sabado = 0
    
    for day in range(1, num_days + 1):
        fecha_obj = date(year, month, day)
        dia_semana = fecha_obj.weekday()
        
        if dia_semana == 6:  # Domingo siempre queda libre
            asignacion = ["DOMINGO / LIBRE"]
        elif dia_semana == 5:  # Sábados: Conservan su propia secuencia fija
            if labs_sabados and idx_sabado < len(labs_sabados):
                asignacion = labs_sabados[idx_sabado]
            else:
                asignacion = []
            idx_sabado += 1
        else:  # Días de semana (Lunes a Viernes): Siguen el orden secuencial de carga
            if labs_semana and idx_semana < len(labs_semana):
                asignacion = labs_semana[idx_semana]
            else:
                asignacion = []
            idx_semana += 1
            
        calendario.append({
            "Fecha": fecha_obj.strftime("%Y-%m-%d"),
            "Día": dias_es[dia_semana],
            "Laboratorios": asignacion 
        })
    return calendario

def obtener_calendario(db_conn, year, month):
    if not db_conn: return []
    doc_id = f"{year}_{month:02d}"
    doc = db_conn.collection("configuracion_calendario").document(doc_id).get()
    if doc.exists:
        return doc.to_dict().get("dias", [])
    else:
        # Calcular de manera automática el año y mes anterior
        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1
            
        prev_doc_id = f"{prev_year}_{prev_month:02d}"
        prev_doc = db_conn.collection("configuracion_calendario").document(prev_doc_id).get()
        
        labs_semana = None
        labs_sabados = None
        
        # Si hay planificación registrada en el mes anterior, extraemos los patrones
        if prev_doc.exists:
            prev_dias = prev_doc.to_dict().get("dias", [])
            
            # 1. Guardamos la carga de los sábados en orden cronológico (1º sábado, 2º sábado...)
            labs_sabados = [d.get("Laboratorios", []) for d in prev_dias if d.get("Día") == "Sábado"]
            
            # 2. Guardamos la lista continua de lunes a viernes en el orden en que fueron configurados
            labs_semana = [d.get("Laboratorios", []) for d in prev_dias if d.get("Día") in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]]
            
        # Generamos el nuevo calendario inyectando el orden del mes pasado
        nuevo_cal = generar_calendario_dinamico(year, month, labs_semana, labs_sabados)
        db_conn.collection("configuracion_calendario").document(doc_id).set({"dias": nuevo_cal})
        return nuevo_cal

def actualizar_calendario(db_conn, year, month, df_actualizado):
    if not db_conn: return
    doc_id = f"{year}_{month:02d}"
    if isinstance(df_actualizado, pd.DataFrame):
        dias_dict = df_actualizado.to_dict(orient="records")
    else:
        dias_dict = df_actualizado
    db_conn.collection("configuracion_calendario").document(doc_id).set({"dias": dias_dict})

# --- 5. FORMATOS Y ESTILOS ---
def formato_ve(valor, es_porcentaje=False, es_unidad=False):
    if pd.isna(valor) or valor == "": return "0" if es_unidad else "0,00"
    try:
        v = float(valor)
        if es_porcentaje: return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " %"
        elif es_unidad: return f"{int(round(v)):,}".replace(",", ".")
        else: return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

def estilar_tabla_oscura(df_datos, formatters):
    df_styled = df_datos.style.format(formatters).set_properties(**{
        'border': '1px solid #3a3a3a', 'color': '#ffffff', 'background-color': '#111111'
    })
    df_styled = df_styled.set_table_styles([{'selector': 'tr:hover td', 'props': [('background-color', '#2c3e50')]}], overwrite=False)
    
    def destacar_ganador_oscuro(s):
        is_max = s == s.max()
        return ['background-color: #0e3a1d; color: #52d681; font-weight: bold; border: 1px solid #10b981;' if v else '' for v in is_max]
    
    columnas_part = [c for c in df_datos.columns if '% Part.' in str(c)]
    if columnas_part: df_styled = df_styled.apply(destacar_ganador_oscuro, subset=columnas_part)
    return df_styled

# --- 6. MENÚ DE NAVEGACIÓN PRINCIPAL ---
opcion = st.sidebar.radio("Seleccione una opción:", ["Cargar Excel", "Ver Reportes", "Consolidado Total", "Cargar Comparador"])

# ==========================================
# VISTA 1: CARGAR EXCEL
# ==========================================
if opcion == "Cargar Excel":
    st.header("📥 Carga de Pedidos desde EXCEL")
    
    hoy = datetime.now()
    ayer = hoy - timedelta(days=1)
    manana = hoy + timedelta(days=1)
    
    # Formatos de fecha (Uno para buscar en la base de datos, otro para mostrar)
    hoy_str_db = hoy.strftime("%Y-%m-%d")
    hoy_str_visor = hoy.strftime("%d-%m-%Y") 

    # Función auxiliar para extraer laboratorios de un día específico
    def extraer_labs_dia(fecha_busqueda):
        cal = obtener_calendario(db, fecha_busqueda.year, fecha_busqueda.month)
        fecha_str = fecha_busqueda.strftime("%Y-%m-%d")
        for dia in cal:
            if dia.get("Fecha") == fecha_str:
                labs = dia.get("Laboratorios", [])
                if isinstance(labs, str): 
                    return [l.strip().upper() for l in labs.split(",") if l.strip() and "DOMINGO" not in labs.upper()]
                else: 
                    return [l.upper() for l in labs if "DOMINGO" not in str(l).upper()]
        return []

    lista_labs_hoy = extraer_labs_dia(hoy)
    lista_labs_ayer = extraer_labs_dia(ayer)
    lista_labs_manana = extraer_labs_dia(manana)
            
    # DISEÑO: Nombres de laboratorios tipo "Etiquetas"
    if lista_labs_hoy:
        html_labs = "".join([f'<span style="background-color: #1e293b; color: #60a5fa; padding: 8px 16px; border-radius: 20px; font-weight: bold; margin: 5px 10px 5px 0; display: inline-block; border: 1px solid #3b82f6; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">🔬 {lab}</span>' for lab in lista_labs_hoy])
    else:
        html_labs = '<span style="color: #9ca3af; font-style: italic; padding: 5px;">Ninguno asignado / Día Libre 🏖️</span>'

    st.markdown(f"""
    <div style="background-color: #0f172a; padding: 25px; border-radius: 12px; border-left: 6px solid #3b82f6; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h4 style="margin-top: 0; margin-bottom: 15px; color: #f8fafc;">📅 Planificación de Hoy ({hoy_str_visor})</h4>
        <div>{html_labs}</div>
    </div>
    """, unsafe_allow_html=True)

    # DISEÑO: Carrusel de imágenes de los laboratorios
    if lista_labs_hoy:
        logos_guardados = obtener_logos_firebase()
        html_imagenes = ""
        
        for lab in lista_labs_hoy:
            lab_id = lab.strip().upper().replace(" ", "_")
            if lab_id in logos_guardados and logos_guardados[lab_id]:
                img_src = f"data:image/png;base64,{logos_guardados[lab_id]}"
                # Se aumentó width/height a 120px y se redujo el margin a 10px
                html_imagenes += f'<img src="{img_src}" style="background-color: white; object-fit: contain; padding: 4px; border-radius: 50%; width: 120px; height: 120px; margin: 0 10px; border: 3px solid #3b82f6; box-shadow: 0 0 12px rgba(59, 130, 246, 0.4);">'
            else:
                nombre_url = lab.replace(" ", "+")
                # Se aumentó width/height a 120px y se redujo el margin a 10px
                html_imagenes += f'<img src="https://ui-avatars.com/api/?name={nombre_url}&background=random&color=fff&size=100&rounded=true&bold=true&font-size=0.4" style="border-radius: 50%; width: 120px; height: 120px; margin: 0 10px; border: 3px solid #3b82f6; box-shadow: 0 0 12px rgba(59, 130, 246, 0.4);">'
        
        html_repetido = html_imagenes * 10
        st.markdown(f"""
        <style>
            .carrusel-contenedor {{ width: 100%; overflow: hidden; white-space: nowrap; background-color: #141414; padding: 20px 0; border-radius: 15px; border: 1px solid #222; margin-bottom: 30px; position: relative; }}
            .carrusel-contenido {{ display: inline-block; animation: mover-carrusel 40s linear infinite; }}
            @keyframes mover-carrusel {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
        </style>
        <div class="carrusel-contenedor"><div class="carrusel-contenido">{html_repetido}</div></div>
        """, unsafe_allow_html=True)
    else:
        st.divider()
    with st.expander("👀 Ver laboratorios de Ayer y Mañana"):
        col_ayer, col_manana = st.columns(2)
        with col_ayer:
            st.markdown(f"**Ayer ({ayer.strftime('%d-%m-%Y')}):**")
            if lista_labs_ayer:
                for l in lista_labs_ayer: st.write(f"▪️ {l}")
            else:
                st.write("*Ninguno / Libre*")
        with col_manana:
            st.markdown(f"**Mañana ({manana.strftime('%d-%m-%Y')}):**")
            if lista_labs_manana:
                for l in lista_labs_manana: st.write(f"▪️ {l}")
            else:
                st.write("*Ninguno / Libre*")    

    col1, col2 = st.columns(2)
    with col1:
        sede_input = st.selectbox("Seleccione la Sede / Sucursal:", LISTA_SEDES, index=LISTA_SEDES.index(st.session_state.sede_seleccionada), key="sede_widget", on_change=actualizar_sede)
    
    with col2:
        labs_ya_cargados = []
        if db:
            docs_sede = db.collection("reportes_comparador").where("sede", "==", sede_input).stream()
            labs_ya_cargados = [d.to_dict().get("laboratorio", "").upper() for d in docs_sede]

        labs_disponibles = list(set(lista_labs_ayer + lista_labs_hoy))
        labs_pendientes = [lab for lab in labs_disponibles if lab.upper() not in labs_ya_cargados]

        if not labs_pendientes:
            st.success("🎉 ¡Todos los pedidos de ayer y hoy están cargados para esta sede!")
            laboratorio_input = ""
        else:
            laboratorio_input = st.selectbox("Seleccione el Laboratorio a cargar:", labs_pendientes)

    if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
    uploaded_file = st.file_uploader("Seleccionar archivo (.xlsm / .xlsx)", type=["xlsx", "xlsm"], key=f"uploader_{st.session_state.uploader_key}")

    if uploaded_file is not None and laboratorio_input != "":
        doc_id_verificar = f"{sede_input.lower().replace(' ', '_')}_{laboratorio_input.lower().replace(' ', '_')}"
        esta_bloqueado = db.collection("reportes_comparador").document(doc_id_verificar).get().exists if db else False

        if esta_bloqueado:
            st.warning(f"⚠️ **Sobre-escritura detectada:** Los datos de {laboratorio_input} para la sede {sede_input} ya existen. Guardar reemplazará los registros previos.")
        
        try:
            progreso = st.progress(0, text="Leyendo matriz...")
            xls = pd.ExcelFile(uploaded_file, engine='openpyxl')
            hoja_objetivo = next((h for h in xls.sheet_names if "TABLA" in h.strip().upper()), None)
            
            if not hoja_objetivo:
                st.error("❌ No se encontró ninguna hoja llamada 'TABLA'.")
                progreso.empty()
                st.stop()

            df_full = pd.read_excel(uploaded_file, sheet_name=hoja_objetivo, engine='openpyxl')
            df_full = df_full.dropna(how='all')
            df_full = df_full.dropna(axis=1, how='all')

            idx_recorte = len(df_full)
            for idx, row in df_full.iterrows():
                row_str = " ".join([str(val).upper() for val in row.values[:3]])
                if "TOTAL" in row_str:
                    idx_recorte = idx
                    break

            df_tabla = df_full.iloc[:idx_recorte].copy()
            df_tabla = df_tabla.dropna(how='all')

            c_usd, c_und, c_art = None, None, None
            for col in df_tabla.columns[1:]:
                c_lower = str(col).lower().strip()
                if 'compra' in c_lower or 'dolar' in c_lower or '$' in c_lower: c_usd = col
                elif 'art' in c_lower: c_art = col
                elif 'unid' in c_lower: c_und = col

            if not c_usd and len(df_tabla.columns) > 1: c_usd = df_tabla.columns[1]
            if not c_art and len(df_tabla.columns) > 2: c_art = df_tabla.columns[2]
            if not c_und and len(df_tabla.columns) > 3: c_und = df_tabla.columns[3]

            rename_dict = {df_tabla.columns[0]: "Droguería"}
            if c_usd: rename_dict[c_usd] = "Total Compra"
            if c_art: rename_dict[c_art] = "Total Artículos"
            if c_und: rename_dict[c_und] = "Total Unidades"
            
            df_tabla = df_tabla.rename(columns=rename_dict)
            df_tabla = df_tabla.loc[:, ~df_tabla.columns.duplicated(keep='last')]

            def limpiar_numero(x):
                if pd.isna(x): return 0
                if isinstance(x, str): 
                    x = x.replace('$', '').replace('USD', '').strip()
                    return x.replace('.', '').replace(',', '.')
                return x

            for col_req in ["Total Compra", "Total Artículos", "Total Unidades"]:
                if col_req not in df_tabla.columns: df_tabla[col_req] = 0
                df_tabla[col_req] = pd.to_numeric(df_tabla[col_req].apply(limpiar_numero), errors='coerce').fillna(0)

            df_tabla = df_tabla[df_tabla["Total Unidades"] > 0]
            if df_tabla.empty:
                st.info("💡 No hay artículos con cantidades mayores a 0.")
                progreso.empty()
                st.stop()

            suma_real_dolares = df_tabla["Total Compra"].sum()
            suma_real_unidades = df_tabla["Total Unidades"].sum()

            df_tabla['% Part. Dólares'] = (df_tabla["Total Compra"] / suma_real_dolares * 100) if suma_real_dolares > 0 else 0
            df_tabla['% Part. Unidades'] = (df_tabla["Total Unidades"] / suma_real_unidades * 100) if suma_real_unidades > 0 else 0
            
            for col in ["Total Artículos", "Total Unidades"]: 
                df_tabla[col] = np.floor(df_tabla[col] + 0.5).astype(int)

            df_tabla = df_tabla[[c for c in ORDEN_COLUMNAS if c in df_tabla.columns]]
            
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
            st.dataframe(df_styled, use_container_width=True)

            st.divider()
            col_c1, col_c2 = st.columns(2)
            with col_c1: st.markdown(f"""<div style="background-color:#14231c; padding:20px; border-radius:10px; border-left:6px solid #10b981; text-align:center;"><span style="color:#a3cfbb; font-size:14px; font-weight:bold;">💵 Total Compra</span><br><span style="color:#52d681; font-size:36px; font-weight:900;">$ {formato_ve(suma_real_dolares)}</span></div>""", unsafe_allow_html=True)
            with col_c2: st.markdown(f"""<div style="background-color:#101f30; padding:20px; border-radius:10px; border-left:6px solid #0d6efd; text-align:center;"><span style="color:#9ec5fe; font-size:14px; font-weight:bold;">📦 Total Unidades</span><br><span style="color:#6ea8fe; font-size:36px; font-weight:900;">{formato_ve(suma_real_unidades, es_unidad=True)}</span></div>""", unsafe_allow_html=True)

            permitir_guardado = True
            if laboratorio_input.lower().replace(" ", "") not in uploaded_file.name.lower().replace(" ", ""):
                st.warning(f"⚠️ El archivo `{uploaded_file.name}` no parece de `{laboratorio_input}`.")
                if not st.checkbox("Confirmar carga manual", value=False): permitir_guardado = False

            if permitir_guardado and st.button("Guardar en Base de Datos", type="primary"):
                with st.spinner("Sincronizando..."):    
                    payload = {
                        "sede": sede_input, "laboratorio": laboratorio_input,
                        "total_dolares": float(suma_real_dolares), "total_unidades": int(round(suma_real_unidades)),
                        "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "datos_cuadro": df_tabla.to_dict(orient="records")
                    }
                    db.collection("reportes_comparador").document(doc_id_verificar).set(payload)
                    st.success("🚀 Sincronizado con éxito.")
                    time.sleep(1)
                    st.session_state.uploader_key += 1
                    st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

# ==========================================
# VISTA 2: VER REPORTES Y PLANIFICACIÓN (OPTIMIZADO)
# ==========================================
# ==========================================
    # ==========================================
    # NUEVA SECCIÓN: DESCARGA DEL EXCEL MAESTRO
    # (Asegúrate de que esta línea esté a la misma altura de indentación que el contenido de Cargar Excel)
    # ==========================================
    st.divider()
    
    if db is not None:
        doc_ref_global = db.collection("configuracion_global").document("comparador_maestro")
        doc_snap_global = doc_ref_global.get()
        ultima_act = doc_snap_global.to_dict().get("ultima_actualizacion", "Sin registros") if doc_snap_global.exists else "Sin registros"
        
        # Diseño mejorado: Título modificado y fecha más resaltada
        st.markdown(f"""
        <div style="background-color: #1e293b; padding: 25px; border-radius: 12px; border-left: 6px solid #10b981; box-shadow: 0 6px 12px rgba(0,0,0,0.4); margin-bottom: 25px;">
            <h3 style="margin: 0 0 10px 0; color: #f8fafc; font-size: 24px;">📊 Archivo Excel Comparador</h3>
            <p style="margin: 0; color: #94a3b8; font-size: 16px;">Última actualización: <span style="color: #52d681; font-weight: bold; font-size: 19px;">{ultima_act}</span></p>
        </div>
        """, unsafe_allow_html=True)

        @st.cache_data(show_spinner=False)
        def obtener_bytes_maestro(fecha_actualizacion):
            try:
                bucket = storage.bucket()
                blob = bucket.blob("comparador_maestro/excel_actual.xlsm")
                if blob.exists():
                    return blob.download_as_bytes()
            except:
                return None

       
        excel_bytes = obtener_bytes_maestro(ultima_act)

        if excel_bytes:
            # --- CSS INYECTADO: BOTÓN PREMIUM (CORREGIDO) ---
            st.markdown("""
            <style>
                /* Estructura y fondo del botón */
                div[data-testid="stDownloadButton"] button {
                    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
                    border: 1px solid #047857 !important;
                    border-radius: 10px !important;
                    padding: 15px 20px !important; 
                    box-shadow: 0 4px 10px rgba(16, 185, 129, 0.3) !important;
                    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
                }
                
                /* Forzar el tamaño, fuente y negrita */
                div[data-testid="stDownloadButton"] button, 
                div[data-testid="stDownloadButton"] button p {
                    font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
                    font-size: 20px !important; 
                    font-weight: 900 !important; 
                    color: white !important;
                    letter-spacing: 1px !important; 
                    margin: 0 !important;
                }
                
                /* Efecto hover (al pasar el mouse) */
                div[data-testid="stDownloadButton"] button:hover {
                    background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
                    box-shadow: 0 8px 20px rgba(16, 185, 129, 0.6) !important;
                    transform: translateY(-3px) !important;
                    border: 1px solid #064e3b !important;
                }
                
                /* LA SOLUCIÓN: Efecto visual de "Presionado" sin bloquear el clic */
                div[data-testid="stDownloadButton"] button:active,
                div[data-testid="stDownloadButton"] button:focus {
                    transform: translateY(2px) !important; /* Se hunde profundamente */
                    box-shadow: 0 1px 3px rgba(16, 185, 129, 0.4) !important;
                    filter: brightness(0.6) !important; /* Se oscurece notablemente */
                }
            </style>
            """, unsafe_allow_html=True)

            # Botón centrado
            c_btn1, c_btn2, c_btn3 = st.columns([1, 2, 1])
            with c_btn2:
                tz_venezuela = timezone(timedelta(hours=-4))
                fecha_hoy_str = datetime.now(tz_venezuela).strftime("%d_%m")
                
                st.download_button(
                    label="📥 DESCARGAR EXCEL AHORA",
                    data=excel_bytes,
                    file_name=f"COMPARADOR_{fecha_hoy_str}.xlsm",
                    mime="application/vnd.ms-excel.sheet.macroEnabled.12",
                    use_container_width=True,
                    type="primary"
                )
        else:
            st.info("💡 Aún no se ha subido ningún archivo maestro a la base de datos.")

elif opcion == "Ver Reportes":
    st.header("📊 Panel de Visualización y Planificación")
    
    # --- MEJORA ESTÉTICA: Selectores globales al inicio ---
    hoy = datetime.now()
    col_f_global1, col_f_global2 = st.columns(2)
    with col_f_global1: 
        mes_sel = st.selectbox("Seleccionar Mes de Consulta/Planificación:", range(1, 13), index=hoy.month - 1, key="global_mes_sel")
    with col_f_global2: 
        anio_sel = st.selectbox("Seleccionar Año de Consulta/Planificación:", [hoy.year, hoy.year+1], index=0, key="global_anio_sel")

    st.divider()

    # Descarga inicial de datos de Firebase para optimizar el rendimiento de todas las pestañas
    lista_reportes_completa = []
    if db is not None:
        with st.spinner("Consultando base de datos..."):
            docs = db.collection("reportes_comparador").stream()
            lista_reportes_completa = [dict(doc.to_dict(), id_real_fb=doc.id) for doc in docs]

    # --- REQUERIMIENTO 2: Definición de las 5 pestañas ---
    # Modifica la declaración de las pestañas
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Consolidado de Reportes", 
    "🗓️ Calendario Visual", 
    "📊 Tabla Resumen del Mes", 
    "🔍 Rastreo de Cargas (Bi-Mes)",
    "🚀 APERTURA",
    "📦 Control de Inventario" # <--- NUEVA PESTAÑA
     ])
    
    # ==========================================
    # PESTAÑA 1: CONSOLIDADO DE REPORTES (Filtrado por mes activo)
    # ==========================================
    with tab1:
        if db is not None:
            # --- REQUERIMIENTO 1: Filtrar para que muestre SOLO el mes seleccionado ---
            mes_busqueda_str = f"{anio_sel}-{mes_sel:02d}"
            lista_reportes = [r for r in lista_reportes_completa if r.get("fecha_registro", "").startswith(mes_busqueda_str)]
            
            labs_sistema = sorted(list(set(r.get("laboratorio", "").strip().upper() for r in lista_reportes if r.get("laboratorio"))))

            if labs_sistema:
                lab_guardado = st.query_params.get("lab", labs_sistema[0])
                idx_lab = labs_sistema.index(lab_guardado) if lab_guardado in labs_sistema else 0
        
                lab_seleccionado = st.selectbox("Seleccione el Laboratorio a evaluar:", labs_sistema, index=idx_lab)
                st.query_params["lab"] = lab_seleccionado
                
                reportes_filtrados = [r for r in lista_reportes if str(r.get("laboratorio", "")).strip().upper() == str(lab_seleccionado).strip().upper()]
                sedes_con_carga = [r["sede"] for r in reportes_filtrados]
                sedes_faltantes = [s for s in LISTA_SEDES if s not in sedes_con_carga]

                st.markdown(f"### 🗺️ Estatus de Envío — `{lab_seleccionado}` ({mes_sel:02d}/{anio_sel})")
                c_cargadas, c_faltantes = st.columns(2)
                with c_cargadas:
                    st.markdown("#### 🟢 Reportes Listos")
                    for s in sedes_con_carga: st.markdown(f"✅ **{s}**")
                    if not sedes_con_carga: st.write("*Ninguna sede ha cargado este laboratorio en el mes seleccionado.*")
                with c_faltantes:
                    st.markdown("#### 🔴 Reportes Pendientes")
                    for s in sedes_faltantes: st.markdown(f"❌ <span style='color:#ff4b4b; font-weight:bold;'>{s}</span>", unsafe_allow_html=True)
                    if not sedes_faltantes: st.write("*¡Todas las sedes al día!*")

                st.divider()
                st.markdown(f"### 📦 Consolidado General Unificado — `{lab_seleccionado}`")
                
                tablas_sedes_limpias = []
                for r in reportes_filtrados:
                    df_tmp = pd.DataFrame(r["datos_cuadro"])
                    if not df_tmp.empty:
                        if "Droguería" not in df_tmp.columns: df_tmp = df_tmp.rename(columns={df_tmp.columns[0]: "Droguería"})
                        
                        def limpiar_num_df(x):
                            if pd.isna(x): return 0
                            if isinstance(x, str): return x.replace('.', '').replace(',', '.')
                            return x

                        for req in ["Total Compra", "Total Artículos", "Total Unidades"]:
                            if req not in df_tmp.columns: df_tmp[req] = 0
                            df_tmp[req] = pd.to_numeric(df_tmp[req].apply(limpiar_num_df), errors='coerce').fillna(0)
                        
                        df_tmp = df_tmp[[c for c in ORDEN_COLUMNAS if c in df_tmp.columns]]
                        tablas_sedes_limpias.append(df_tmp)
                
                if tablas_sedes_limpias:
                    df_consolidado = pd.concat(tablas_sedes_limpias, ignore_index=True).groupby("Droguería")[["Total Compra", "Total Artículos", "Total Unidades"]].sum().reset_index()
                    total_usd_global = df_consolidado["Total Compra"].sum()
                    total_und_global = df_consolidado["Total Unidades"].sum()
                    df_consolidado['% Part. Dólares'] = (df_consolidado["Total Compra"] / total_usd_global * 100) if total_usd_global > 0 else 0
                    df_consolidado['% Part. Unidades'] = (df_consolidado["Total Unidades"] / total_und_global * 100) if total_und_global > 0 else 0
                    df_consolidado = df_consolidado[[c for c in ORDEN_COLUMNAS if c in df_consolidado.columns]]

                    formatters_global = {}
                    for col in df_consolidado.columns:
                        if col == "Droguería": continue
                        col_str = str(col).lower()
                        if 'part.' in col_str or '%' in col_str: formatters_global[col] = lambda x: formato_ve(x, es_porcentaje=True)
                        elif 'unidades' in col_str or 'artículos' in col_str: formatters_global[col] = lambda x: formato_ve(x, es_unidad=True)
                        else: formatters_global[col] = lambda x: formato_ve(x)

                    st.dataframe(estilar_tabla_oscura(df_consolidado, formatters_global), use_container_width=True)

                    st.markdown("### ➕ Desglose Detallado por Sucursal")
                    for i, r in enumerate(reportes_filtrados):
                        with st.expander(f"🔹 {r['sede']} | 📦 Unidades: {formato_ve(r['total_unidades'], es_unidad=True)} | 💵 Compra: $ {formato_ve(r['total_dolares'])}"):
                            st.button("🗑️ Eliminar Registro", key=f"del_{r['id_real_fb']}", type="secondary", on_click=lambda id_d: db.collection("reportes_comparador").document(id_d).delete(), args=(r['id_real_fb'],))
                            st.dataframe(estilar_tabla_oscura(tablas_sedes_limpias[i], formatters_global), use_container_width=True)
            else:
                st.info(f"💡 No hay datos registrados en el sistema para el mes {mes_sel:02d}/{anio_sel}.")

    # ==========================================
    # PESTAÑA 2: CALENDARIO VISUAL E INTERACTIVO
    # ==========================================
    with tab2:
        st.subheader(f"🗓️ Planificación Visual de Cargas del Mes ({mes_sel:02d}/{anio_sel})")
        
        cal_mes = obtener_calendario(db, anio_sel, mes_sel)
        num_dias_mes = calendar.monthrange(anio_sel, mes_sel)[1]
        if st.session_state.dia_seleccionado > num_dias_mes:
            st.session_state.dia_seleccionado = num_dias_mes

        cols_header = st.columns(7)
        dias_semana_nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        for idx, name in enumerate(dias_semana_nombres):
            cols_header[idx].markdown(f"<div style='text-align: center; font-weight: bold; background-color: #1e1e1e; padding: 5px; border-radius: 5px;'>{name}</div>", unsafe_allow_html=True)

        semanas_matriz = calendar.monthcalendar(anio_sel, mes_sel)
        hoy_actual_date = hoy.date()

        for semana in semanas_matriz:
            cols_dia = st.columns(7)
            for i in range(7):
                dia_num = semana[i]
                if dia_num == 0:
                    cols_dia[i].write("")
                else:
                    fecha_str = f"{anio_sel}-{mes_sel:02d}-{dia_num:02d}"
                    info_dia = next((d for d in cal_mes if d.get("Fecha") == fecha_str), None)
                    
                    labs_del_dia = info_dia.get("Laboratorios", []) if info_dia else []
                    if isinstance(labs_del_dia, str):
                        cantidad_labs = len([l for l in labs_del_dia.split(",") if l.strip() and "DOMINGO" not in l.upper()])
                    else:
                        cantidad_labs = len([l for l in labs_del_dia if "DOMINGO" not in str(l).upper()])

                    es_domingo = (i == 6)
                    texto_boton = "DOMINGO" if es_domingo else f"{cantidad_labs} Labs"
                    
                    es_hoy = (hoy_actual_date.year == anio_sel and hoy_actual_date.month == mes_sel and hoy_actual_date.day == dia_num)
                    es_seleccionado = (st.session_state.dia_seleccionado == dia_num)
                 
                    marca = "🔴 " if es_hoy else ""
                    label_visual = f"{marca}{dia_num}\n\n{texto_boton}\n\n"
                    tipo_b = "primary" if es_seleccionado else "secondary"
  
                    if cols_dia[i].button(label_visual, key=f"cal_btn_{fecha_str}", type=tipo_b, use_container_width=True):
                        st.session_state.dia_seleccionado = dia_num
                        st.rerun()

        st.divider()
        
        # Panel de edición de laboratorios del día seleccionado
        dia_sel = st.session_state.dia_seleccionado
        fecha_sel_str = f"{anio_sel}-{mes_sel:02d}-{dia_sel:02d}"
        info_dia_sel = next((d for d in cal_mes if d.get("Fecha") == fecha_sel_str), None)
        
        st.markdown(f"### 🔍 Laboratorios para el Día: **{dia_sel:02d}/{mes_sel:02d}/{anio_sel}**")
        
        labs_actuales = info_dia_sel.get("Laboratorios", []) if info_dia_sel else []
        if isinstance(labs_actuales, str):
            labs_actuales = [l.strip().upper() for l in labs_actuales.split(",") if l.strip()]
            
        df_labs_dia = pd.DataFrame({
            "Laboratorio": pd.Series(labs_actuales, dtype="str"),
            "Eliminar": pd.Series([False] * len(labs_actuales), dtype="bool")
        })
 
        col_ed1, col_ed2 = st.columns([2, 1])
        with col_ed1:
            st.markdown("👇 **Escribe los laboratorios aquí.** Usa '+' para añadir. Marca **🗑️ Eliminar** y guarda para borrar.")
            df_editado = st.data_editor(
                df_labs_dia,
                key=f"editor_tabla_{fecha_sel_str}",
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Laboratorio": st.column_config.TextColumn("Nombre del Laboratorio", required=True),
                    "Eliminar": st.column_config.CheckboxColumn("🗑️ Eliminar", default=False)
                }
            )
        with col_ed2:
            st.write("")
            st.write("")
            if st.button("💾 Guardar Día", type="primary", use_container_width=True):
                nuevos_labs = []
                for _, row in df_editado.iterrows():
                    if not row.get("Eliminar", False):
                        val = str(row["Laboratorio"]).strip().upper()
                        if val and val not in ["NONE", "NAN", "<NA>"]:
                            nuevos_labs.append(val)
                 
                for d in cal_mes:
                    if d.get("Fecha") == fecha_sel_str:
                        d["Laboratorios"] = nuevos_labs
                        break
                 
                actualizar_calendario(db, anio_sel, mes_sel, pd.DataFrame(cal_mes))
                st.success(f"¡Guardado correctamente! ({len(nuevos_labs)} laboratorios)")
                time.sleep(0.5)
                st.rerun()

        st.divider()
        # --- NUEVA REASIGNACIÓN TEMPORAL DE CARGAS ---
        st.markdown("#### 🛠️ Reasignación Temporal de Cargas")
        st.markdown("Mueve todos los laboratorios de un día específico a otro día distinto. (Ajuste Temporal)")
        c_em1, c_em2, c_em3 = st.columns([1, 1, 2])
        
        dias_disponibles = list(range(1, num_dias_mes + 1))
        
        with c_em1:
            dia_origen = st.selectbox("📅 Día Origen (Desde):", dias_disponibles, index=dias_disponibles.index(dia_sel) if dia_sel in dias_disponibles else 0)
            
        with c_em2:
            dias_destino_validos = [d for d in dias_disponibles if d != dia_origen]
            dia_destino = st.selectbox("📅 Día Destino (Hacia):", dias_destino_validos)
            
        with c_em3:
            st.write("") 
            st.write("")
            if st.button(f"🔄 Mover del día {dia_origen} al {dia_destino}", type="secondary", use_container_width=True):
                origen_str = f"{anio_sel}-{mes_sel:02d}-{dia_origen:02d}"
                destino_str = f"{anio_sel}-{mes_sel:02d}-{dia_destino:02d}"
                
                idx_origen = next((i for i, d in enumerate(cal_mes) if d["Fecha"] == origen_str), None)
                idx_destino = next((i for i, d in enumerate(cal_mes) if d["Fecha"] == destino_str), None)
                
                labs_origen = cal_mes[idx_origen].get("Laboratorios", [])
                labs_destino = cal_mes[idx_destino].get("Laboratorios", [])
              
                if "DOMINGO" in str(labs_destino).upper():
                    st.error("❌ No puedes mover laboratorios hacia un Domingo.")
                elif not labs_origen:
                    st.warning("⚠️ El día origen está vacío, no hay nada que mover.")
                else:
                    combinados = list(set(labs_destino + labs_origen))
                    cal_mes[idx_destino]["Laboratorios"] = combinados
                    cal_mes[idx_origen]["Laboratorios"] = [] 
                   
                    actualizar_calendario(db, anio_sel, mes_sel, pd.DataFrame(cal_mes))
                    st.success(f"✅ ¡Carga movida con éxito del día {dia_origen} al día {dia_destino}!")
                    time.sleep(1.5)
                    st.rerun()

        st.markdown("**Copiar Planificación Mensual:**")
        if st.button("📥 Importar y sobreescribir desde el mes anterior", type="primary"):
            if mes_sel == 1:
                p_year, p_month = anio_sel - 1, 12
            else:
                p_year, p_month = anio_sel, mes_sel - 1
            
            prev_doc = db.collection("configuracion_calendario").document(f"{p_year}_{p_month:02d}").get()
            if prev_doc.exists:
                prev_dias = prev_doc.to_dict().get("dias", [])
                labs_sabados = [d.get("Laboratorios", []) for d in prev_dias if d.get("Día") == "Sábado"]
                labs_semana = [d.get("Laboratorios", []) for d in prev_dias if d.get("Día") in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]]
                
                nuevo_cal = generar_calendario_dinamico(anio_sel, mes_sel, labs_semana, labs_sabados)
                actualizar_calendario(db, anio_sel, mes_sel, nuevo_cal)
                st.success("✅ Planificación importada con éxito.")
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("❌ El mes anterior está vacío en la base de datos.")
                
        st.divider()

        # ==========================================
        # Administrador global de logos y laboratorios
        # ==========================================
        with st.expander("🖼️ Administrador Global de Logos y Laboratorios (Clic para abrir)", expanded=False):
            st.markdown("Busca, sube logos o **elimina laboratorios** del sistema y del calendario actual.")
            logos_actuales_db = obtener_logos_firebase()
            
            # Recopilamos todos los laboratorios
            nombres_visuales_globales = set()
            for key in logos_actuales_db.keys():
                nombres_visuales_globales.add(key.replace("_", " "))
                
            for dia in cal_mes:
                labs_dia = dia.get("Laboratorios", [])
                if isinstance(labs_dia, str):
                    labs_dia = [l.strip().upper() for l in labs_dia.split(",") if l.strip()]
                for l in labs_dia:
                    if l and "DOMINGO" not in str(l).upper():
                        nombres_visuales_globales.add(l.strip().upper())
            
            lista_todos_labs = sorted(list(nombres_visuales_globales))
            
            # --- NUEVO: Buscador Interactivo ---
            texto_busqueda = st.text_input("🔍 Buscar laboratorio (escribe para filtrar):", "").strip().upper()
            if texto_busqueda:
                lista_todos_labs = [lab for lab in lista_todos_labs if texto_busqueda in lab]

            if not lista_todos_labs:
                st.info("💡 No se encontraron laboratorios con ese nombre.")
            else:
                cols_logos = st.columns(4) 
                for idx, lab_name in enumerate(lista_todos_labs):
                    with cols_logos[idx % 4]:
                        # Diseño tipo "Tarjeta" para cada laboratorio
                        st.markdown("""<div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; margin-bottom: 15px;">""", unsafe_allow_html=True)
                        
                        lab_id_check = lab_name.replace(" ", "_")
                        estado_texto = "✅" if lab_id_check in logos_actuales_db and logos_actuales_db[lab_id_check] else "❌"
                        st.markdown(f"<div style='text-align:center; font-weight:bold; margin-bottom:10px;'>{lab_name} {estado_texto}</div>", unsafe_allow_html=True)
                        
                        logo_file = st.file_uploader("Subir", type=["png", "jpg", "jpeg"], key=f"global_logo_{lab_name}", label_visibility="collapsed")
                        
                        if logo_file:
                            with st.spinner("Guardando..."):
                                guardar_logo_firebase(lab_name, logo_file.getvalue())
                                st.success("Guardado")
                                time.sleep(1)
                                st.rerun()
                                
                        # --- NUEVO: Botón de Eliminar ---
                        if st.button("🗑️ Eliminar Lab", key=f"del_lab_{lab_name}", type="secondary", use_container_width=True):
                            with st.spinner("Eliminando..."):
                                # 1. Eliminar logo de Firebase
                                db.collection("configuracion_logos").document(lab_id_check).delete()
                                
                                # 2. Eliminar del calendario del mes actual
                                hubo_cambios = False
                                for dia in cal_mes:
                                    labs_dia = dia.get("Laboratorios", [])
                                    if isinstance(labs_dia, str):
                                        labs_dia = [l.strip().upper() for l in labs_dia.split(",") if l.strip()]
                                    
                                    if lab_name in labs_dia:
                                        labs_dia.remove(lab_name)
                                        dia["Laboratorios"] = labs_dia
                                        hubo_cambios = True
                                        
                                if hubo_cambios:
                                    actualizar_calendario(db, anio_sel, mes_sel, pd.DataFrame(cal_mes))
                                    
                                st.success(f"Eliminado")
                                time.sleep(1)
                                st.rerun()
                        
                        st.markdown("</div>", unsafe_allow_html=True)

    # ==========================================
    # REQUERIMIENTO 2 - PESTAÑA 3: TABLA RESUMEN DEL MES
    # ==========================================
    with tab3:
        st.subheader(f"📊 Cronograma Consolidado Tipo Tabla ({mes_sel:02d}/{anio_sel})")
        cal_mes_tabla = obtener_calendario(db, anio_sel, mes_sel)
        
        if cal_mes_tabla:
            # Estructuramos la información limpia para mostrar en formato lineal
            datos_tabla_resumen = []
            for d in cal_mes_tabla:
                labs = d.get("Laboratorios", [])
                labs_str = ", ".join(labs) if isinstance(labs, list) else str(labs)
                if not labs_str.strip(): labs_str = "SÍN PLANIFICAR"
                
                # Reformateamos la fecha para que esté en formato latino (DD-MM-YYYY)
                fecha_iso = d.get("Fecha", "")
                try:
                    fecha_latina = datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d-%m-%Y")
                except:
                    fecha_latina = fecha_iso

                datos_tabla_resumen.append({
                    "Fecha": fecha_latina,
                    "Día de la Semana": d.get("Día", ""),
                    "Laboratorios Asignados": labs_str
                })
            
            df_resumen_mes = pd.DataFrame(datos_tabla_resumen)
            
            # Aplicamos diseño oscuro uniforme
            st.dataframe(
                df_resumen_mes.style.set_properties(**{
                    'border': '1px solid #3a3a3a', 'color': '#ffffff', 'background-color': '#111111'
                }), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info("No hay datos de planificación para este mes.")

    # ==========================================
    # REQUERIMIENTO 3 - PESTAÑA 4: RASTREO BI-MES POR LABORATORIO
    # ==========================================
    with tab4:
        st.subheader("🔍 Matriz de Control de Cargas (Mes Actual y Pasado)")
        st.markdown("Verifica rápidamente qué sucursales han subido información de cada laboratorio.")
        
        # Determinamos las variables temporales del mes actual de ejecución y el anterior
        hoy_ejecucion = datetime.now()
        str_mes_actual = f"{hoy_ejecucion.year}-{hoy_ejecucion.month:02d}"
        
        primer_dia_actual = hoy_ejecucion.replace(day=1)
        fecha_mes_pasado = primer_dia_actual - timedelta(days=1)
        str_mes_pasado = f"{fecha_mes_pasado.year}-{fecha_mes_pasado.month:02d}"
        
        # Filtramos la lista completa de reportes recuperada de Firebase
        reportes_bi_mes = [
            r for r in lista_reportes_completa 
            if r.get("fecha_registro", "").startswith(str_mes_actual) or r.get("fecha_registro", "").startswith(str_mes_pasado)
        ]
        
        # Mapeamos: { LABORATORIO: { "Actual": {sedes}, "Pasado": {sedes} } }
        matriz_cargas = {}
        for rep in reportes_bi_mes:
            lab = rep.get("laboratorio", "").strip().upper()
            sede = rep.get("sede", "").strip().upper()
            fecha_reg = rep.get("fecha_registro", "")
            
            if not lab: continue
            if lab not in matriz_cargas:
                matriz_cargas[lab] = {"Actual": set(), "Pasado": set()}
            
            if fecha_reg.startswith(str_mes_actual):
                matriz_cargas[lab]["Actual"].add(sede)
            elif fecha_reg.startswith(str_mes_pasado):
                matriz_cargas[lab]["Pasado"].add(sede)
        
        # Transformamos la matriz en un DataFrame limpio
        filas_tabla_rastreo = []
        for lab, meses in matriz_cargas.items():
            sedes_actual = meses["Actual"]
            sedes_pasado = meses["Pasado"]
            
            # Calculamos las sedes que faltan en base a LISTA_SEDES global
            faltan_actual = [s for s in LISTA_SEDES if s not in sedes_actual]
            faltan_pasado = [s for s in LISTA_SEDES if s not in sedes_pasado]

            filas_tabla_rastreo.append({
                "Laboratorio / Marca": lab,
                f"✅ Cargaron - Mes Actual ({hoy_ejecucion.month:02d}/{hoy_ejecucion.year})": ", ".join(sorted(list(sedes_actual))) if sedes_actual else "Ninguna",
                f"❌ FALTAN - Mes Actual ({hoy_ejecucion.month:02d}/{hoy_ejecucion.year})": ", ".join(sorted(faltan_actual)) if faltan_actual else "Todas al día",
                f"✅ Cargaron - Mes Pasado ({fecha_mes_pasado.month:02d}/{fecha_mes_pasado.year})": ", ".join(sorted(list(sedes_pasado))) if sedes_pasado else "Ninguna",
                f"❌ FALTAN - Mes Pasado ({fecha_mes_pasado.month:02d}/{fecha_mes_pasado.year})": ", ".join(sorted(faltan_pasado)) if faltan_pasado else "Todas al día"
            })
            
        if filas_tabla_rastreo:
            df_rastreo = pd.DataFrame(filas_tabla_rastreo).sort_values(by="Laboratorio / Marca")
            st.dataframe(
                df_rastreo.style.set_properties(**{
                    'border': '1px solid #3a3a3a', 'color': '#ffffff', 'background-color': '#111111'
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No se han detectado cargas operativas en la base de datos para el período actual ni el anterior.")
   # ==========================================
    # PESTAÑA 5: MODO APERTURA GLOBAL (ESTÉTICA ORIGINAL OPTIMIZADA)
    # ==========================================
    with tab5:
        st.subheader("🚀 Gestión de Apertura (Global)")
        
        sede_apertura = st.selectbox("🏢 Selecciona la Sede para Apertura:", LISTA_SEDES, key="sede_ap")
        
        # --- 1. MEMORIA LOCAL (EVITA EL PARPADEO DE PANTALLA) ---
        if "sede_activa" not in st.session_state or st.session_state.sede_activa != sede_apertura:
            st.session_state.sede_activa = sede_apertura
            doc_apertura = db.collection("estado_apertura").document(sede_apertura).get()
            procesados_nube = doc_apertura.to_dict().get("procesados", []) if doc_apertura.exists else []
            st.session_state.procesados_locales = set(procesados_nube)
            
        # --- 2. EXTRAER CALENDARIO ---
        cal_mes_apertura = obtener_calendario(db, anio_sel, mes_sel)
        labs_del_mes = set()
        if cal_mes_apertura:
            for dia in cal_mes_apertura:
                labs_dia = dia.get("Laboratorios", [])
                if isinstance(labs_dia, str):
                    labs_dia = [l.strip().upper() for l in labs_dia.split(",") if l.strip()]
                for l in labs_dia:
                    if l and "DOMINGO" not in str(l).upper():
                        labs_del_mes.add(l.strip().upper())
        labs_del_mes = sorted(list(labs_del_mes))
        
        # --- 3. FUNCIONES CALLBACK (Se ejecutan en segundo plano sin reiniciar todo) ---
        def mover_a_procesado(lab):
            st.session_state.procesados_locales.add(lab)
            
        def regresar_a_pendiente(lab):
            st.session_state.procesados_locales.discard(lab)
            
        # --- 4. MÉTRICAS ---
        total_labs = len(labs_del_mes)
        procesados_del_mes = [lab for lab in st.session_state.procesados_locales if lab in labs_del_mes]
        cant_procesados = len(procesados_del_mes)
        cant_pendientes = total_labs - cant_procesados
        porcentaje = int((cant_procesados / total_labs) * 100) if total_labs > 0 else 0

        col_m1, col_m2, col_m3, col_m4 = st.columns([1, 1, 1, 2])
        col_m1.metric("📦 Planificados", total_labs)
        col_m2.metric("✅ Listos", cant_procesados)
        col_m3.metric("🔴 Pendientes", cant_pendientes)
        with col_m4:
            st.markdown(f"<div style='text-align: right; font-weight: bold;'>Progreso: {porcentaje}%</div>", unsafe_allow_html=True)
            st.progress(porcentaje / 100)
            
        st.divider()

        # --- 5. BUSCADOR Y GUARDADO EN LA NUBE ---
        col_b1, col_b2 = st.columns([3, 1])
        busqueda = col_b1.text_input("🔍 Buscar laboratorio...", "").strip().upper()
        
        # El botón maestro para sincronizar con el programa de escritorio
        if col_b2.button("💾 Guardar Cambios en la Nube", type="primary", use_container_width=True):
            with st.spinner("Sincronizando con el escritorio..."):
                db.collection("estado_apertura").document(sede_apertura).set({
                    "procesados": list(st.session_state.procesados_locales)
                }, merge=True)
                st.success("¡Guardado exitosamente!")
                
        st.info("💡 **Tip:** Mueve los laboratorios con los botones de abajo. **No olvides darle a 'Guardar Cambios en la Nube'** cuando termines.")

        # --- 6. LA ESTÉTICA DE DOS COLUMNAS ---
        col_pendientes, col_procesados = st.columns(2)
        
        with col_pendientes:
            st.markdown(f"""<div style="background-color:#1e1e1e; padding:15px; border-radius:10px; border-top:4px solid #ff4b4b; margin-bottom:15px;">
                        <h4 style="margin-top:0; margin-bottom:0; color:#ff8080;">🔴 Pendientes</h4></div>""", unsafe_allow_html=True)
            
            pendientes_lista = [l for l in labs_del_mes if l not in st.session_state.procesados_locales]
            if busqueda: pendientes_lista = [l for l in pendientes_lista if busqueda in l]
                
            if not pendientes_lista:
                st.success("¡Todo listo por aquí!")
            else:
                for lab in pendientes_lista:
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"🔬 **{lab}**")
                    # Usamos on_click para evitar el lag de recarga
                    c2.button("✔️ Listo", key=f"btn_p_{lab}_{sede_apertura}", on_click=mover_a_procesado, args=(lab,), use_container_width=True)

        with col_procesados:
            st.markdown(f"""<div style="background-color:#14231c; padding:15px; border-radius:10px; border-top:4px solid #10b981; margin-bottom:15px;">
                        <h4 style="margin-top:0; margin-bottom:0; color:#52d681;">✅ Procesados</h4></div>""", unsafe_allow_html=True)
            
            procesados_lista = sorted(list(st.session_state.procesados_locales))
            if busqueda: procesados_lista = [l for l in procesados_lista if busqueda in l]
                
            if not procesados_lista:
                st.write("Aún no hay procesados.")
            else:
                for lab in procesados_lista:
                    c1, c2 = st.columns([3, 1])
                    badge = "📅" if lab in labs_del_mes else "<span style='color:gray; font-size:12px;'>(Extra)</span>"
                    c1.markdown(f"✅ {lab} {badge}", unsafe_allow_html=True)
                    # Usamos on_click para evitar el lag de recarga
                    c2.button("❌ Quitar", key=f"btn_q_{lab}_{sede_apertura}", on_click=regresar_a_pendiente, args=(lab,), use_container_width=True)


    # ==========================================
    # PESTAÑA 6: CONTROL DE INVENTARIO Y ALERTAS (OPTIMIZADO)
    # ==========================================
    with tab6:
        st.subheader("📦 Control de Inventario Cruzado entre Sedes")
        st.markdown("Este módulo analiza los artículos para evitar sobrepasar el inventario de los proveedores. *Los reportes se vencen automáticamente a las 3 horas de cargados.*")

        ahora_local = datetime.utcnow() - timedelta(hours=4)
        reportes_activos = {}
        documentos_a_limpiar_inv = []
        
        for r in lista_reportes:
            fecha_reg_str = r.get("fecha_registro_inv", r.get("fecha_registro"))
            sede_lab = f"{r.get('sede','').strip().upper()}_{r.get('laboratorio','').strip().upper()}"
            doc_id_actual = f"{r.get('sede','').lower().replace(' ', '_')}_{r.get('laboratorio','').lower().replace(' ', '_')}"
            
            tiene_inventario = len(r.get("detalles_items", [])) > 0
            
            if tiene_inventario and fecha_reg_str:
                try:
                    fecha_doc = datetime.strptime(fecha_reg_str, "%Y-%m-%d %H:%M:%S")
                    
                    # Usamos el reloj local sincronizado para medir la diferencia
                    diferencia_horas = (ahora_local - fecha_doc).total_seconds() / 3600
                    
                    if diferencia_horas <= 3.0:
                        if sede_lab not in reportes_activos or \
                           datetime.strptime(reportes_activos[sede_lab].get("fecha_registro_inv", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S") < fecha_doc:
                            reportes_activos[sede_lab] = r
                    else:
                        # Si realmente pasaron 3 horas, vacía SOLO esta sede específica
                        documentos_a_limpiar_inv.append(doc_id_actual)
                except:
                    reportes_activos[sede_lab] = r
            elif tiene_inventario:
                reportes_activos[sede_lab] = r
        
        # Ejecuta la limpieza de Firebase de manera individual, sin afectar a los demás
        if documentos_a_limpiar_inv:
            for doc_id_borrar in documentos_a_limpiar_inv:
                try:
                    db.collection("reportes_comparador").document(doc_id_borrar).update({"detalles_items": []})
                except:
                    pass
                    
        lista_activos = list(reportes_activos.values())
        
        # --- 2. FILTRAR POR LABORATORIO ---
        
        laboratorios_disponibles = sorted(list(set([r.get("laboratorio", "").strip().upper() for r in lista_activos if r.get("laboratorio")])))
        
        if not laboratorios_disponibles:
            st.info("⏰ No hay cargas de inventario activas en este momento.")
        else:
            lab_seleccionado = st.selectbox("🧪 Selecciona el Laboratorio a Auditar:", laboratorios_disponibles)
            
            reportes_filtrados_lab = [r for r in lista_activos if r.get("laboratorio", "").strip().upper() == lab_seleccionado]
            
            # --- 3. CONSOLIDACIÓN INTELIGENTE DE ARTÍCULOS (Anti-Errores) ---
            consolidado = {}
            sedes_detectadas = set()
            
            for r in reportes_filtrados_lab:
                sede_actual = r.get("sede", "Desconocida").strip().upper()
                sedes_detectadas.add(sede_actual)
                
                for item in r.get("detalles_items", []):
                    cod = str(item.get("codigo", "")).strip()
                    prov = str(item.get("proveedor", "")).strip().upper()
                    desc = str(item.get("descripcion", "")).strip()
                    inv = int(item.get("inventario", 0))
                    pedida = int(item.get("cantidad", 0))
                    
                    llave = (cod, prov)
                    
                    if llave not in consolidado:
                        # Si es la primera vez que vemos este código, guardamos su descripción y su inventario
                        consolidado[llave] = {
                            "Código de Barra": cod,
                            "Descripción": desc,
                            "Proveedor": prov,
                            "Inv. Disp.": inv
                        }
                    else:
                        # Si el código ya existe, mantenemos la PRIMERA descripción.
                        # Pero si el nuevo inventario reportado es MENOR, nos quedamos con el menor (más seguro)
                        if inv < consolidado[llave]["Inv. Disp."]:
                            consolidado[llave]["Inv. Disp."] = inv
                            
                    # Sumamos lo pedido por esta sede
                    consolidado[llave][sede_actual] = consolidado[llave].get(sede_actual, 0) + pedida
            
            if not consolidado:
                st.warning(f"⚠️ No se encontraron detalles para {lab_seleccionado}.")
            else:
                df_pivot = pd.DataFrame(list(consolidado.values()))
                sedes_cols = sorted(list(sedes_detectadas))
                
                # Rellenar con 0 si una sede no pidió este producto específico
                for s in sedes_cols:
                    if s not in df_pivot.columns:
                        df_pivot[s] = 0
                    df_pivot[s] = df_pivot[s].fillna(0).astype(int)
                
                # 4. Cálculos y orden de columnas
                df_pivot["Total Solicitado"] = df_pivot[sedes_cols].sum(axis=1)
                df_pivot["Diferencia"] = df_pivot["Inv. Disp."] - df_pivot["Total Solicitado"]
                
                # Reglas de Alertas
                cond_excedido = df_pivot["Total Solicitado"] > df_pivot["Inv. Disp."]
                cond_precaucion = (df_pivot["Total Solicitado"] >= (df_pivot["Inv. Disp."] * 0.90)) & (~cond_excedido) & (df_pivot["Total Solicitado"] > 0)
                
                df_pivot["Estatus"] = np.where(cond_excedido, "🔴 EXCEDIDO", 
                                      np.where(cond_precaucion, "🟡 PRECAUCIÓN", "✅ OK"))
                
                df_pivot["Orden_Estatus"] = np.where(df_pivot["Estatus"] == "🔴 EXCEDIDO", 1,
                                            np.where(df_pivot["Estatus"] == "🟡 PRECAUCIÓN", 2, 3))
                
                # --- MÉTRICAS ---
                st.markdown(f"##### 📊 Resumen de Pedidos Cruzados: {lab_seleccionado}")
                c_met1, c_met2, c_met3 = st.columns(3)
                total_items = len(df_pivot)
                items_excedidos = len(df_pivot[df_pivot["Estatus"] == "🔴 EXCEDIDO"])
                items_precaucion = len(df_pivot[df_pivot["Estatus"] == "🟡 PRECAUCIÓN"])
                
                c_met1.metric("📦 PRODUCTOS", f"{total_items}")
                c_met2.metric("🚨 ALERTAS CRÍTICAS", f"{items_excedidos}")
                c_met3.metric("⚠️ ALERTAS PRECAUCIÓN", f"{items_precaucion}")
                
                # Buscador y Filtro
                col_b1, col_b2 = st.columns([2, 1])
                with col_b1:
                    busqueda_cod = st.text_input("🔍 Buscar por Producto, Código o Proveedor:", "")
                with col_b2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    mostrar_alertas = st.checkbox("⚠️ Ver solo alertas", value=False)
                
                if mostrar_alertas:
                    df_pivot = df_pivot[df_pivot["Estatus"].isin(["🔴 EXCEDIDO", "🟡 PRECAUCIÓN"])]
                    
                if busqueda_cod:
                    b = busqueda_cod.upper()
                    df_pivot = df_pivot[df_pivot['Código de Barra'].str.contains(b) | 
                                        df_pivot['Descripción'].str.upper().str.contains(b) | 
                                        df_pivot['Proveedor'].str.upper().str.contains(b)]
                
                # --- ORDENAMIENTO DE FILAS ---
                df_pivot = df_pivot.sort_values(by=["Orden_Estatus", "Proveedor", "Diferencia"], ascending=[True, True, True])
                
                # --- ORDENAMIENTO DE COLUMNAS (Inv. Disp. al lado del Total) ---
                columnas_ordenadas = ["Estatus", "Código de Barra", "Descripción", "Proveedor"] + sedes_cols + ["Total Solicitado", "Inv. Disp.", "Diferencia"]
                df_pivot = df_pivot[columnas_ordenadas]
                
                # --- DISEÑO VISUAL ---
                def colorear_filas_inventario(row):
                    if row["Estatus"] == "🔴 EXCEDIDO":
                        return ['background-color: #421212; color: #ff8080; font-weight: bold'] * len(row)
                    elif row["Estatus"] == "🟡 PRECAUCIÓN":
                        return ['background-color: #423812; color: #ffdd80; font-weight: bold'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    df_pivot.style.apply(colorear_filas_inventario, axis=1)\
                                  .format({"Inv. Disp.": "{:,.0f}", "Total Solicitado": "{:,.0f}", "Diferencia": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                    height=450
                )

                # --- 4. BOTÓN DE DESCARGA LIMPIA ---
                # Quitamos Estatus, Orden_Estatus (si no lo ocultamos) y Diferencia para el Excel descargable
                columnas_a_quitar = ["Estatus", "Orden_Estatus", "Diferencia"]
                df_descarga = df_pivot.drop(columns=[col for col in columnas_a_quitar if col in df_pivot.columns])
                csv = df_descarga.to_csv(index=False).encode('utf-8-sig')
                
                st.download_button(
                    label=f"📥 Descargar Cuadro {lab_seleccionado} (Sin Alertas)",
                    data=csv,
                    file_name=f"Consolidado_{lab_seleccionado}_{datetime.now().strftime('%d_%m_%H%M')}.csv",
                    mime="text/csv",
                    type="primary"
                )                
                 
# ==========================================
# VISTA 3: CONSOLIDADO TOTAL
# ==========================================
elif opcion == "Consolidado Total":
    st.header("🌍 Consolidado Total NY-COMPRAS")
    if db is not None:
        with st.spinner("Cargando..."):
            docs = db.collection("reportes_comparador").stream()
        lista_reportes = [dict(doc.to_dict(), id_real_fb=doc.id) for doc in docs]
            
        if lista_reportes:
            df_master = pd.DataFrame(lista_reportes)
            df_master['fecha_registro_dt'] = pd.to_datetime(df_master['fecha_registro']).dt.date
            
            st.markdown("### 📅 Filtrar por Rango de Fechas")
            col_f1, col_f2 = st.columns([1, 2])
            with col_f1:
                rango_fechas = st.date_input("Seleccione rango:", value=(df_master['fecha_registro_dt'].min(), df_master['fecha_registro_dt'].max()), format="DD/MM/YYYY")
            
            st.divider()

            if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
                df_master = df_master[(df_master['fecha_registro_dt'] >= rango_fechas[0]) & (df_master['fecha_registro_dt'] <= rango_fechas[1])]
                
                if df_master.empty:
                    st.warning("⚠️ Sin registros para las fechas seleccionadas.")
                else:
                    df_sedes = df_master.groupby("sede")[["total_dolares", "total_unidades"]].sum().reset_index().rename(columns={"sede": "Sede", "total_dolares": "Total Compra", "total_unidades": "Total Unidades"})
                    gran_total_usd = df_sedes["Total Compra"].sum()
                    gran_total_und = df_sedes["Total Unidades"].sum()
                    df_sedes['% Part. Dólares'] = (df_sedes["Total Compra"] / gran_total_usd * 100) if gran_total_usd > 0 else 0
                    df_sedes['% Part. Unidades'] = (df_sedes["Total Unidades"] / gran_total_und * 100) if gran_total_und > 0 else 0
                    df_sedes = df_sedes.sort_values(by="Total Compra", ascending=False)
                    
                    formatters_cons = {"Total Compra": lambda x: formato_ve(x), "Total Unidades": lambda x: formato_ve(x, es_unidad=True), "% Part. Dólares": lambda x: formato_ve(x, es_porcentaje=True), "% Part. Unidades": lambda x: formato_ve(x, es_porcentaje=True)}
                    
                    st.markdown("### 📌 Resumen Global")
                    col_m1, col_m2 = st.columns(2)
                    with col_m1: st.markdown(f"""<div style="background-color:#14231c; padding:25px; border-radius:12px; border-left:6px solid #10b981; text-align:center;"><span style="color:#a3cfbb; font-size:16px; font-weight:bold;">💵 Gran Total Compras</span><br><span style="color:#52d681; font-size:52px; font-weight:900;">$ {formato_ve(gran_total_usd)}</span></div>""", unsafe_allow_html=True)
                    with col_m2: st.markdown(f"""<div style="background-color:#101f30; padding:25px; border-radius:12px; border-left:6px solid #0d6efd; text-align:center;"><span style="color:#9ec5fe; font-size:16px; font-weight:bold;">📦 Gran Total Unidades</span><br><span style="color:#6ea8fe; font-size:52px; font-weight:900;">{formato_ve(gran_total_und, es_unidad=True)}</span></div>""", unsafe_allow_html=True)

                    st.divider()
                    st.markdown("### 🏆 Ranking de Consolidado por Sedes")
                    st.dataframe(estilar_tabla_oscura(df_sedes, formatters_cons), use_container_width=True)
                    
                    st.divider()
                    st.markdown("### ➕ Detalle de Compras (Laboratorios por Sede)")
                    for idx, row in df_sedes.iterrows():
                        df_filtro_sede = df_master[df_master["sede"] == row["Sede"]].copy()
                        if not df_filtro_sede.empty:
                            df_filtro_sede = df_filtro_sede.groupby("laboratorio")[["total_dolares", "total_unidades"]].sum().reset_index().rename(columns={"laboratorio": "Laboratorio", "total_dolares": "Total Compra", "total_unidades": "Total Unidades"})
                            df_filtro_sede['% Part. Dólares'] = (df_filtro_sede["Total Compra"] / row["Total Compra"] * 100) if row["Total Compra"] > 0 else 0
                            df_filtro_sede['% Part. Unidades'] = (df_filtro_sede["Total Unidades"] / row["Total Unidades"] * 100) if row["Total Unidades"] > 0 else 0
                            with st.expander(f"🔹 {row['Sede']} | 📦 Unidades: {formato_ve(row['Total Unidades'], es_unidad=True)} | 💵 Compra: $ {formato_ve(row['Total Compra'])}"):
                                st.dataframe(estilar_tabla_oscura(df_filtro_sede.sort_values(by="Total Compra", ascending=False), formatters_cons), use_container_width=True)
                    
                    st.divider()
                    st.markdown("### 🔬 Aporte Detallado por Laboratorio")
                    df_labs = df_master.groupby("laboratorio")[["total_dolares", "total_unidades"]].sum().reset_index().rename(columns={"laboratorio": "Laboratorio", "total_dolares": "Total Compra", "total_unidades": "Total Unidades"})
                    df_labs['% Part. Dólares'] = (df_labs["Total Compra"] / gran_total_usd * 100) if gran_total_usd > 0 else 0
                    df_labs['% Part. Unidades'] = (df_labs["Total Unidades"] / gran_total_und * 100) if gran_total_und > 0 else 0
                    st.dataframe(estilar_tabla_oscura(df_labs.sort_values(by="Total Compra", ascending=False), formatters_cons), use_container_width=True)
            else:
                st.info("👈 Por favor, selecciona una fecha de inicio y fin para generar el consolidado.")
        else:
            st.info("No hay datos registrados en el sistema aún. Carga un Excel para comenzar.")
    else:
        st.error("Error de conexión con Firebase.")

    # ==========================================
# VISTA 4: CARGAR COMPARADOR (SOLO SUBIDA)
# ==========================================
elif opcion == "Cargar Comparador":
    st.header("☁️ Panel Administrativo: Subir Comparador Maestro")
    st.markdown("Sube la última versión del Excel (`.xlsm`) para que todo el equipo pueda descargarla desde la pantalla principal.")
    
    tz_venezuela = timezone(timedelta(hours=-4))
    hoy_ve = datetime.now(tz_venezuela)
    
    fecha_esperada_str = hoy_ve.strftime("%d_%m")
    nombre_esperado = f"COMPARADOR_{fecha_esperada_str}"
    
    if db is not None:
        try:
            bucket = storage.bucket()
            doc_ref = db.collection("configuracion_global").document("comparador_maestro")
            
            st.divider()

            if "uploader_comp_key" not in st.session_state: 
                st.session_state.uploader_comp_key = 100
                
            uploaded_comp = st.file_uploader(
                f"Selecciona el archivo actualizado '{nombre_esperado}' (.xlsm)", 
                type=["xlsm"], 
                key=f"up_comp_{st.session_state.uploader_comp_key}"
            )

            if uploaded_comp is not None:
                nombre_archivo_subido = uploaded_comp.name.upper()
                
                if nombre_esperado not in nombre_archivo_subido:
                    st.error(f"❌ Error: El archivo debe llamarse o contener '{nombre_esperado}' en su nombre.")
                else:
                    st.info(f"✅ Archivo válido listo para subir: {uploaded_comp.name} ({(uploaded_comp.size / (1024*1024)):.2f} MB)")
                    
                    if st.button("🚀 Confirmar y Subir a la Nube", type="primary", use_container_width=True):
                        with st.spinner("Subiendo archivo pesado a Firebase Storage. Por favor no cierres la ventana..."):
                            try:
                                blob = bucket.blob("comparador_maestro/excel_actual.xlsm")
                                blob.upload_from_string(
                                    uploaded_comp.getvalue(), 
                                    content_type="application/vnd.ms-excel.sheet.macroEnabled.12"
                                )
                                
                                doc_ref.set({
                                    "ultima_actualizacion": hoy_ve.strftime("%d-%m-%Y %I:%M %p")
                                })
                                
                                st.success("🎉 ¡Archivo maestro actualizado con éxito para todo el equipo!")
                                time.sleep(2)
                                st.session_state.uploader_comp_key += 1
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Ocurrió un error al subir el Excel: {e}")
                                
        except Exception as err:
            st.error(f"Error de configuración con Storage: {err}")
    else:
        st.error("Error de conexión con Firebase. Verifica tus credenciales.")
    

