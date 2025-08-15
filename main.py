#!/usr/bin/env python3
import os, re, json, uuid, datetime, tempfile, pathlib, asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ----- Config -----
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "./data"))
MEDIA_DIR = DATA_DIR / "media"
JSONL_PATH = DATA_DIR / "entries.jsonl"
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # required
CAL_RE = re.compile(r"^\s*(\d{2,5})\s*(k?cal)?\s*$", re.I)

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
JSONL_PATH.touch(exist_ok=True)

def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)

def fmt_utc_human(dt: datetime.datetime) -> str:
    dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")

@dataclass
class PendingEntry:
    started_at: datetime.datetime
    texts: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)

    @property
    def description(self) -> str:
        return "\n".join(t for t in self.texts if t).strip()

# user_id -> PendingEntry
state: Dict[int, PendingEntry] = {}

# ----- Helpers -----
def get_or_create_entry(user_id: int) -> PendingEntry:
    if user_id not in state:
        state[user_id] = PendingEntry(started_at=utc_now())
    return state[user_id]

def save_jsonl(sent_dt: datetime.datetime, description: str, images: List[str], calories: int) -> None:
    payload = {
        "sent": fmt_utc_human(sent_dt),
        "description": description,
        "images": images,
        "calories": calories,
    }
    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Food diary ready.\n"
        "- Send text and/or photos.\n"
        "- Close with “850 cal”.\n"
        "Commands: /status, /discard, /help"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Usage:\n"
        "• Text/photo starts or updates the current entry.\n"
        "• Send “850 cal” (any 2–5 digits + optional kcal) to save & reset.\n"
        "• /status shows pending text/photo count.\n"
        "• /discard drops the pending entry."
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    pe = state.get(uid)
    if not pe:
        await update.message.reply_text("No pending entry.")
        return
    await update.message.reply_text(
        f"Pending since {fmt_utc_human(pe.started_at)}\n"
        f"Texts: {len(pe.texts)}\nPhotos: {len(pe.images)}\n"
        "Send “### cal” to save."
    )

async def cmd_discard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    pe = state.pop(uid, None)
    if not pe:
        await update.message.reply_text("Nothing to discard.")
        return
    await update.message.reply_text("Pending entry discarded.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Calories -> close & flush
    m = CAL_RE.match(text)
    if m:
        kcal = int(m.group(1))
        pe = state.get(uid)
        if not pe:
            await update.message.reply_text("No pending entry. Start by sending a message or a photo.")
            return
        desc = pe.description
        imgs = list(pe.images)
        sent_dt = pe.started_at
        save_jsonl(sent_dt, desc, imgs, kcal)
        state.pop(uid, None)
        await update.message.reply_text(
            f"Saved: {fmt_utc_human(sent_dt)}, {kcal} kcal, "
            f"{len(desc.splitlines()) if desc else 0} text line(s), {len(imgs)} photo(s)."
        )
        return

    # Otherwise accumulate text
    pe = get_or_create_entry(uid)
    pe.texts.append(text)
    await update.message.reply_text("Noted.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    uid = update.effective_user.id
    photo = update.message.photo[-1]  # largest size
    file = await photo.get_file()

    # Save to disk
    fname = f"{uuid.uuid4()}.jpg"
    fpath = MEDIA_DIR / fname
    # telegram saves to local path:
    await file.download_to_drive(custom_path=str(fpath))

    pe = get_or_create_entry(uid)
    pe.images.append(str(fpath))
    await update.message.reply_text("Photo added.")

def main():
    if not BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_TOKEN env var.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("discard", cmd_discard))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()