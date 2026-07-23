# ==============================================================================
# SECCIÓN 1: IMPORTACIÓN DE LIBRERÍAS
# ==============================================================================
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS

# ==============================================================================
# SECCIÓN 2: CONFIGURACIÓN DE LA INTELIGENCIA ARTIFICIAL (GEMINI API)
# ==============================================================================
# Clave privada para comunicarnos con los servidores de Google Gemini
GEMINI_API_KEY = "AQ.Ab8RN6Jd2jIACONsXuFajVYRdDqyo3UFPlfyb1RZyxHEycRUGg"
genai.configure(api_key=GEMINI_API_KEY)

# Inicializamos el modelo ultra rápido 'gemini-1.5-flash'
model = genai.GenerativeModel('gemini-1.5-flash')

# Personalidad e instrucciones base para Logan
SYSTEM_PROMPT = """
Eres Logan, un asistente de domótica inteligente, amigable, ingenioso y eficiente.
Tu función principal es ayudar al usuario a controlar los dispositivos de su hogar.
Responde de forma breve, natural y conversacional (ideal para ser leído en voz alta).
"""

# ==============================================================================
# SECCIÓN 3: CONFIGURACIÓN DEL SERVIDOR WEB (FLASK)
# ==============================================================================
app = Flask(__name__)
# Permite que la página web se comunique con el servidor sin bloqueos de navegador (CORS)
CORS(app)

# ==============================================================================
# SECCIÓN 4: VARIABLES DE ESTADO GLOBAL
# ==============================================================================
# Guarda la memoria de los dispositivos en el servidor
estado_rele = "OFF"       # Estado de la luz: "ON" u "OFF"
movimiento_sensor = "0"   # Estado del sensor PIR: "1" (presencia) o "0" (sin presencia)

# ==============================================================================
# SECCIÓN 5: RUTAS Y ENDPOINTS (COMUNICACIÓN CON USUARIOS Y ESP32)
# ==============================================================================

# 🎙️ RUTA 1: Procesar las órdenes habladas o escritas del usuario
@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele
    
    # Recibir el mensaje mandado desde la página web
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "No escuché ningún mensaje.", "estado_rele": estado_rele})

    mensaje_minusc = user_message.lower()

    # --- Detección de Intenciones de Domótica ---
    if any(palabra in mensaje_minusc for palabra in ["enciende", "prende", "encender", "prendas"]):
        estado_rele = "ON"
    elif any(palabra in mensaje_minusc for palabra in ["apaga", "apagar", "apagues"]):
        estado_rele = "OFF"

    # --- Consultar a Gemini API ---
    prompt_completo = f"{SYSTEM_PROMPT}\nEstado actual de la luz: {estado_rele}\nUsuario dice: {user_message}\nLogan:"
    
    try:
        response = model.generate_content(prompt_completo)
        respuesta_texto = response.text.strip()
    except Exception as e:
        print(f"❌ Error consultando a Gemini: {e}")
        respuesta_texto = f"Entendido. Cambié el estado del relé a {estado_rele}."

    # Devolver respuesta a la interfaz web
    return jsonify({
        "reply": respuesta_texto,
        "estado_rele": estado_rele
    })


# 🔌 RUTA 2: Consulta del ESP32 (El ESP32 pregunta qué hacer con el Relé)
@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    # Retorna si el relé debe estar ON u OFF en formato JSON
    return jsonify({
        "relay": estado_rele
    })


# 📡 RUTA 3: El ESP32 envía lecturas de sensores al servidor
@app.route('/esp32/update', methods=['POST'])
def esp32_update():
    global movimiento_sensor
    data = request.get_json() or {}
    
    # Actualiza el estado del sensor si el ESP32 lo envía
    if "motion" in data:
        movimiento_sensor = str(data["motion"])
        
    return jsonify({"status": "ok", "relay": estado_rele})


# 🌐 RUTA 4: Verificación de estado general del servidor en navegador
@app.route('/status', methods=['GET'])
def status():
    return f"""
    <h1>🤖 Estado del Servidor de Logan</h1>
    <p><b>Estado del Relé (Luz):</b> {estado_rele}</p>
    <p><b>Movimiento Sensor:</b> {movimiento_sensor}</p>
    <p><b>IA Activa:</b> Google Gemini API (gemini-1.5-flash)</p>
    """

# ==============================================================================
# SECCIÓN 6: ARRANCAR EL SERVIDOR
# ==============================================================================
if __name__ == '__main__':
    # Arranca el servidor localmente en el puerto 5000
    print("🚀 Servidor de Logan iniciando con Gemini API...")
    app.run(host='0.0.0.0', port=5000, debug=True)