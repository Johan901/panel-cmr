import streamlit as st
import os
os.environ["PSYCOPG_ALLOW_CYTHON"] = "1"
import psycopg2
import os
from dotenv import load_dotenv
from twilio.rest import Client
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import requests
from PIL import Image
from io import BytesIO
from datetime import date


load_dotenv()

st.set_page_config(page_title="Panel Aurora", layout="wide")

# Twilio setup
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

# DB setup
def get_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        dbname=os.getenv("PG_DB"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        port=os.getenv("PG_PORT", "5432")
    )

# Enviar mensaje vía Twilio
def enviar_mensaje(numero, texto):
    client = Client(TWILIO_SID, TWILIO_TOKEN)

    # ✅ Asegurar formato correcto una sola vez
    if numero.startswith("whatsapp:"):
        numero = numero.replace("whatsapp:", "")

    message = client.messages.create(
        from_="whatsapp:" + TWILIO_NUMBER,
        to="whatsapp:" + numero,
        body=texto
    )
    return message.sid


# Guardar mensaje en chat_history como "assistant"
def guardar_mensaje(numero, texto, rol="assistant"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO chat_history (phone_number, role, message, timestamp)
        VALUES (%s, %s, %s, NOW())
    """, (numero, rol, texto))
    conn.commit()
    cur.close()
    conn.close()

def mostrar_imagen_twilio(media_url):
    try:
        response = requests.get(
            media_url,
            auth=(TWILIO_SID, TWILIO_TOKEN)
        )
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            st.image(image, width=300)
        else:
            st.warning("No se pudo cargar la imagen (Twilio)")
    except Exception as e:
        st.error(f"Error al mostrar imagen: {e}")

# Obtener historial de conversación
def obtener_conversacion(numero):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id AS sid, role, message, timestamp, media_url, quoted_sid
        FROM chat_history
        WHERE phone_number = %s
        ORDER BY timestamp ASC
    """, (numero,))
    datos = cur.fetchall()
    cur.close()
    conn.close()
    return datos



# Obtener alertas pendientes
def obtener_alertas():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, phone_number, nombre, mensaje, fecha
        FROM alertas_pendientes
        WHERE respondido = FALSE
        ORDER BY fecha DESC
    """)
    datos = cur.fetchall()
    cur.close()
    conn.close()
    return datos

# Marcar alerta como respondida
def marcar_respondido(alerta_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE alertas_pendientes
        SET respondido = TRUE
        WHERE id = %s
    """, (alerta_id,))
    conn.commit()
    cur.close()
    conn.close()

# Listar chats recientes únicos
def obtener_ultimos_chats(fecha_filtrada):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (phone_number) phone_number, message, timestamp
        FROM chat_history
        WHERE DATE(timestamp AT TIME ZONE 'America/Bogota') = %s
        ORDER BY phone_number, timestamp DESC
        LIMIT 100
    """, (fecha_filtrada,))
    datos = cur.fetchall()
    cur.close()
    conn.close()
    return datos


# --- UI ---
menu = st.sidebar.radio("Selecciona vista:", ["📬 Conversaciones", "📌 Pedidos pendientes"])

if menu == "📬 Conversaciones":
    st.title("📬 Conversaciones completas")

    # Filtro por fecha sin zonas ni problemas
    fecha_seleccionada = st.date_input("📅 Filtrar por día:", value=date.today())

    # Cargar todos los chats desde la base
    chats = obtener_ultimos_chats(fecha_seleccionada)

    # Asegurar que cada mensaje tenga solo fecha (sin hora) y filtrar
    numeros = [c[0] for c in chats]

    if not numeros:
        st.warning("No hay conversaciones en la fecha seleccionada.")
    else:
        if "vista_conversacion_directa" in st.session_state:
            numero_seleccionado = st.session_state["vista_conversacion_directa"]
            del st.session_state["vista_conversacion_directa"]
        else:
            numero_seleccionado = st.selectbox("Selecciona un número para ver el chat:", numeros)

        if numero_seleccionado:
            st.subheader(f"Chat con {numero_seleccionado}")
            mensajes = obtener_conversacion(numero_seleccionado)

        # Crear diccionario para buscar mensajes por SID
        referencia_mensajes = {}
        for sid, rol, msg, ts, media_url, quoted_sid in mensajes:
            referencia_mensajes[sid] = (rol, msg, ts)

        # Mostrar mensajes
        for sid, rol, msg, ts, media_url, quoted_sid in mensajes:
            ts_str = ts.strftime("%Y-%m-%d %H:%M")

            # 🔹 Mostrar respuesta citada si existe
            if quoted_sid and quoted_sid in referencia_mensajes:
                _, msg_citado, _ = referencia_mensajes[quoted_sid]
                st.markdown(f"""
                    <div style='padding: 8px; margin-bottom: 4px; background-color: #f0f0f0; border-left: 4px solid #999'>
                    <b>↪ Respuesta a:</b><br>{msg_citado}
                    </div>
                """, unsafe_allow_html=True)

            # 🔸 Mostrar mensaje actual
            if rol == "user":
                st.markdown(f"<div style='text-align: left; color: #333'><b>{ts_str}</b><br>👤 {msg}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align: right; color: #006400'><b>{ts_str}</b><br>🤖 {msg}</div>", unsafe_allow_html=True)

            # 🖼️ Mostrar imagen si existe
            if media_url:
                mostrar_imagen_twilio(media_url)
            elif "twilio.com" in msg and "Media" in msg:
                import re
                match = re.search(r"\((https://api\.twilio\.com[^\)]+)\)", msg)
                if match:
                    url_directa = match.group(1)
                    mostrar_imagen_twilio(url_directa)

            st.markdown("<hr>", unsafe_allow_html=True)


        # Auto-refresh cada 10 segundos (10,000 ms)
        st_autorefresh(interval=10000, key="refresh")

        # Inicializar respuesta si no existe
        if "respuesta" not in st.session_state:
            st.session_state["respuesta"] = ""

        with st.form("responder_form"):
            respuesta = st.text_area("Responder mensaje:", value=st.session_state["respuesta"], key="input_area")
            
            if st.form_submit_button("Enviar respuesta"):
                try:
                    sid = enviar_mensaje(numero_seleccionado, respuesta)
                    guardar_mensaje(numero_seleccionado, respuesta, rol="assistant")
                    st.success(f"✅ Enviado correctamente (SID: {sid})")
                    st.session_state["respuesta"] = ""  #Limpiar solo si se envió
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        with st.form("form_imagen"):
            st.markdown("📷 **Enviar imagen al cliente:**")
            imagen = st.file_uploader("Selecciona una imagen", type=["jpg", "jpeg", "png"], key="upload_image_form")
            texto_imagen = st.text_input("Mensaje opcional junto a la imagen", "")

            if st.form_submit_button("Enviar imagen"):
                if imagen is None:
                    st.warning("Debes seleccionar una imagen.")
                else:
                    try:
                        # 🔄 1. Subir imagen temporal a imgbb (u otro servidor público)
                        import base64
                        imgbb_api_key = os.getenv("IMGBB_API_KEY")
                        if not imgbb_api_key:
                            st.error("⚠️ Falta configurar la API Key de imgbb en el archivo .env (IMGBB_API_KEY)")
                        else:
                            imagen_bytes = imagen.read()
                            imagen_b64 = base64.b64encode(imagen_bytes).decode("utf-8")
                            res = requests.post(
                                "https://api.imgbb.com/1/upload",
                                data={"key": imgbb_api_key, "image": imagen_b64}
                            )
                            res.raise_for_status()
                            media_url = res.json()["data"]["url"]

                            # 🔁 2. Enviar por Twilio
                            client = Client(TWILIO_SID, TWILIO_TOKEN)
                            message = client.messages.create(
                                from_="whatsapp:" + TWILIO_NUMBER,
                                to="whatsapp:" + numero_seleccionado,
                                body=texto_imagen or None,
                                media_url=[media_url]
                            )

                            # 💾 3. Guardar en chat_history
                            conn = get_connection()
                            cur = conn.cursor()
                            cur.execute("""
                                INSERT INTO chat_history (phone_number, role, message, media_url, timestamp)
                                VALUES (%s, %s, %s, %s, NOW())
                            """, (numero_seleccionado, "assistant", texto_imagen or "", media_url))
                            conn.commit()
                            cur.close()
                            conn.close()

                            st.success("✅ Imagen enviada correctamente.")
                    except Exception as e:
                        st.error(f"❌ Error al enviar imagen: {e}")


elif menu == "📌 Pedidos pendientes":
    st.title("📌 Clientes que quieren separar prenda")
    st_autorefresh(interval=10000, key="refresh_alertas")

    # Filtro por fecha
    fecha_inicio = st.date_input("📅 Ver alertas del día:", datetime.now().date())
    
    alertas = obtener_alertas()
    alertas_filtradas = [a for a in alertas if a[4].date() == fecha_inicio]

    for alerta in alertas_filtradas:
        id_alerta, numero, nombre, mensaje, fecha = alerta
        st.markdown(f"**📞 {numero} – {nombre or 'Sin nombre'}**")
        st.markdown(f"🕒 {fecha.strftime('%Y-%m-%d %H:%M')}<br>💬 {mensaje}", unsafe_allow_html=True)

        if st.button("🗨️ Ir a la conversación", key=f"ir_chat_{id_alerta}"):
            st.session_state["vista_conversacion_directa"] = numero
            st.experimental_rerun()

        st.markdown("---")
