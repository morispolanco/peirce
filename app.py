import streamlit as st
import sqlite3
import hashlib
from openai import OpenAI
import time

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="Vigía SaaS", layout="wide")

ADMIN_USER = "mp"
ADMIN_PASS = "Mita1962"

# -----------------------------
# DB
# -----------------------------
conn = sqlite3.connect("app.db", check_same_thread=False)
c = conn.cursor()

# Users
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT
)
""")

# Historial
c.execute("""
CREATE TABLE IF NOT EXISTS historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    problema TEXT,
    resultado TEXT,
    timestamp TEXT
)
""")

# Usage (estructura nueva)
c.execute("""
CREATE TABLE IF NOT EXISTS usage (
    username TEXT PRIMARY KEY,
    requests INTEGER,
    max_requests INTEGER
)
""")

conn.commit()

# -----------------------------
# MIGRACIÓN AUTOMÁTICA
# -----------------------------
try:
    c.execute("ALTER TABLE usage ADD COLUMN max_requests INTEGER DEFAULT 10")
    conn.commit()
except:
    pass  # ya existe

# Asegurar datos
c.execute("UPDATE usage SET max_requests = 10 WHERE max_requests IS NULL")
conn.commit()

# -----------------------------
# HELPERS
# -----------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def crear_usuario(username, password, max_requests):
    try:
        c.execute("INSERT INTO users VALUES (?, ?)", 
                  (username, hash_password(password)))
        
        c.execute("INSERT INTO usage VALUES (?, ?, ?)", 
                  (username, 0, max_requests))
        
        conn.commit()
        return True
    except:
        return False

def eliminar_usuario(username):
    c.execute("DELETE FROM users WHERE username=?", (username,))
    c.execute("DELETE FROM usage WHERE username=?", (username,))
    c.execute("DELETE FROM historial WHERE username=?", (username,))
    conn.commit()

def login_usuario(username, password):
    if username == ADMIN_USER and password == ADMIN_PASS:
        return "admin"
    
    c.execute("SELECT * FROM users WHERE username=? AND password=?", 
              (username, hash_password(password)))
    
    return "user" if c.fetchone() else None

def get_usage_data(username):
    c.execute("SELECT requests, max_requests FROM usage WHERE username=?", (username,))
    row = c.fetchone()
    return row if row else (0, 10)

def increment_usage(username):
    c.execute("UPDATE usage SET requests = requests + 1 WHERE username=?", (username,))
    conn.commit()

def update_max_requests(username, new_limit):
    c.execute("UPDATE usage SET max_requests=? WHERE username=?", 
              (new_limit, username))
    conn.commit()

def reset_usage(username):
    c.execute("UPDATE usage SET requests=0 WHERE username=?", (username,))
    conn.commit()

def save_historial(username, problema, resultado):
    c.execute(
        "INSERT INTO historial (username, problema, resultado, timestamp) VALUES (?, ?, ?, ?)",
        (username, problema, resultado, time.strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()

def get_historial(username):
    c.execute("SELECT problema, resultado, timestamp FROM historial WHERE username=?", (username,))
    return c.fetchall()

def get_all_users():
    c.execute("SELECT username FROM users")
    return [u[0] for u in c.fetchall()]

# -----------------------------
# OPENROUTER
# -----------------------------
if "OPENROUTER_API_KEY" not in st.secrets:
    st.error("Falta API KEY")
    st.stop()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=st.secrets["OPENROUTER_API_KEY"]
)

# -----------------------------
# SESSION
# -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "role" not in st.session_state:
    st.session_state.role = None

# -----------------------------
# LOGIN
# -----------------------------
if not st.session_state.user:
    st.title("🔐 Login")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        role = login_usuario(username, password)

        if role:
            st.session_state.user = username
            st.session_state.role = role
            st.success("Bienvenido")
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

    st.stop()

# -----------------------------
# ADMIN PANEL
# -----------------------------
if st.session_state.role == "admin":

    st.title("🛠️ Panel de Administración")

    if st.button("Cerrar sesión"):
        st.session_state.user = None
        st.session_state.role = None
        st.rerun()

    # Crear usuario
    st.subheader("👥 Crear usuario")

    new_user = st.text_input("Nuevo usuario")
    new_pass = st.text_input("Contraseña", type="password")
    new_limit = st.number_input("Límite de usos", min_value=1, value=10)

    if st.button("Crear usuario"):
        if crear_usuario(new_user, new_pass, new_limit):
            st.success("Usuario creado")
        else:
            st.error("Ya existe")

    # Configurar límites
    st.subheader("⚙️ Configurar límites")

    usuarios = get_all_users()

    if usuarios:
        user_sel = st.selectbox("Seleccionar usuario", usuarios)

        uso_actual, current_limit = get_usage_data(user_sel)

        new_limit = st.number_input(
            "Nuevo límite",
            min_value=1,
            value=current_limit
        )

        if st.button("Actualizar límite"):
            update_max_requests(user_sel, new_limit)
            st.success("Límite actualizado")

        if st.button("Resetear uso"):
            reset_usage(user_sel)
            st.success("Uso reiniciado")

    # Eliminar usuario
    st.subheader("🗑️ Eliminar usuario")

    if usuarios:
        user_del = st.selectbox("Eliminar usuario", usuarios, key="delete")

        if st.button("Eliminar"):
            eliminar_usuario(user_del)
            st.success("Usuario eliminado")
            st.rerun()

    st.stop()

# -----------------------------
# APP USUARIO
# -----------------------------
st.title(f"🧠 Vigía - Usuario: {st.session_state.user}")

if st.button("Cerrar sesión"):
    st.session_state.user = None
    st.session_state.role = None
    st.rerun()

uso_actual, max_uso = get_usage_data(st.session_state.user)

if uso_actual >= max_uso:
    st.warning("Has alcanzado tu límite de uso")
    st.stop()

# Inputs
empresa = st.text_input("Tipo de negocio")
area = st.selectbox("Área", ["Ventas", "Marketing", "Operaciones", "Finanzas"])
problema = st.text_area("Problema")
datos = st.text_area("Datos adicionales")

# IA
def generar_respuesta():
    prompt = f"""
Actúa como consultor de negocios.

Negocio: {empresa}
Área: {area}
Problema: {problema}
Datos: {datos}

Genera:
- Diagnóstico
- 3 hipótesis
- Mejor hipótesis
- Acciones claras
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )

    return response.choices[0].message.content

if st.button("Analizar"):
    if not problema:
        st.warning("Describe el problema")
    else:
        with st.spinner("Analizando..."):
            resultado = generar_respuesta()

            save_historial(st.session_state.user, problema, resultado)
            increment_usage(st.session_state.user)

        st.success("Análisis listo")
        st.markdown(resultado)

# Historial
st.subheader("📁 Historial")

for h in get_historial(st.session_state.user)[::-1]:
    with st.expander(f"{h[2]} - {h[0][:40]}"):
        st.write(h[1])

# Sidebar
st.sidebar.write(f"Uso: {uso_actual}/{max_uso}")
