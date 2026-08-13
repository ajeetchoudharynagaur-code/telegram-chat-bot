import telebot
import json
import os
import logging
import threading
import time
from threading import Lock
from flask import Flask

# ================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 8940270305
DATA_FILE = "bot_data.json"
DELETE_INTERVAL = 20

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

bot = telebot.TeleBot(TOKEN)
db_lock = Lock()

# ================= FLASK / RENDER =================

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram Bot is Alive ✅", 200


@app.route("/health")
def health():
    return "OK", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


# ================= LOGGING =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ================= DATABASE =================

def empty_db():
    return {
        "history": {},
        "reply_map": {},
        "blocked": [],
        "autodelete": {}
    }


def load_data():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return empty_db()

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            data.setdefault("history", {})
            data.setdefault("reply_map", {})
            data.setdefault("blocked", [])
            data.setdefault("autodelete", {})

            for uid in data["history"]:
                data["history"][uid].setdefault("name", "Unknown")
                data["history"][uid].setdefault("username", "N/A")
                data["history"][uid].setdefault("u", [])
                data["history"][uid].setdefault("a", [])

            return data

        except Exception as e:
            logging.error(f"DB Read Error: {e}")
            return empty_db()


def save_data(data):
    with db_lock:
        temp = DATA_FILE + ".tmp"

        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            os.replace(temp, DATA_FILE)

        except Exception as e:
            logging.error(f"DB Save Error: {e}")


def ensure_user(data, user_id):
    user_id = str(user_id)

    if user_id not in data["history"]:
        data["history"][user_id] = {
            "u": [],
            "a": [],
            "name": "Unknown",
            "username": "N/A"
        }

    if user_id not in data["autodelete"]:
        data["autodelete"][user_id] = False


def add_history(
    data,
    user_id,
    user_message_id=None,
    admin_message_id=None,
    name="Unknown",
    username="N/A"
):
    user_id = str(user_id)

    ensure_user(data, user_id)

    data["history"][user_id]["name"] = name
    data["history"][user_id]["username"] = username

    if user_message_id is not None:
        data["history"][user_id]["u"].append(
            int(user_message_id)
        )

    if admin_message_id is not None:
        data["history"][user_id]["a"].append(
            int(admin_message_id)
        )


# ================= AUTO DELETE =================

def auto_delete_worker():

    while True:

        try:
            time.sleep(DELETE_INTERVAL)

            data = load_data()

            changed = False

            for user_id, status in list(
                data["autodelete"].items()
            ):

                if status is not True:
                    continue

                history = data["history"].get(
                    user_id,
                    {}
                )

                user_messages = history.get("u", [])[:]
                admin_messages = history.get("a", [])[:]

                for msg_id in user_messages:
                    try:
                        bot.delete_message(
                            int(user_id),
                            int(msg_id)
                        )
                    except Exception:
                        pass

                for msg_id in admin_messages:
                    try:
                        bot.delete_message(
                            ADMIN_ID,
                            int(msg_id)
                        )
                    except Exception:
                        pass

                if user_messages or admin_messages:

                    data["history"][user_id]["u"] = []
                    data["history"][user_id]["a"] = []

                    changed = True

            if changed:
                save_data(data)

        except Exception as e:
            logging.error(
                f"AutoDelete Worker Error: {e}"
            )


# ================= START COMMAND =================

@bot.message_handler(commands=["start"])
def start(message):

    chat_id = message.chat.id
    data = load_data()

    if chat_id == ADMIN_ID:

        bot.send_message(
            ADMIN_ID,
            f"""
🛡️ PRIVATE ADMIN PANEL

↩️ Reply करके जवाब दें।

👥 /users
📨 /msg
🚫 /blocked
⛔ /ban <id>
✅ /unban <id>

🔥 /autodeleteon
❌ /autodeleteoff

🧹 /clear
💥 /clearall

⏱️ AutoDelete Timer: {DELETE_INTERVAL}s
"""
        )

        return

    user_id = str(chat_id)

    if user_id in data["blocked"]:

        bot.send_message(
            chat_id,
            "⛔ आपको इस bot से block कर दिया गया है।"
        )

        return

    name = (
        message.from_user.first_name
        or "No Name"
    )

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "N/A"
    )

    is_returning = user_id in data["history"]

    ensure_user(data, chat_id)

    data["history"][user_id]["name"] = name
    data["history"][user_id]["username"] = username

    status = (
        "✅ ON"
        if data["autodelete"].get(user_id)
        else "❌ OFF"
    )

    if is_returning:

        bot.send_message(
            chat_id,
            f"""
🙏 वापस स्वागत है!

Auto Delete Status: {status}
Timer: {DELETE_INTERVAL}s

/autodeleteon
/autodeleteoff
"""
        )

        admin_msg = bot.send_message(
            ADMIN_ID,
            f"""
🔄 USER RETURNED

👤 {name}
🆔 `{chat_id}`
AutoDelete: {status}
""",
            parse_mode="Markdown"
        )

    else:

        bot.send_message(
            chat_id,
            f"""
🙏 नमस्ते!

Auto Delete Status: {status}
Timer: {DELETE_INTERVAL}s

/autodeleteon
/autodeleteoff
"""
        )

        admin_msg = bot.send_message(
            ADMIN_ID,
            f"""
🔔 NEW USER

👤 {name}
🆔 `{chat_id}`
AutoDelete: {status}
""",
            parse_mode="Markdown"
        )

    data["reply_map"][
        str(admin_msg.message_id)
    ] = str(chat_id)

    save_data(data)


# ================= AUTO DELETE COMMANDS =================

def set_autodelete(message, status):

    chat_id = str(message.chat.id)
    data = load_data()

    target_user = chat_id

    if message.chat.id == ADMIN_ID:

        if not message.reply_to_message:

            bot.send_message(
                ADMIN_ID,
                f"⚠️ किसी user के message पर Reply करके "
                f"`/{'autodeleteon' if status else 'autodeleteoff'}` करो",
                parse_mode="Markdown"
            )

            return

        target_user = data["reply_map"].get(
            str(message.reply_to_message.message_id)
        )

        if not target_user:

            bot.send_message(
                ADMIN_ID,
                "❌ Mapping नहीं मिली।"
            )

            return

    ensure_user(data, target_user)

    data["autodelete"][target_user] = status

    if status:

        bot.send_message(
            message.chat.id,
            f"""
🔥 Auto Delete ON कर दिया गया।

अब इस chat की history लगभग
{DELETE_INTERVAL}s के बाद delete होगी।
"""
        )

        msg_text = "🔥 Admin ने Auto Delete ON कर दिया है।"

    else:

        bot.send_message(
            message.chat.id,
            "❌ Auto Delete OFF कर दिया गया।"
        )

        msg_text = "❌ Admin ने Auto Delete OFF कर दिया है।"

    if message.chat.id == ADMIN_ID:

        try:
            bot.send_message(
                int(target_user),
                msg_text
            )
        except Exception:
            pass

    else:

        try:
            bot.send_message(
                ADMIN_ID,
                f"{msg_text}\n\n"
                f"User `{target_user}` ने Auto Delete "
                f"{'ON' if status else 'OFF'} किया है।",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    save_data(data)


@bot.message_handler(commands=["autodeleteon"])
def autodelete_on(message):
    set_autodelete(message, True)


@bot.message_handler(commands=["autodeleteoff"])
def autodelete_off(message):
    set_autodelete(message, False)


# ================= USERS =================

@bot.message_handler(commands=["users"])
def users(message):

    if message.chat.id != ADMIN_ID:
        return

    data = load_data()

    users_list = list(
        data["history"].keys()
    )

    if not users_list:

        bot.send_message(
            ADMIN_ID,
            "👥 अभी कोई saved user नहीं है।"
        )

        return

    text = (
        "👥 SAVED USERS\n"
        "🔥 = AutoDelete ON\n\n"
    )

    for i, user_id in enumerate(
        users_list,
        1
    ):

        name = data["history"][user_id].get(
            "name",
            "Unknown"
        )

        status = (
            "⛔"
            if user_id in data["blocked"]
            else
            "🔥"
            if data["autodelete"].get(user_id)
            else "✅"
        )

        text += (
            f"{i}. {status} 👤 {name}\n"
            f"🆔 `{user_id}`\n\n"
        )

    bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="Markdown"
    )


# ================= BLOCKED USERS =================

@bot.message_handler(commands=["blocked"])
def blocked_users(message):

    if message.chat.id != ADMIN_ID:
        return

    data = load_data()

    blocked_list = data["blocked"]

    if not blocked_list:

        bot.send_message(
            ADMIN_ID,
            "🚫 अभी कोई blocked user नहीं है।"
        )

        return

    text = (
        "🚫 BLOCKED USERS\n"
        "`/unban USER_ID`\n\n"
    )

    for i, user_id in enumerate(
        blocked_list,
        1
    ):

        name = data["history"].get(
            user_id,
            {}
        ).get(
            "name",
            "Unknown"
        )

        text += (
            f"{i}. 👤 {name}\n"
            f"🆔 `{user_id}`\n\n"
        )

    bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="Markdown"
    )


# ================= BAN =================

@bot.message_handler(commands=["ban"])
def ban_user(message):

    if message.chat.id != ADMIN_ID:
        return

    data = load_data()

    parts = message.text.split(
        " ",
        1
    )

    if len(parts) < 2:

        bot.send_message(
            ADMIN_ID,
            "⚠️ Use: `/ban 123456789`",
            parse_mode="Markdown"
        )

        return

    target_user = parts[1].strip()

    if target_user not in data["history"]:

        bot.send_message(
            ADMIN_ID,
            "❌ user DB में नहीं है।"
        )

        return

    if target_user in data["blocked"]:

        bot.send_message(
            ADMIN_ID,
            "⚠️ पहले से blocked है।"
        )

        return

    data["blocked"].append(target_user)

    save_data(data)

    bot.send_message(
        ADMIN_ID,
        f"⛔ BANNED: `{target_user}`",
        parse_mode="Markdown"
    )

    try:
        bot.send_message(
            int(target_user),
            "⛔ आपको इस bot से block कर दिया गया है।"
        )
    except Exception:
        pass


# ================= UNBAN =================

@bot.message_handler(commands=["unban"])
def unban_user(message):

    if message.chat.id != ADMIN_ID:
        return

    data = load_data()

    parts = message.text.split(
        " ",
        1
    )

    if len(parts) < 2:

        bot.send_message(
            ADMIN_ID,
            "⚠️ Use: `/unban 123456789`",
            parse_mode="Markdown"
        )

        return

    target_user = parts[1].strip()

    if target_user not in data["blocked"]:

        bot.send_message(
            ADMIN_ID,
            "❌ ये blocked नहीं है।"
        )

        return

    data["blocked"].remove(target_user)

    save_data(data)

    bot.send_message(
        ADMIN_ID,
        f"✅ UNBANNED: `{target_user}`",
        parse_mode="Markdown"
    )

    try:
        bot.send_message(
            int(target_user),
            "✅ आपको unblock कर दिया गया है।"
        )
    except Exception:
        pass


# ================= ADMIN MESSAGE =================

@bot.message_handler(commands=["msg"])
def msg_user(message):

    if message.chat.id != ADMIN_ID:
        return

    data = load_data()

    parts = message.text.split(
        " ",
        2
    )

    if len(parts) < 3:

        bot.send_message(
            ADMIN_ID,
            "⚠️ Use: `/msg 123456789 Hello`",
            parse_mode="Markdown"
        )

        return

    target_user = parts[1]
    text = parts[2]

    if target_user in data["blocked"]:

        bot.send_message(
            ADMIN_ID,
            "⛔ ये user blocked है।"
        )

        return

    if target_user not in data["history"]:

        bot.send_message(
            ADMIN_ID,
            "❌ user DB में नहीं है।"
        )

        return

    try:

        sent = bot.send_message(
            int(target_user),
            f"📨 ADMIN:\n\n{text}"
        )

        data["history"][target_user]["a"].append(
            sent.message_id
        )

        save_data(data)

        bot.send_message(
            ADMIN_ID,
            f"✅ Sent to `{target_user}`",
            parse_mode="Markdown"
        )

    except Exception as e:

        bot.send_message(
            ADMIN_ID,
            f"❌ Error: {e}"
        )


# ================= CLEAR USER =================

@bot.message_handler(commands=["clear"])
def clear_user(message):

    chat_id = message.chat.id
    data = load_data()

    target_user = None

    if chat_id == ADMIN_ID:

        if not message.reply_to_message:

            bot.send_message(
                ADMIN_ID,
                "⚠️ Reply करके /clear भेजें।"
            )

            return

        target_user = data["reply_map"].get(
            str(message.reply_to_message.message_id)
        )

        if not target_user:

            bot.send_message(
                ADMIN_ID,
                "❌ Mapping नहीं मिली।"
            )

            return

    else:

        target_user = str(chat_id)

    if target_user not in data["history"]:

        bot.send_message(
            chat_id,
            "ℹ️ History नहीं मिली।"
        )

        return

    history = data["history"][target_user]

    for msg_id in history.get("u", []):

        try:
            bot.delete_message(
                int(target_user),
                int(msg_id)
            )
        except Exception:
            pass

    for msg_id in history.get("a", []):

        try:
            bot.delete_message(
                ADMIN_ID,
                int(msg_id)
            )
        except Exception:
            pass

    for message_id, mapped_user in list(
        data["reply_map"].items()
    ):

        if str(mapped_user) == target_user:
            del data["reply_map"][message_id]

    data["history"][target_user]["u"] = []
    data["history"][target_user]["a"] = []

    save_data(data)

    bot.send_message(
        chat_id,
        f"🧹 CHAT CLEARED: {target_user}"
    )


# ================= CLEAR ALL =================

@bot.message_handler(commands=["clearall"])
def clear_all(message):

    if message.chat.id != ADMIN_ID:
        return

    data = load_data()

    all_users = list(
        data["history"].keys()
    )

    for user_id in data["history"]:

        data["history"][user_id]["u"] = []
        data["history"][user_id]["a"] = []

    data["reply_map"] = {}

    save_data(data)

    bot.send_message(
        ADMIN_ID,
        f"""
💥 CLEAR ALL COMPLETE

👥 Users: {len(all_users)}
"""
    )


# ================= MESSAGE TYPES =================

SUPPORTED_TYPES = [
    "text",
    "photo",
    "video",
    "document",
    "audio",
    "voice",
    "sticker",
    "animation",
    "contact",
    "location"
]


# ================= MAIN CHAT HANDLER =================

@bot.message_handler(
    func=lambda message: True,
    content_types=SUPPORTED_TYPES
)
def handle_message(message):

    chat_id = message.chat.id
    message_id = message.message_id

    data = load_data()

    # ===== ADMIN → USER =====

    if chat_id == ADMIN_ID:

        if not message.reply_to_message:

            bot.send_message(
                ADMIN_ID,
                "⚠️ User के message पर Reply करके जवाब भेजें।"
            )

            return

        target_user = data["reply_map"].get(
            str(message.reply_to_message.message_id)
        )

        if not target_user:

            bot.send_message(
                ADMIN_ID,
                "❌ ये message किसी user का नहीं है।"
            )

            return

        if target_user in data["blocked"]:

            bot.send_message(
                ADMIN_ID,
                "⛔ ये user blocked है।"
            )

            return

        try:

            reply_to_id = None

            if (
                target_user in data["history"]
                and data["history"][target_user]["u"]
            ):
                reply_to_id = data["history"][target_user]["u"][-1]

            copied = bot.copy_message(
                chat_id=int(target_user),
                from_chat_id=ADMIN_ID,
                message_id=message_id,
                reply_to_message_id=reply_to_id
            )

            add_history(
                data,
                target_user,
                user_message_id=copied.message_id,
                admin_message_id=message_id
            )

            save_data(data)

        except Exception as e:

            logging.error(
                f"Admin → User error: {e}"
            )

            bot.send_message(
                ADMIN_ID,
                f"❌ Error: {e}"
            )

        return

    # ===== USER → ADMIN =====

    user_id = str(chat_id)

    if user_id in data["blocked"]:
        return

    name = (
        message.from_user.first_name
        or "No Name"
    )

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "N/A"
    )

    try:

        ensure_user(
            data,
            user_id
        )

        reply_to_id = None

        if (
            message.reply_to_message
            and data["history"].get(user_id)
            and data["history"][user_id]["a"]
        ):
            reply_to_id = data["history"][user_id]["a"][-1]

        copied = bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=chat_id,
            message_id=message_id,
            reply_to_message_id=reply_to_id
        )

        admin_message_id = copied.message_id

        data["reply_map"][
            str(admin_message_id)
        ] = user_id

        add_history(
            data,
            user_id,
            user_message_id=message_id,
            admin_message_id=admin_message_id,
            name=name,
            username=username
        )

        save_data(data)

    except Exception as e:

        logging.error(
            f"User → Admin error: {e}"
        )


# ================= MESSAGE REACTIONS =================

@bot.message_handler(
    content_types=["message_reaction"]
)
def handle_reaction(update):

    data = load_data()

    c