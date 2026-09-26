import os, json, random, datetime
from flask import Flask
from threading import Thread, Lock
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
# ========== CONFIG LIMPIA PARA VENDER - DEJAR EN BLANCO ==========
TOKEN = os.environ.get("TOKEN") # El cliente pondrá su token en Render
ADMIN_CHANNEL_ID = "" # ID del grupo admin - DEJAR VACIO
CANAL_PAGOS_ID = "" # ID del canal de pagos - DEJAR VACIO
ADMIN_USER_ID = 0 # ID del admin - DEJAR EN 0
TARJETA = "" # Ej: 9238-xxxx-xxxx-xxxx - DEJAR VACIO
MOVIL = "" # Ej: 55xxxxxx - DEJAR VACIO
WALLET_BEP20 = "" # Wallet USDT BEP20 - DEJAR VACIO
SOPORTE_USERNAME = "" # Ej: @Soporte - DEJAR VACIO
# ============================================================
MENSAJE_FINAL = "✅ Pedido registrado. Le pagaremos en breve. Gracias por preferirnos 🙏\n\nUsa /tienda para nuevo pedido"
ADVERTENCIA = "⚠️ ATENCIÓN:\nLa captura debe verse con TOTAL CLARIDAD (monto, fecha, referencia).\n\n🚫 Cualquier intento de engaño, captura falsa, editada o estafa = BANEO PERMANENTE y serás reportado en todos los grupos y canales."
MENSAJE_AGOTADO = "⚠️ Saldo ETECSA agotado por hoy límite 3\nPor favor vuelve mañana para realizar tu pedido. Te esperamos 🙏"
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot activo"
PRECIOS_FILE = "precios.json"
lock_precios = Lock()
def cargar_precios():
    if os.path.exists(PRECIOS_FILE):
        try:
            with open(PRECIOS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"saldo_compra": 0, "saldo_venta": 0, "usdt_compra": 0, "usdt_venta": 0}
def guardar_precios(d):
    with lock_precios:
        with open(PRECIOS_FILE, "w", encoding="utf-8") as f: json.dump(d, f)
precios = cargar_precios()
STOCK_FILE = "stock.json"
lock_stock = Lock()
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
        with open(STOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
stock = cargar_stock()
TIENDA_FILE = "tienda.json"
lock_tienda = Lock()
def cargar_tienda():
    if os.path.exists(TIENDA_FILE):
        try:
            with open(TIENDA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("cerrada", False)
        except: pass
    return False
def guardar_tienda(cerrada):
    with lock_tienda:
        with open(TIENDA_FILE, "w", encoding="utf-8") as f:
            json.dump({"cerrada": cerrada}, f)
tiendaCerrada = cargar_tienda()
MENSAJE_CERRADO = """🌙 ¡CubanStore está CERRADO ahora mismo! 🔒

🕒 Horario de trabajo:
De 8:00 AM a 10:30 PM
Hora de Cuba 🇨🇺"""
async def cmd_cerrar(u,c):
    global tiendaCerrada
    if u.effective_user.id!= ADMIN_USER_ID: return
    tiendaCerrada = True
    guardar_tienda(True)
    await u.message.reply_text("🔒 CubanStore CERRADA correctamente")
async def cmd_abrir(u,c):
    global tiendaCerrada
    if u.effective_user.id!= ADMIN_USER_ID: return
    tiendaCerrada = False
    guardar_tienda(False)
    await u.message.reply_text("🔓 CubanStore ABIERTA correctamente")
def gen_id(): return f"{random.randint(1000, 9999)}"
TRANSFER_FILE = "transferencias.json"
LIMITE_DIARIO = 3
lock_transfer = Lock()
def cargar_transfer():
    if not os.path.exists(TRANSFER_FILE):
        return {"usadas": 0, "fecha": str(datetime.date.today())}
    try:
        with open(TRANSFER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("fecha")!= str(datetime.date.today()):
            return {"usadas": 0, "fecha": str(datetime.date.today())}
        return data
    except:
        return {"usadas": 0, "fecha": str(datetime.date.today())}
def guardar_transfer(data):
    with lock_transfer:
        with open(TRANSFER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
PENDIENTES = {}
PAGOS_INFO = {}
ORDENES_ACTIVAS = {}
lock_pendientes = Lock()

async def cancelar_automatico(context):
    data = context.job.data
    pid = data["pid"]
    uid = data["uid"]
    tipo = data.get("tipo", "compra_saldo")
    monto = data.get("monto", 0)
    total = data.get("total", 0)
    usuario = data.get("usuario", "Usuario")
    username = data.get("username", "")
    if pid not in ORDENES_ACTIVAS: return
    ORDENES_ACTIVAS.pop(pid, None)
    with lock_pendientes:
        PENDIENTES.pop(pid, None)
    if uid in context.application.user_data:
        try: context.application.user_data[uid].clear()
        except: pass
    if "compra" in tipo:
        titulo_user = "❌ COMPRA CANCELADA"
        motivo_user = "Tiempo de compra expirado\n(20 min sin completar el pago)"
        extra_user = "Puede volver a realizar una nueva\ncompra cuando quiera."
        tipo_admin = "Compra de saldo" if "saldo" in tipo else "Compra de USDT"
    else:
        titulo_user = "❌ VENTA CANCELADA"
        motivo_user = "Tiempo de venta expirado\n(20 min sin entregar)"
        extra_user = "Puede volver a realizar una nueva\nventa cuando quiera."
        tipo_admin = "Venta de saldo" if "saldo" in tipo else "Venta de USDT"
    texto_usuario = f"""{titulo_user}\n\n┌─────────────────────────┐\n│ Orden #{pid}\n│ Estado: CANCELADA ❌\n│\n│ Motivo: {motivo_user}\n│\n│ {extra_user}\n└─────────────────────────┘\n\nUsa /tienda para una nueva orden.\nCuban.Store 💙"""
    texto_admin = f"""⚠️ {titulo_user} AUTOMÁTICAMENTE\n\n📋 Orden #{pid}\n👤 Usuario: {usuario} {username}\n🆔 ID: {uid}\n\n📦 Detalles:\nTipo: {tipo_admin}\nCantidad: {monto}\nTotal: {total:.0f} CUP\n\n⏰ Motivo: 20 min sin completar\n📅 {datetime.datetime.now().strftime('%d/%m/%Y - %I:%M %p')}"""
    try:
        await context.bot.send_message(uid, texto_usuario)
        if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, texto_admin)
    except Exception as e: print(f"Error auto-cancel: {e}")

async def cmd_stock(u,c):
    if u.effective_user.id!= ADMIN_USER_ID:
        await u.message.reply_text("❌ No tienes permiso, solo el admin puede cambiar el stock."); return
    if not c.args:
        await u.message.reply_text(f"📦 STOCK ACTUAL:\n💰 Saldo: {stock['saldo']:.0f}\n💵 USDT: {stock['usdt']:.0f}\n\nUso:\n/stock saldo 100 -> poner 100 de saldo\n/stock saldo 0 -> agotado\n/stock usdt 50 -> poner 50 USDT\n/stock usdt 0 -> agotado\n/stock ver -> ver stock"); return
    if c.args[0].lower() == "ver":
        await u.message.reply_text(f"📦 STOCK ACTUAL:\n💰 Saldo disponible: {stock['saldo']:.0f} CUP\n💵 USDT disponible: {stock['usdt']:.0f} USDT"); return
    if len(c.args) < 2:
        await u.message.reply_text("Uso: /stock saldo 100 o /stock usdt 50"); return
    tipo = c.args[0].lower()
    try: cantidad = float(c.args[1].replace(",", "."))
    except:
        await u.message.reply_text("Cantidad no válida. Ej: /stock saldo 100"); return
    if tipo in ["saldo", "cup"]:
        stock["saldo"] = cantidad; guardar_stock(stock)
        estado = "❌ AGOTADO" if cantidad <=0 else f"✅ {cantidad:.0f}"
        await u.message.reply_text(f"✅ Stock de SALDO actualizado: {estado}")
    elif tipo in ["usdt", "crypto"]:
        stock["usdt"] = cantidad; guardar_stock(stock)
        estado = "❌ AGOTADO" if cantidad <=0 else f"✅ {cantidad:.0f}"
        await u.message.reply_text(f"✅ Stock de USDT actualizado: {estado}")
    else: await u.message.reply_text("Tipo no válido. Usa: saldo o usdt\nEj: /stock saldo 100")

async def cambiar_saldo(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['saldo_compra']}\nUso: /saldo 950")
    precios["saldo_compra"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ Compra -> {precios['saldo_compra']}")
async def cambiar_venta(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['saldo_venta']}\nUso: /venta 780")
    precios["saldo_venta"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ Venta -> {precios['saldo_venta']}")
async def cambiar_usdtc(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['usdt_compra']}\nUso: /usdtc 360")
    precios["usdt_compra"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ USDT Compra -> {precios['usdt_compra']}")
async def cambiar_usdtv(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    if not c.args: return await u.message.reply_text(f"Actual: {precios['usdt_venta']}\nUso: /usdtv 350")
    precios["usdt_venta"]=int(c.args[0]); guardar_precios(precios); await u.message.reply_text(f"✅ USDT Venta -> {precios['usdt_venta']}")
async def ver_precios(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    await u.message.reply_text(f"PRECIOS:\nCompra saldo: {precios['saldo_compra']}\nVenta saldo: {precios['saldo_venta']}\nUSDT Compra: {precios['usdt_compra']}\nUSDT Venta: {precios['usdt_venta']}\n\nSTOCK:\nSaldo: {stock['saldo']:.0f}\nUSDT: {stock['usdt']:.0f}")
async def cmd_gaste1(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    data = cargar_transfer(); data["usadas"] = min(data["usadas"] + 1, LIMITE_DIARIO); data["fecha"] = str(datetime.date.today()); guardar_transfer(data)
    await u.message.reply_text(f"✅ Anotado. Hoy: {data['usadas']}/{LIMITE_DIARIO} usadas. Te quedan {LIMITE_DIARIO - data['usadas']}")
async def cmd_reset(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    data = {"usadas": 0, "fecha": str(datetime.date.today())}; guardar_transfer(data); await u.message.reply_text(f"♻️ Contador reseteado a 0/{LIMITE_DIARIO}. Saldo desbloqueado.")
async def cmd_estado(u,c):
    if u.effective_user.id!= ADMIN_USER_ID: return
    data = cargar_transfer(); await u.message.reply_text(f"📊 ESTADO HOY {data['fecha']}:\nUsadas: {data['usadas']}/{LIMITE_DIARIO}\nQuedan: {LIMITE_DIARIO - data['usadas']}\n\n🏪 Tienda: {'🔒 CERRADA' if tiendaCerrada else '🔓 ABIERTA'}\n📦 Stock Saldo: {stock['saldo']:.0f}\n📦 Stock USDT: {stock['usdt']:.0f}")
async def mostrar_menu(u,c):
    if tiendaCerrada:
        if isinstance(u,Update): await u.message.reply_text(MENSAJE_CERRADO)
        else: await u.edit_message_text(MENSAJE_CERRADO)
        return
    kb=[[InlineKeyboardButton("📲💳 Comprar saldo",callback_data="comprar_saldo")],[InlineKeyboardButton("💵📱 Vender saldo",callback_data="vender_saldo")],[InlineKeyboardButton("🚀🪙 Comprar USDT",callback_data="comprar_crypto")],[InlineKeyboardButton("💸🔗 Vender USDT",callback_data="vender_crypto")]]
    if isinstance(u,Update): await u.message.reply_text("🛍️ Elige:",reply_markup=InlineKeyboardMarkup(kb))
    else: await u.edit_message_text("🛍️ Elige:",reply_markup=InlineKeyboardMarkup(kb))
async def tienda(u,c): await mostrar_menu(u,c)
async def soporte(u,c):
    await u.message.reply_text(f"📞 SOPORTE OFICIAL\n\n👤 Dueño: {SOPORTE_USERNAME}\n\nSi tienes dudas escríbeme directo al privado 🙏", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Hablar con Soporte", url=f"https://t.me/{SOPORTE_USERNAME.replace('@','')}")]]))
async def button(update, context):
    q=update.callback_query; await q.answer()
    data=q.data
    if data.startswith("confirmar_"):
        try:
            _, uid_str, pid = data.split("_",2)
            await context.bot.send_message(chat_id=int(uid_str), text=f"✅ Pedido #{pid} - ¡Pago realizado! ✅\n\nGracias por preferirnos 🙏\nUsa /tienda para nuevo pedido")
            await q.edit_message_text(f"{q.message.text}\n\n✅ CONFIRMADO Y PAGADO - #{pid}")
            try:
                info = PAGOS_INFO.get(pid, {}); operacion = info.get("operacion", "intercambio"); monto = info.get("monto", "0.00 CUP"); usuario_txt = info.get("usuario", "Usuario")
                texto_canal = f"📢 Solicitud completada\n\n🧾 No. pedido: {pid}\n💱 Operación: {operacion}\n💰 Monto pagado: {monto}\n👤 Usuario: {usuario_txt}\n\n📊 Estado:\n--- ✅ Pagado ---"
                if CANAL_PAGOS_ID: await context.bot.send_message(chat_id=CANAL_PAGOS_ID, text=texto_canal)
                PAGOS_INFO.pop(pid, None)
            except Exception as e2: print(f"Error canal pagos: {e2}")
        except Exception as e: print(e)
        return
    if data.startswith("aprobar_"):
        try:
            _, uid_str, pid = data.split("_",2); uid = int(uid_str)
            with lock_pendientes: info = PENDIENTES.pop(pid, None)
            if not info: await q.edit_message_text(f"{q.message.text}\n\n⚠️ Ya fue procesado #{pid}"); return
            tipo = info["tipo"]; user_data = context.application.user_data.get(uid, {})
            if tipo == "compra_saldo":
                user_data["flow"] = "compra_saldo_captura"; user_data["monto"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\n\nQuieres {info['monto']:.0f} saldo = {info['total']:.0f} CUP\n\n💳 Transfiere {info['total']:.0f} CUP a:\nTarjeta: <code>{TARJETA}</code>\nMóvil: <code>{MOVIL}</code>\n\nToca el número para copiar 👆\n\n{ADVERTENCIA}\n\nAhora manda la CAPTURA 📸", parse_mode="HTML")
            elif tipo == "venta_saldo":
                user_data["flow"] = "venta_saldo_captura"; user_data["monto"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\n\nVendes {info['monto']:.0f} saldo\nRecibes: {info['total']:.0f} CUP\n\nTransfiere saldo a <code>{MOVIL}</code> 👆 toca para copiar\n\n{ADVERTENCIA}\n\nManda CAPTURA 📸", parse_mode="HTML")
            elif tipo == "compra_usdt":
                user_data["flow"] = "compra_usdt_wallet"; user_data["usdt"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\n\n{info['monto']} USDT = {info['total']:.0f} CUP\n\n🌐 Red: BEP20 (BSC)\nManda tu WALLET BEP20")
            elif tipo == "venta_usdt":
                user_data["flow"] = "venta_usdt_captura"; user_data["usdt"] = info["monto"]; user_data["total_cup"] = info["total"]; user_data["pedido_id"] = pid
                await context.bot.send_message(uid, f"✅ #{pid} APROBADO\n\nVenderás {info['monto']} USDT\nRecibirás: {info['total']:.0f} CUP\n\n🌐 Red: BEP20 (BSC) - OBLIGATORIO\nEnvía los {info['monto']} USDT a:\n<code>{WALLET_BEP20}</code>\n\n⚠️ Solo BEP20, si envías por otra red se pierde el dinero\n\n{ADVERTENCIA}\n\nLuego manda CAPTURA 📸", parse_mode="HTML")
            ORDENES_ACTIVAS[pid] = {"uid": uid, "tipo": tipo}
            try: context.job_queue.run_once(cancelar_automatico, 1200, data={"pid": pid, "uid": uid, "tipo": tipo, "monto": info["monto"], "total": info["total"], "usuario": info.get("usuario","Usuario"), "username": info.get("username","")}, name=f"cancel_{pid}")
            except Exception as e: print(f"Error job_queue: {e}")
            await q.edit_message_text(f"{q.message.text}\n\n✅ APROBADO POR TI - #{pid} (Expira en 20 min)")
        except Exception as e: print(f"Error aprobar: {e}")
        return
    if data.startswith("rechazar_"):
        try:
            _, uid_str, pid = data.split("_",2); uid = int(uid_str)
            with lock_pendientes: PENDIENTES.pop(pid, None)
            ORDENES_ACTIVAS.pop(pid, None)
            if uid in context.application.user_data: context.application.user_data[uid].clear()
            await context.bot.send_message(uid, f"❌ Pedido #{pid} rechazado.\n\nNo se pudo realizar la operación en este momento, intenta más tarde.\nUsa /tienda")
            await q.edit_message_text(f"{q.message.text}\n\n❌ RECHAZADO POR TI - #{pid}")
        except Exception as e: print(f"Error rechazar: {e}")
        return
    if data=="menu": await mostrar_menu(q,context); return
    if tiendaCerrada and data in ["comprar_saldo", "vender_saldo", "comprar_crypto", "vender_crypto"]:
        await q.edit_message_text(MENSAJE_CERRADO, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver",callback_data="menu")]])); return
    pid=gen_id(); context.user_data.clear(); context.user_data["pedido_id"]=pid
    if data=="comprar_saldo":
        trans = cargar_transfer()
        if trans["usadas"] >= LIMITE_DIARIO:
            await q.edit_message_text(MENSAJE_AGOTADO, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver",callback_data="menu")]])); return
        disponible = stock.get("saldo", 0)
        if disponible <= 0:
            await q.edit_message_text(f"💰 Saldo disponible: 0 CUP ❌ AGOTADO\n\nPor ahora no tenemos saldo, vuelve más tarde 🙏", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver",callback_data="menu")]])); return
        context.user_data["flow"]="compra_saldo"
        await q.edit_message_text(f"📲💳 Comprar saldo - #{pid}\n\n💰 Saldo disponible en la tienda: {disponible:.0f} CUP\n💵 Precio: 360 = {precios['saldo_compra']} CUP\n\n✍️ Escribe cuánto quieres comprar:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Atrás",callback_data="menu")]]))
    elif data=="vender_saldo":
        context.user_data["flow"]="venta_saldo"
        await q.edit_message_text(f"💵📱 Vender saldo - #{pid}\n\nPagamos: 360 = {precios['saldo_venta']} CUP\n\nEscribe cuánto vendes:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Atrás",callback_data="menu")]]))
    elif data=="comprar_crypto":
        disponible = stock.get("usdt", 0)
        if disponible <= 0:
            await q.edit_message_text(f"💵 USDT disponible: 0 USDT ❌ AGOTADO\n\nPor ahora no tenemos USDT, vuelve más tarde 🙏", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver",callback_data="menu")]])); return
        context.user_data["flow"]="compra_usdt_monto"
        await q.edit_message_text(f"🚀🪙 Comprar USDT - #{pid}\n\n💵 USDT disponibles en la tienda: {disponible:.0f} USDT\n💰 Precio: {precios['usdt_compra']} CUP = 1 USDT\n🌐 Red: BEP20 (BSC)\n\n⚠️ SOLO trabajamos USDT por BEP20\n\n¿Cuántos USDT quieres?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Atrás",callback_data="menu")]]))
    elif data=="vender_crypto":
        context.user_data["flow"]="venta_usdt_monto"
        await q.edit_message_text(f"💸🔗 Vender USDT - #{pid}\n\n💰 Pagamos: {precios['usdt_venta']} CUP = 1 USDT\n🌐 Red: BEP20 (BNB Smart Chain)\n\n⚠️ Envía SOLO por BEP20\n\n¿Cuántos USDT vendes?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Atrás",callback_data="menu")]]))

async def recibir_mensaje(update, context):
    if not update.message: return
    usuario=update.effective_user.first_name or "Usuario"; username=f"@{update.effective_user.username}" if update.effective_user.username else ""; uid=update.effective_user.id
    flow=context.user_data.get("flow"); pid=context.user_data.get("pedido_id", gen_id()); txt=update.message.text or ""
    if txt.startswith("/"): return
    if not flow: return await update.message.reply_text("Usa /tienda")
    if update.message.photo:
        ORDENES_ACTIVAS.pop(pid, None)
        try:
            jobs = context.job_queue.get_jobs_by_name(f"cancel_{pid}")
            for j in jobs: j.schedule_removal()
        except: pass
    def header(t): return f"🆕 #{pid} - {t}\n👤 {usuario} {username}\n🆔 {uid}"
    def btn_confirmar(): return InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Confirmar Pago #{pid}", callback_data=f"confirmar_{uid}_{pid}")]])
    def btn_aprobacion(): return InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ APROBAR #{pid}", callback_data=f"aprobar_{uid}_{pid}"), InlineKeyboardButton(f"❌ RECHAZAR", callback_data=f"rechazar_{uid}_{pid}")]])
    if flow=="compra_saldo":
        try:
            monto=float(txt.replace(",","."))
            if monto > stock.get("saldo", 0) and stock.get("saldo", 0) > 0:
                await update.message.reply_text(f"❌ Solo tenemos {stock['saldo']:.0f} CUP disponible. Escribe una cantidad menor."); return
            total=(monto/360)*precios['saldo_compra']
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "compra_saldo", "monto": monto, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid}\nSolicitud de {monto:.0f} saldo = {total:.0f} CUP enviada a revisión.\nTe avisamos cuando sea aprobada.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 SOLICITUD PENDIENTE #{pid}\n{header('COMPRA SALDO')}\nSaldo: {monto:.0f}\nTotal: {total:.0f} CUP\nStock restante: {stock['saldo']:.0f}\n\n¿Aprobar?", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número. Ej: 360")
    elif flow=="compra_saldo_captura":
        if update.message.photo:
            try:
                if ADMIN_CHANNEL_ID: await update.message.forward(ADMIN_CHANNEL_ID)
            except: pass
            context.user_data["flow"]="compra_saldo_telefono"; await update.message.reply_text("📸 Captura recibida ✅\n\nEscribe tu NÚMERO donde te enviamos el saldo")
        else: await update.message.reply_text(f"Manda foto con claridad 📸\n\n{ADVERTENCIA}")
    elif flow=="compra_saldo_telefono":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            monto = context.user_data.get('monto',0); total = context.user_data.get('total_cup',0)
            PAGOS_INFO[pid] = {"operacion": "compra de saldo", "monto": f"{monto:.0f} de saldo", "usuario": f"{usuario} {username}"}
            stock["saldo"] = max(0, stock["saldo"] - monto); guardar_stock(stock)
            tdata = cargar_transfer(); tdata["usadas"] = min(tdata["usadas"] + 1, LIMITE_DIARIO); tdata["fecha"] = str(datetime.date.today()); guardar_transfer(tdata)
            if ADMIN_CHANNEL_ID:
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"📲 RESUMEN FINAL #{pid}\n{usuario}\nSaldo: {monto:.0f} = {total:.0f} CUP\n📦 Stock restante: {stock['saldo']:.0f}", reply_markup=btn_confirmar())
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"📱 NUMERO COPIABLE #{pid}:\n<code>{txt}</code>", parse_mode="HTML")
        except: pass
        context.user_data.clear()
    elif flow=="venta_saldo":
        try:
            monto=float(txt.replace(",",".")); total=(monto/360)*precios['saldo_venta']
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "venta_saldo", "monto": monto, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid}\nSolicitud de vender {monto:.0f} saldo = {total:.0f} CUP enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 SOLICITUD PENDIENTE #{pid}\n{header('VENTA SALDO')}\nSaldo: {monto:.0f}\nA pagar: {total:.0f} CUP\n\n¿Aprobar?", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número. Ej: 360")
    elif flow=="venta_saldo_captura":
        if update.message.photo:
            try:
                if ADMIN_CHANNEL_ID: await update.message.forward(ADMIN_CHANNEL_ID)
            except: pass
            context.user_data["flow"]="venta_saldo_datos"; await update.message.reply_text(f"📸 Captura recibida ✅\n\nManda tu TARJETA CUP y tu NÚMERO a confirmar para pagarte los {context.user_data.get('total_cup',0):.0f} CUP")
        else: await update.message.reply_text(f"Manda foto con claridad 📸\n\n{ADVERTENCIA}")
    elif flow=="venta_saldo_datos":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            monto = context.user_data.get('monto',0); total = context.user_data.get('total_cup',0)
            PAGOS_INFO[pid] = {"operacion": "venta de saldo", "monto": f"{total:.2f} CUP", "usuario": f"{usuario} {username}"}
            stock["saldo"] = stock["saldo"] + monto; guardar_stock(stock)
            if ADMIN_CHANNEL_ID:
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"💵 RESUMEN FINAL #{pid}\n{usuario}\nVende: {monto:.0f}\nA pagar: {total:.0f} CUP\n📦 Stock nuevo: {stock['saldo']:.0f}", reply_markup=btn_confirmar())
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"💳 TARJETA Y NUMERO COPIABLE #{pid}:\n<code>{txt}</code>", parse_mode="HTML")
        except: pass
        context.user_data.clear()
    elif flow=="compra_usdt_monto":
        try:
            cant=float(txt.replace(",","."))
            if cant > stock.get("usdt", 0) and stock.get("usdt", 0) > 0:
                await update.message.reply_text(f"❌ Solo tenemos {stock['usdt']:.0f} USDT disponible. Escribe una cantidad menor."); return
            total=cant*precios['usdt_compra']
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "compra_usdt", "monto": cant, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid}\nSolicitud de {cant} USDT = {total:.0f} CUP enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 SOLICITUD PENDIENTE #{pid}\n{header('COMPRA USDT BEP20')}\nCantidad: {cant} USDT = {total:.0f} CUP\nRed: BEP20\nStock restante: {stock['usdt']:.0f}\n\n¿Aprobar?", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número. Ej: 10")
    elif flow=="compra_usdt_wallet":
        context.user_data["wallet_cliente"]=txt; context.user_data["flow"]="compra_usdt_captura"
        await update.message.reply_text(f"✅ Wallet BEP20 guardada\n\n💳 Transfiere {context.user_data['total_cup']:.0f} CUP a:\nTarjeta: <code>{TARJETA}</code>\nMóvil: <code>{MOVIL}</code>\n\nToca para copiar 👆\n\n{ADVERTENCIA}\n\nManda CAPTURA 📸", parse_mode="HTML")
        try:
            if ADMIN_CHANNEL_ID:
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"{header('COMPRA USDT BEP20')}\nCantidad: {context.user_data['usdt']} USDT = {context.user_data['total_cup']:.0f} CUP")
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"👛 WALLET BEP20 COPIABLE #{pid}:\n<code>{txt}</code>", parse_mode="HTML")
        except: pass
    elif flow=="compra_usdt_captura":
        if update.message.photo:
            try:
                if ADMIN_CHANNEL_ID: await update.message.forward(ADMIN_CHANNEL_ID)
            except: pass
            context.user_data["flow"]="compra_usdt_final"; await update.message.reply_text("📸 Captura ✅\n\nEscribe tu NÚMERO de contacto")
        else: await update.message.reply_text(f"Manda captura con claridad 📸\n\n{ADVERTENCIA}")
    elif flow=="compra_usdt_final":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            usdt = context.user_data.get('usdt',0); total = context.user_data.get('total_cup',0)
            PAGOS_INFO[pid] = {"operacion": "compra de USDT", "monto": f"{usdt} USDT", "usuario": f"{usuario} {username}"}
            stock["usdt"] = max(0, stock["usdt"] - usdt); guardar_stock(stock)
            if ADMIN_CHANNEL_ID:
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"📲 RESUMEN FINAL #{pid}\n{usuario}\nUSDT BEP20: {usdt}\nTotal: {total:.0f} CUP\n📦 Stock USDT restante: {stock['usdt']:.0f}\nContacto: {txt}", reply_markup=btn_confirmar())
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"👛 WALLET + CONTACTO COPIABLE #{pid}:\nWallet: <code>{context.user_data['wallet_cliente']}</code>\nNumero: <code>{txt}</code>", parse_mode="HTML")
        except: pass
        context.user_data.clear()
    elif flow=="venta_usdt_monto":
        try:
            cant=float(txt.replace(",",".")); total=cant*precios['usdt_venta']
            with lock_pendientes: PENDIENTES[pid] = {"uid": uid, "tipo": "venta_usdt", "monto": cant, "total": total, "usuario": usuario, "username": username}
            await update.message.reply_text(f"⏳ #{pid}\nSolicitud de vender {cant} USDT (BEP20) = {total:.0f} CUP enviada a revisión.")
            if ADMIN_CHANNEL_ID: await context.bot.send_message(ADMIN_CHANNEL_ID, f"🔔 SOLICITUD PENDIENTE #{pid}\n{header('VENTA USDT BEP20')}\nCantidad: {cant} USDT = {total:.0f} CUP\nRed: BEP20\n\n¿Aprobar?", reply_markup=btn_aprobacion())
        except: await update.message.reply_text("Solo número. Ej: 20")
    elif flow=="venta_usdt_captura":
        if update.message.photo:
            try:
                if ADMIN_CHANNEL_ID: await update.message.forward(ADMIN_CHANNEL_ID)
            except: pass
            context.user_data["flow"]="venta_usdt_datos"; await update.message.reply_text(f"📸 Captura recibida ✅\n\nManda tu TARJETA CUP y tu NÚMERO a confirmar para pagarte los {context.user_data.get('total_cup',0):.0f} CUP")
        else: await update.message.reply_text(f"Manda captura con claridad 📸\n\n{ADVERTENCIA}")
    elif flow=="venta_usdt_datos":
        await update.message.reply_text(MENSAJE_FINAL)
        try:
            total = context.user_data.get('total_cup',0); usdt = context.user_data.get('usdt',0)
            PAGOS_INFO[pid] = {"operacion": "venta de USDT", "monto": f"{total:.2f} CUP", "usuario": f"{usuario} {username}"}
            stock["usdt"] = stock["usdt"] + usdt; guardar_stock(stock)
            if ADMIN_CHANNEL_ID:
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"💵 RESUMEN FINAL #{pid}\n{usuario}\nVende: {usdt} USDT BEP20\nRecibe: {total:.0f} CUP\n📦 Stock USDT nuevo: {stock['usdt']:.0f}", reply_markup=btn_confirmar())
                await context.bot.send_message(ADMIN_CHANNEL_ID, f"💳 DATOS COPIABLES #{pid}:\n<code>{txt}</code>", parse_mode="HTML")
        except: pass
        context.user_data.clear()

def run_flask(): app_web.run(host='0.0.0.0',port=int(os.environ.get("PORT",10000)))
def main():
    Thread(target=run_flask,daemon=True).start()
    app=Application.builder().token(TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).build()
    app.add_handler(CommandHandler("tienda",tienda))
    app.add_handler(CommandHandler("soporte",soporte))
    app.add_handler(CommandHandler("saldo",cambiar_saldo))
    app.add_handler(CommandHandler("venta",cambiar_venta))
    app.add_handler(CommandHandler("usdtc",cambiar_usdtc))
    app.add_handler(CommandHandler("usdtv",cambiar_usdtv))
    app.add_handler(CommandHandler("precios",ver_precios))
    app.add_handler(CommandHandler("gaste1",cmd_gaste1))
    app.add_handler(CommandHandler("reset",cmd_reset))
    app.add_handler(CommandHandler("estado",cmd_estado))
    app.add_handler(CommandHandler("cerrar",cmd_cerrar))
    app.add_handler(CommandHandler("abrir",cmd_abrir))
    app.add_handler(CommandHandler("stock",cmd_stock))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, recibir_mensaje))
    print("🤖 Bot FINAL LIMPIO con STOCK AUTOMATICO + TIMER 20 MIN"); app.run_polling()
if __name__=="__main__": main()
