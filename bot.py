import os
import sqlite3
import imaplib
from email import policy
from email.parser import BytesParser
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EMAIL_ACCOUNT = os.getenv('EMAIL_ACCOUNT')
APP_PASSWORD = os.getenv('APP_PASSWORD')
IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = int(os.getenv('IMAP_PORT'))
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

conn = sqlite3.connect('email_bot.db')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        telegram_id INTEGER,
        email_list TEXT
    )
''')
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Welcome! Send me a list of emails, each separated by a new line.')

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cursor.execute('DELETE FROM users WHERE user_id = ?', (update.message.from_user.id,))
    conn.commit()
    await update.message.reply_text('Your emails have been deleted. Click /start to add new emails.')

async def show_subscribed_emails(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cursor.execute('SELECT email_list FROM users WHERE user_id = ?', (update.message.from_user.id,))
    result = cursor.fetchone()
    if result:
        await update.message.reply_text(f"Your subscribed emails:\n{result[0]}")
    else:
        await update.message.reply_text("You haven't subscribed to any emails yet.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    email_list = update.message.text.strip().split('\n')
    
    if not all('@' in email for email in email_list):
        await update.message.reply_text('Please provide valid email addresses, each on a new line.')
        return

    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, telegram_id, email_list)
        VALUES (?, ?, ?)
    ''', (user_id, update.message.chat_id, '\n'.join(email_list)))
    conn.commit()

    await update.message.reply_text('Your emails have been saved.')

def fetch_emails():
    with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as mail:
        mail.login(EMAIL_ACCOUNT, APP_PASSWORD)
        mail.select('inbox')
        status, data = mail.search(None, 'UNSEEN')
        mail_ids = data[0].split()

        emails = []
        for mail_id in mail_ids:
            status, msg_data = mail.fetch(mail_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = BytesParser(policy=policy.default).parsebytes(response_part[1])
                    emails.append(msg)
            mail.store(mail_id, '+FLAGS', '\\Seen')
    return emails

async def get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    cursor.execute('SELECT email_list FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if not result:
        await update.message.reply_text("You haven't subscribed to any emails yet. Use /start to add emails.")
        return

    # Send initial "Processing..." message
    processing_message = await update.message.reply_text("Processing... Please wait.")

    user_emails = result[0].split('\n')
    emails = fetch_emails()
    
    response_text = ""
    otps_found = False
    for email in emails:
        recipient = email['to']
        if recipient in user_emails:
            body = email.get_payload(decode=True).decode()
            body_text = BeautifulSoup(body, 'html.parser').get_text().replace('\n', '')
            response_text += f"OTP for {recipient}:\n\n{body_text}\n\n"
            otps_found = True
    
    if not otps_found:
        response_text = "No new OTPs found for your subscribed emails."

    # Update the "Processing..." message with the actual response
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=processing_message.message_id,
        text=response_text
    )
    
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("show", show_subscribed_emails))
    application.add_handler(CommandHandler("getOtp", get_otp))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()