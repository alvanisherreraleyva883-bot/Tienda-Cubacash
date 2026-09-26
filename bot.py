import os, json, random, datetime
from flask import Flask
from threading import Thread, Lock
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# ========== CONFIG LIMPIA PARA VENDER ==========
TOKEN = os.environ.get("TOKEN")
ADMIN_CHANNEL_ID = ""
CANAL_PAGOS_ID = ""
ADMIN_USER_ID = 0
TARJETA = ""
MOVIL = ""
WALLET_BEP20 = ""
SOPORTE_USERNAME = ""
# ===============================================

if not TOKEN:
    print("❌ ERROR: No hay TOKEN en Environment de Render")
    # No salimos para que Flask siga vivo y veas el error en logs

MENSAJE_FINAL = "✅ Pedido registrado. Le pagaremos en breve. Gracias por preferirnos 🙏\n\nUsa /tienda para nuevo pedido"
ADVERTENCIA = "⚠️ ATENCIÓN:\nLa captura debe verse con TOTAL CLARIDAD (monto, fecha, referencia).\n\n🚫 Cualquier intento de engaño, captura falsa, editada o estafa = BANEO PERMANENTE."
MENSAJE_AGOTADO = "⚠️ Saldo ETECSA agotado por hoy límite 3\nPor favor vuelve mañana."
MENSAJE_CERRADO = """🌙 ¡Tienda CERRADA ahora mismo! 🔒\n\n🕒 Horario:\nDe 8:00 AM a 10:30 PM Hora Cuba 🇨🇺"""

app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot activo - CubanStore"

PRECIOS_FILE = "precios.json"
STOCK_FILE = "stock.json"
TIENDA_FILE = "tienda.json"
TRANSFER_FILE = "transferencias.json"
LIMITE_DIARIO = 3

lock_precios = Lock()
lock_stock = Lock()
lock_tienda = Lock()
lock_transfer = Lock()
lock_pendientes = Lock()

def cargar_precios():
    if os.path.exists(PRECIOS_FILE):
        try:
            with open(PRECIOS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"saldo_compra": 950, "saldo_venta": 850, "usdt_compra": 360, "usdt_venta": 350}

def guardar_precios(d):
    with lock_precios:
        with open(PRECIOS_FILE, "w", encoding="utf-8") as f: json.dump(d, f)

def cargar_stock():
    if os.path.exists(STOCK_FILE):
        try:
            with open(STOCK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"saldo": float(data.get("saldo", 0)), "usdt": float(data.get("usdt", 0))}
        except: pass
    return {"saldo": 0, "usdt": 0}

def guardar_stock(d):
    with lock_stock:
        with open(STOCK_FILE, "w", encoding="utf-8") as f: json.dump(d, f)

def cargar_tienda():
    if os.path.exists(TIENDA_FILE):
        try:
            with open(TIENDA_FILE, "r", encoding="utf-8") as f: return f.read().strip() == "True" or json.load(f).get("cerrada", False)
        except: pass
    return False

def guardar_tienda(cerrada):
    with lock_tienda:
        with open(TIENDA_FILE, "w", encoding="utf-8") as f: json.dump({"cerrada": cerrada}, f)

def cargar_transfer():
    if not os.path.exists(TRANSFER_FILE): return {"usadas": 0, "fecha": str(datetime.date.today())}
    try:
        with open(TRANSFER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("fecha")!= str(datetime.date.today()): return {"usadas": 0, "fecha": str(datetime.date.today())}
        return data
    except: return {"usadas": 0, "fecha": str(datetime.date.today())}

def guardar_transfer(data):
    with lock_transfer:
        with open(TRANSFER_FILE, "w", encoding="utf-8") as f: json.dump(data, f)

precios = cargar_precios()
stock = cargar_stock()
tiendaCerrada = cargar_tienda()
PENDIENTES = {}
PAGOS_INFO = {}
ORDENES_ACTIVAS = {}

def gen_id(): return f"{random.randint(1000, 9999)}"

#... [TODAS TUS FUNCIONES DE ABAJO SE QUEDAN IGUAL]...
# Te dejo el resto de funciones igual que las tenias, solo copia desde aqui hasta el final que te puse abajo

async def cancelar_automatico(context):
    data = context.job.data
    pid = data["pid"]; uid = data["uid"]
    tipo = data.get("tipo", "compra_saldo")
    monto = data.get("monto", 0); total = data.get("total", 0)
    usuario = data.get("usuario", "Usuario"); username = data.get("username", "")
    if pid not in ORDENES_ACTIVAS: return
    ORDENES_ACTIVAS.pop(pid, None)
    with lock_pendientes: PENDIENTES.pop(pid, None)
    if uid in context.application.user_data:
        try: context.application.user_data[uid].clear()
        except: pass
    if "compra" in tipo:
        titulo_user = "❌ COMPRA CANCELADA"; motivo_user = "Tiempo expirado (20 min)"
        extra_user = "Puedes hacer una nueva compra cuando quieras."
        tipo_admin = "Compra"
    else:
        titulo_user = "❌ VENTA CANCELADA"; motivo_user = "Tiempo expirado (20 min)"
        extra_user = "Puedes hacer una nueva venta cuando quieras."
        tipo_admin = "Venta"
    texto_usuario = f"{titulo_user}\n\nOrden #{pid} CANCELADA ❌\nMotivo: {motivo_user}\n{extra_user}\n\nUsa /tienda"
    texto_admin = f"⚠️ {titulo_user} #{pid}\nUsuario: {usuario} {username}\nTipo: {tipo_admin}\nMonto: {monto}\nTotal: {total:.0f}"
    try:
        await context.bot.send_message(uid, texto_usuario)
        if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, texto_admin)
    except Exception as e: print(f"Error auto-cancel: {e}")

async def cmd_stock(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args:
        await u.message.reply_text(f"📦 STOCK:\nSaldo: {stock['saldo']:.0f}\nUSDT: {stock['usdt']:.0f}\n\nUso:\n/stock saldo 100\n/stock usdt 50\n/stock ver"); return
    if c.args[0].lower() == "ver":
        await u.message.reply_text(f"📦 STOCK:\nSaldo: {stock['saldo']:.0f}\nUSDT: {stock['usdt']:.0f}"); return
    if len(c.args) < 2: return await u.message.reply_text("Uso: /stock saldo 100")
    tipo = c.args[0].lower()
    try: cantidad = float(c.args[1].replace(",", "."))
    except: return await u.message.reply_text("Cantidad no válida")
    if tipo in ["saldo", "cup"]: stock["saldo"] = cantidad; guardar_stock(stock); await u.message.reply_text(f"✅ Saldo: {cantidad:.0f}")
    elif tipo in ["usdt", "crypto"]: stock["usdt"] = cantidad; guardar_stock(stock); await u.message.reply_text(f"✅ USDT: {cantidad:.0f}")

async def cambiar_saldo(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['saldo_compra']}")
    precios["saldo_compra"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ Compra -> {precios['saldo_compra']}")
async def cambiar_venta(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['saldo_venta']}")
    precios["saldo_venta"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ Venta -> {precios['saldo_venta']}")
async def cambiar_usdtc(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['usdt_compra']}")
    precios["usdt_compra"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ USDT Compra -> {precios['usdt_compra']}")
async def cambiar_usdtv(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['usdt_venta']}")
    precios["usdt_venta"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ USDT Venta -> {precios['usdt_venta']}")
async def ver_precios(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    await u.message.reply_text(f"PRECIOS:\nCompra saldo: {precios['saldo_compra']}\nVenta saldo: {precios['saldo_venta']}\nUSDT C: {precios['usdt_compra']}\nUSDT V: {precios['usdt_venta']}\n\nSTOCK:\nSaldo: {stock['saldo']:.0f}\nUSDT: {stock['usdt']:.0f}")
async def cmd_gaste1(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    data = cargar_transfer(); data["usadas"] = min(data["usadas"] + 1, LIMITE_DIARIO); guardar_transfer(data); await u.message.reply_text(f"✅ Hoy: {data['usadas']}/{LIMITE_DIARIO}")
async def cmd_reset(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    guardar_transfer({"usadas": 0, "fecha": str(datetime.date.today())}); await u.message.reply_text("♻️ Reseteado")
async def cmd_estado(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    data = cargar_transfer(); await u.message.reply_text(f"📊 Hoy {data['fecha']}: {data['usadas']}/{LIMITE_DIARIO}\nTienda: {'CERRADA' if tiendaCerrada else 'ABIERTA'}\nStock S: {stock['saldo']:.0f} | U: {stock['usdt']:.0f}")
async def cmd_cerrar(u,c):
    global tiendaCerrada
    if u.effective_user.id!= ADMIN_USER_ID: return
    tiendaCerrada = True; guardar_tienda(True); await u.message.reply_text("🔒 CERRADA")
async def cmd_abrir(u,c):
    global tiendaCerrada
    if u.effective_user.id!= ADMIN_USER_ID: return
    tiendaCerrada = False; guardar_tienda(False); await u.message.reply_text("🔓 ABIERTA")

async def mostrar_menu(u,c):
    if tiendaCerrada:
        if isinstance(u,Update): await u.message.reply_text(MENSAJE_CERRADO)
        else: await u.edit_message_text(MENSAJE_CERRADO); return
    kb=[[InlineKeyboardButton("📲💳 Comprar saldo",callback_data="comprar_saldo")],[InlineKeyboardButton("💵📱 Vender saldo",callback_data="vender_saldo")],[InlineKeyboardButton("🚀🪙 Comprar USDT",callback_data="comprar_crypto")],[InlineKeyboardButton("💸🔗 Vender USDT",callback_data="vender_crypto")]]
    if isinstance(u,Update): await u.message.reply_text("🛍️ Elige:",reply_markup=InlineKeyboardMarkup(kb))
    else: await u.edit_message_text("🛍️ Elige:",reply_markup=InlineKeyboardMarkup(kb))

async def tienda(u,c): await mostrar_menu(u,c)
async def soporte(u,c): await u.message.reply_text(f"📞 Soporte: {SOPORTE_USERNAME}")

async def button(update, context):
    q=update.callback_query; await q.answer(); data=q.data
    if data.startswith("confirmar_"):
        try:
            _, uid_str, pid = data.split("_",2)
            await context.bot.send_message(chat_id=int(uid_str), text=f"✅ Pedido #{pid} - ¡Pago realizado! ✅\nUsa /tienda")
            await q.edit_message_text(f"{q.message.text}\n\n✅ CONFIRMADO #{pid}")
        except: pass
        return
    if data.startswith("aprobar_"):
        try:
            _, uid_str, pid = data.split("_",2); uid = int(uid_str)
            with lock_pendientes: info = PENDIENTES.pop(pid, None)
            if not info: return await q.edit_message_text(f"Ya procesado #{pid}")
            tipo = info["tipo"]; user_data = context.application.user_data.get(uid, {})
            if tipo == "compra_saldo":
                user_data["flow"] = "compra_saldo_captura"; user_data["monto"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\nTransfiere {info['total']:.0f} CUP a:\n{TARJETA}\n{MOVIL}\n\n{ADVERTENCIA}\nManda CAPTURA")
            elif tipo == "venta_saldo":
                user_data["flow"] = "venta_saldo_captura"; user_data["monto"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\nVendes {info['monto']:.0f} saldo\nTransfiere a {MOVIL}\nManda CAPTURA")
            elif tipo == "compra_usdt":
                user_data["flow"] = "compra_usdt_wallet"; user_data["usdt"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\n{info['monto']} USDT = {info['total']:.0f} CUP\nManda tu WALLET BEP20")
            elif tipo == "venta_usdt":
                user_data["flow"] = "venta_usdt_captura"; user_data["usdt"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\nVenderás {info['monto']} USDT\nEnvía a:\n{WALLET_BEP20}\nManda CAPTURA")
            ORDENES_ACTIVAS[pid] = {"uid": uid, "tipo": tipo}
            try: context.job_queue.run_once(cancelar_automatico, 1200, data={"pid": pid, "uid": uid, "tipo": tipo, "monto": info["monto"], "total": info["total"], "usuario": info.get("usuario",""), "username": info.get("username","")}, name=f"cancel_{pid}")
            except: pass
            await q.edit_message_text(f"APROBADO #{pid} (20 min)")
        except Exception as e: print(f"Error aprobar: {e}")
        return
    if data.startswith("rechazar_"):
        try:
            _, uid_str, pid = data.split("_",2); uid = int(uid_str)
            with lock_pendientes: PENDIENTES.pop(pid, None)
            ORDENES_ACTIVAS.pop(pid, None)
            await context.bot.send_message(uid, f"❌ Pedido #{pid} rechazado.\nUsa /tienda")
            await q.edit_message_text(f"RECHAZADO #{pid}")
        except: pass
        return
    if data=="menu": await mostrar_menu(q,context); return
    pid=gen_id(); context.user_data.clear(); context.user_data["pedido_id"]=pid
    if data=="comprar_saldo":
        trans = cargar_transfer()
        if trans["usadas"] >= LIMITE_DIARIO: return await q.edit_message_text(MENSAJE_AGOTADO)
        if stock.get("saldo", 0) <=0: return await q.edit_message_text("Saldo AGOTADO 0 CUP")
        context.user_data["flow"]="compra_saldo"
        await q.edit_message_text(f"Comprar saldo - #{pid}\nDisponible: {stock['saldo']:.0f}\nPrecio: 360 = {precios['saldo_compra']}\nEscribe cuánto:")
    elif data=="vender_saldo":
        context.user_data["flow"]="venta_saldo"
        await q.edit_message_text(f"Vender saldo - #{pid}\nPagamos: 360 = {precios['saldo_venta']}\nEscribe cuánto vendes:")
    elif data=="comprar_crypto":
        if stock.get("usdt", 0) <=0: return await q.edit_message_text("USDT AGOTADO")
        context.user_data["flow"]="compra_usdt_monto"
        await q.edit_message_text(f"Comprar USDT - #{pid}\nDisponibles: {stock['usdt']:.0f}\nPrecio: {precios['usdt_compra']} CUP = 1 USDT\n¿Cuántos?")
    elif data=="vender_crypto":
        context.user_data["flow"]="venta_usdt_monto"
        await q.edit_message_text(f"Vender USDT - #{pid}\nPagamos: {precios['usdt_venta']} CUP = 1 USDT\n¿Cuántos vendes?")

async def recibir_mensaje(update, context):
    if not update.message: return
    usuario=update.effective_user.first_name or "Usuario"; username=f"@{update.effective_user.username}" if update.effective_user.username else ""; uid=update.effective_user.id
    flow=context.user_data.get("flow"); pid=context.user_data.get("pedido_id", gen_id()); txt=update.message.text or ""
    if txt.startswith("/"): return
    if not flow: return await update.message.reply_text("Usa /tienda")
    def header(t): return f"🆕 #{pid} - {t}\n👤 {usuario} {username}\n🆔 {uid}"
    def btn_confirmar(): return InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Confirmar Pago #{pid}", callback_data=f"confirmar_{uid}_{pid}")]])
    def btn_aprobacion(): return InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ APROBAR #{pid}", callback_data=f"aprobar_{uid}_{pid}"), InlineKeyboardButton(f"❌ RECHAZAR", callback_data=f"rechazar_{uid}_{pid}")]])
    if flow=="compra_saldo":
        try:
            monto=float(txt.replace(",",".")); total=(monto/360)*precios['saldo_compra']
            if monto > stock.get("saldo", 0) and stock.get("saldo", 0) > 0: return await update.message.reply_text(f"Solo {stock['saldo']:.0f} disponible")
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "compra_saldo", "monto": monto, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid} Enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 #{pid} {header('COMPRA SALDO')}\nSaldo: {monto:.0f}\nTotal: {total:.0f}", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número")
    elif flow=="compra_saldo_captura":
        if update.message.photo:
            if ADMIN_CHANNEL_ID:
                try: await update.message.forward(ADMIN_CHANNEL_ID)
                except: pass
            context.user_data["flow"]="compra_saldo_telefono"; await update.message.reply_text("📸 Recibida\nEscribe tu NÚMERO")
        else: await update.message.reply_text("Manda foto")
    elif flow=="compra_saldo_telefono":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            stock["saldo"] = max(0, stock["saldo"] - context.user_data.get('monto',0)); guardar_stock(stock)
            tdata = cargar_transfer(); tdata["usadas"]+=1; guardar_transfer(tdata)
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"📲 FINAL #{pid}\n{usuario}\nNum: {txt}", reply_markup=btn_confirmar())
        except: pass
        context.user_data.clear()
    #... resto de flows igual...
    elif flow=="venta_saldo":
        try:
            monto=float(txt.replace(",",".")); total=(monto/360)*precios['saldo_venta']
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "venta_saldo", "monto": monto, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid} Enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 #{pid} {header('VENTA SALDO')}\nSaldo: {monto:.0f}", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número")
    elif flow=="venta_saldo_captura":
        if update.message.photo:
            if ADMIN_CHANNEL_ID:
                try: await update.message.forward(ADMIN_CHANNEL_ID)
                except: pass
            context.user_data["flow"]="venta_saldo_datos"; await update.message.reply_text("📸 Recibida\nManda TARJETA y NUMERO")
        else: await update.message.reply_text("Manda foto")
    elif flow=="venta_saldo_datos":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            stock["saldo"]+=context.user_data.get('monto',0); guardar_stock(stock)
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"💵 FINAL #{pid}\n{usuario}\nDatos: {txt}", reply_markup=btn_confirmar())
        except: pass
        context.user_data.clear()
    elif flow=="compra_usdt_monto":
        try:
            cant=float(txt.replace(",",".")); total=cant*precios['usdt_compra']
            if cant > stock.get("usdt", 0) and stock.get("usdt", 0) > 0: return await update.message.reply_text(f"Solo {stock['usdt']:.0f} disponible")
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "compra_usdt", "monto": cant, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid} Enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 #{pid} COMPRA USDT {cant}", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número")
    elif flow=="compra_usdt_wallet":
        context.user_data["wallet_cliente"]=txt; context.user_data["flow"]="compra_usdt_captura"
        await update.message.reply_text(f"Wallet guardada\nTransfiere {context.user_data['total_cup']:.0f} CUP a {TARJETA}\nManda CAPTURA")
    elif flow=="compra_usdt_captura":
        if update.message.photo:
            if ADMIN_CHANNEL_ID:
                try: await update.message.forward(ADMIN_CHANNEL_ID)
                except: pass
            context.user_data["flow"]="compra_usdt_final"; await update.message.reply_text("📸 Recibida\nEscribe tu NÚMERO")
        else: await update.message.reply_text("Manda foto")
    elif flow=="compra_usdt_final":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            stock["usdt"]=max(0, stock["usdt"]-context.user_data.get('usdt',0)); guardar_stock(stock)
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"FINAL USDT #{pid}\n{usuario}\nContacto: {txt}", reply_markup=btn_confirmar())
        except: pass
        context.user_data.clear()
    elif flow=="venta_usdt_monto":
        try:
            cant=float(txt.replace(",",".")); total=cant*precios['usdt_venta']
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "venta_usdt", "monto": cant, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid} Enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 #{pid} VENTA USDT {cant}", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número")
    elif flow=="venta_usdt_captura":
        if update.message.photo:
            if ADMIN_CHANNEL_ID:
                try: await update.message.forward(ADMIN_CHANNEL_ID)
                except: pass
            context.user_data["flow"]="venta_usdt_datos"; await update.message.reply_text("📸 Recibida\nManda TARJETA y NUMERO")
        else: await update.message.reply_text("Manda foto")
    elif flow=="venta_usdt_datos":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            stock["usdt"]+=context.user_data.get('usdt',0); guardar_stock(stock)
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"FINAL VENTA USDT #{pid}\n{usuario}\nDatos: {txt}", reply_markup=btn_confirmar())
        except: pass
        context.user_data.clear()

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

def main():
    Thread(target=run_flask, daemon=True).start()
    if not TOKEN:
        print("❌ TOKEN vacio - bot no iniciará polling")
        return
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("tienda", tienda))
    app.add_handler(CommandHandler("soporte", soporte))
    app.add_handler(CommandHandler("saldo", cambiar_saldo))
    app.add_handler(CommandHandler("venta", cambiar_venta))
    app.add_handler(CommandHandler("usdtc", cambiar_usdtc))
    app.add_handler(CommandHandler("usdtv", cambiar_usdtv))
    app.add_handler(CommandHandler("precios", ver_precios))
    app.add_handler(CommandHandler("gaste1", cmd_gaste1))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("cerrar", cmd_cerrar))
    app.add_handler(CommandHandler("abrir", cmd_abrir))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, recibir_mensaje))
    print("🤖 Bot FINAL LIMPIO con STOCK AUTOMATICO + TIMER 20 MIN")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
