import streamlit as st
import os
os.environ["PSYCOPG_ALLOW_CYTHON"] = "1"
import psycopg2
import os
from dotenv import load_dotenv
from twilio.rest import Client
from datetime import datetime

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
    message = client.messages.create(
        from_="whatsapp:" + TWILIO_NUMBER,
        to="whatsapp:" + numero,
        body=texto
    )
    return message.sid

# Obtener historial de conversación
def obtener_conversacion(numero):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT role, message, timestamp
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
@st.cache_data(ttl=60)
def obtener_ultimos_chats():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (phone_number) phone_number, message, timestamp
        FROM chat_history
        ORDER BY phone_number, timestamp DESC
        LIMIT 50
    """)
    datos = cur.fetchall()
    cur.close()
    conn.close()
    return datos

# --- UI ---
menu = st.sidebar.radio("Selecciona vista:", ["📬 Conversaciones", "📌 Pedidos pendientes"])

if menu == "📬 Conversaciones":
    st.title("📬 Conversaciones completas")
    chats = obtener_ultimos_chats()
    numeros = [c[0] for c in chats]
    numero_seleccionado = st.selectbox("Selecciona un número para ver el chat:", numeros)

    if numero_seleccionado:
        st.subheader(f"Chat con {numero_seleccionado}")
        mensajes = obtener_conversacion(numero_seleccionado)

        for rol, msg, ts in mensajes:
            ts_str = ts.strftime("%Y-%m-%d %H:%M")
            if rol == "user":
                st.markdown(f"<div style='text-align: left; color: #333'><b>{ts_str}</b><br>👤 {msg}</div><hr>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align: right; color: #006400'><b>{ts_str}</b><br>🤖 {msg}</div><hr>", unsafe_allow_html=True)

        with st.form("responder_form"):
            respuesta = st.text_area("Responder mensaje:")
            if st.form_submit_button("Enviar respuesta"):
                try:
                    sid = enviar_mensaje(numero_seleccionado, respuesta)
                    st.success(f"✅ Enviado correctamente (SID: {sid})")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

elif menu == "📌 Pedidos pendientes":
    st.title("📌 Clientes que quieren separar prenda")
    alertas = obtener_alertas()

    for alerta in alertas:
        id_alerta, numero, nombre, mensaje, fecha = alerta
        st.markdown(f"**📞 {numero} – {nombre or 'Sin nombre'}**")
        st.markdown(f"🕒 {fecha.strftime('%Y-%m-%d %H:%M')}<br>💬 {mensaje}", unsafe_allow_html=True)

        col1, col2 = st.columns([2, 1])
        with col1:
            with st.form(f"responder_{id_alerta}"):
                texto = st.text_area("Responder al cliente:", key=f"texto_{id_alerta}")
                if st.form_submit_button("Enviar respuesta"):
                    try:
                        sid = enviar_mensaje(numero, texto)
                        st.success(f"✅ Enviado correctamente (SID: {sid})")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
        with col2:
            if st.button("✅ Marcar como respondido", key=f"boton_{id_alerta}"):
                marcar_respondido(id_alerta)
                st.success("Marcado como respondido")
                st.experimental_rerun()
