# main.py
# -*- coding: utf-8 -*-

import os
import csv
import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.constants import ParseMode
from fpdf import FPDF
from googletrans import Translator
from keep_alive import keep_alive  # <<<--- የድር ሰርቨሩን ለማስጀመር

# --- የይዘት ፋይሎች ---
from bot_content import NEWS_ARTICLES, PRESS_RELEASES, POLICY_INFO, SPECIAL_ANALYSIS

# --- የሚስጥር ቁልፎችን ከ Environment Variables ማንበብ ---
# ይህንን በቀጥታ ኮዱ ላይ አናስቀምጥም! Render ላይ እናስገባዋለን።
TELEGRAM_API_TOKEN = os.environ.get("TELEGRAM_API_TOKEN")
ADMIN_CHANNEL_ID = os.environ.get("ADMIN_CHANNEL_ID")

# ⚠️ ወሳኝ ማሳሰቢያ! ⚠️
# Render ላይ ያለው የፋይል ሲስተም ቋሚ አይደለም (ephemeral)።
# ይህ ማለት ከታች ያሉት ፋይሎች (members.csv, last_id.txt, ፎቶዎች)
# ሰርቨሩ restart ሲሆን ወይም ሲተኛ ይጠፋሉ። ይህንን ችግር በዘላቂነት ለመፍታት
# እንደ Render Postgres ያለ ዳታቤዝ መጠቀም ይመከራል። ለአሁኑ ግን ቦቱ እንዲሰራ እናድርገው።
MEMBERS_CSV = "members.csv"
ID_FILE = "last_id.txt"

# ... (ከዚህ በታች ያለው ያንተ የመጀመሪያ ኮድ ነው፣ ምንም አልተቀየረም) ...

# የውይይት ደረጃዎች
(PHOTO, NAME_AM, NAME_EN, DOB, GENDER, NATIONALITY, REGION_AM, SUB_CITY_AM,
 WOREDA_AM, KEBELE, PHONE, EMAIL_CHOICE, EMAIL, SUPPORT_AMOUNT, CONFIRMATION) = range(15)

# የፋይል ስሞች እና ቋሚ ተለዋዋጮች
FONT_PATH = 'AbyssinicaSIL-Regular.ttf'; LOGO_PATH = 'ealpa_logo.png'
SIGNATURE_PATH = 'signature.png'; translator = Translator()

REGIONS_KEYBOARD = [
    ['አዲስ አበባ', 'አማራ', 'ኦሮሚያ'], ['ትግራይ', 'ደቡብ ኢትዮጵያ', 'ሶማሌ'],
    ['አፋር', 'ቤኒሻንጉል ጉሙዝ', 'ጋምቤላ'], ['ሲዳማ', 'ደቡብ ምዕራብ', 'ሐረሪ'],
    ['ድሬዳዋ']
]

# --- HELPER FUNCTIONS ---
def get_next_id():
    if not os.path.exists(ID_FILE):
        with open(ID_FILE, "w") as f: f.write("1000")
    with open(ID_FILE, "r+") as f:
        last_id = int(f.read().strip()); next_id = last_id + 1
        f.seek(0); f.write(str(next_id))
    return f"EUDP-{str(next_id).zfill(6)}"

def gregorian_to_ethiopian_algorithm(year, month, day):
    jdn = (1461 * (year + 4800 + (month - 14) // 12)) // 4 + \
          (367 * (month - 2 - 12 * ((month - 14) // 12))) // 12 - \
          (3 * ((year + 4900 + (month - 14) // 12) // 100)) // 4 + day - 32075
    jera = jdn - 1723856; c = (jera - 1) // 1461; d = (jera - 1) % 1461
    a = d // 365; year = 4 * c + a
    if a == 4: year -= 1
    n = d - 365 * a; month = n // 30 + 1; day = n % 30 + 1
    return int(year), int(month), int(day)

def get_ethiopian_date(gregorian_date):
    try:
        y, m, d = gregorian_to_ethiopian_algorithm(gregorian_date.year, gregorian_date.month, gregorian_date.day)
        return f"{d}/{m}/{y}"
    except: return ""

def save_to_csv(user_data):
    fieldnames = ['id_number', 'photo_path', 'name_am', 'name_en', 'dob', 'gender', 'nationality', 'region_am', 'region_en', 'sub_city_am', 'sub_city_en', 'woreda_am', 'kebele', 'phone', 'email', 'support_amount', 'membership_date_gc', 'membership_date_ec']
    row_data = {field: user_data.get(field, '') for field in fieldnames}
    file_exists = os.path.isfile(MEMBERS_CSV)
    with open(MEMBERS_CSV, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames);
        if not file_exists: writer.writeheader()
        writer.writerow(row_data)

def translate_text(text):
    if not text or text.strip().lower() in ['n/a', 'የለኝም']: return ""
    try: return translator.translate(text, dest='en').text
    except: return ""

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        if os.path.exists(LOGO_PATH): self.image(LOGO_PATH, x=10, y=8, w=20)
        self.add_font('Abyssinica', '', FONT_PATH); self.set_font('Abyssinica', '', 14)
        self.set_y(12); self.cell(0, 8, 'የአባልነት ማመልከቻ ቅጽ', ln=True, align='C')
        self.set_font('Times', 'B', 12); self.cell(0, 8, 'Membership Application Form', ln=True, align='C'); self.ln(5)
    def footer(self):
        self.set_y(-15); self.set_font('Abyssinica', '', 8); self.set_text_color(128); self.cell(0, 10, 'የኢትዮጵያ አንድነት እና ልማት ፓርቲ (ኢአልፓ)', 0, 0, 'C')

def generate_membership_pdf(ud):
    pdf = PDF('P', 'mm', 'A4'); pdf.add_page(); pdf.add_font('Abyssinica', '', FONT_PATH)
    pdf.rect(15, 40, 30, 40)
    if 'photo_path' in ud and os.path.exists(ud['photo_path']): pdf.image(ud['photo_path'], x=15.5, y=40.5, w=29, h=39)
    pdf.set_font('Abyssinica', '', 14); pdf.set_xy(50, 45); pdf.cell(0, 8, ud.get('name_am', ''))
    pdf.set_font('Times', '', 12); pdf.set_xy(50, 55); pdf.cell(0, 8, ud.get('name_en', ''))
    pdf.set_font('Courier', 'B', 12); pdf.set_xy(50, 65); pdf.cell(0, 8, f"ID: {ud.get('id_number', '')}"); pdf.ln(25)
    def f(a, e): am = a or ""; en = e or ""; return f"{am} / {en}" if am and en and en.lower() != "n/a" else am or en
    def d(x, y, la, le, data, w=90):
        pdf.set_xy(x, y); pdf.set_font('Abyssinica', '', 9); pdf.set_text_color(100, 100, 100); pdf.cell(40, 5, f"{la} / {le}")
        pdf.set_xy(x, y+5); pdf.set_font('Abyssinica', '', 11); pdf.set_text_color(0, 0, 0); pdf.cell(w, 8, f"  {data}"); pdf.line(x, y+13, x+w, y+13)
    pdf.set_font('Abyssinica', '', 12); pdf.set_fill_color(230, 230, 230); pdf.cell(0, 8, "  የግል መረጃ / Personal Information", ln=True, fill=True); pdf.ln(4)
    y = pdf.get_y(); d(15, y, 'የትውልድ ቀን', 'Date of Birth', ud.get('dob', ''), 80); d(110, y, 'ፆታ', 'Sex', ud.get('gender', ''), 50)
    y += 18; d(15, y, 'ዜግነት', 'Nationality', ud.get('nationality', ''), 80)
    pdf.set_y(y + 18); pdf.set_font('Abyssinica', '', 12); pdf.set_fill_color(230, 230, 230); pdf.cell(0, 8, "  የመገኛ አድራሻ / Contact Information", ln=True, fill=True); pdf.ln(4)
    y = pdf.get_y(); d(15, y, 'ክልል', 'Region', f(ud.get('region_am'), ud.get('region_en'))); d(110, y, 'ክ/ከተማ', 'Subcity', f(ud.get('sub_city_am'), ud.get('sub_city_en')))
    y += 18; d(15, y, 'ወረዳ', 'Woreda', ud.get('woreda_am', ''), 60); d(110, y, 'ቀበሌ', 'Kebele', ud.get('kebele', ''), 60)
    y += 18; d(15, y, 'ስልክ ቁጥር', 'Phone', ud.get('phone', '')); d(110, y, 'ኢ-ሜይል', 'E-mail', ud.get('email', ''))
    pdf.set_y(y + 25); pdf.set_font('Abyssinica', '', 10); pdf.multi_cell(0, 5, f"እኔ በአባልነት ከተመዘገብኩበት ቀን አንስቶ ፓርቲውን በ {ud.get('support_amount', '___')} ብር ለመደገፍ እንደተስማማሁ በፊርማዬ አረጋግጣለው።", align='C')
    pdf.set_y(250); pdf.line(20, 265, 80, 265); pdf.set_xy(20, 266); pdf.cell(60, 5, "የተመዝጋቢ ፊርማ", align='C')
    if os.path.exists(SIGNATURE_PATH): pdf.image(SIGNATURE_PATH, x=135, y=252, w=40)
    pdf.line(130, 265, 190, 265); pdf.set_xy(130, 266); pdf.cell(60, 5, "የሊቀመንበር ፊርማ", align='C')
    filename = f"EALPA_Form_{ud.get('id_number')}.pdf"; pdf.output(filename); return filename

# --- GENERAL & INFO COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "👋 ሰላም! ወደ ኢአልፓ ይፋዊ ቦት እንኳን በደህና መጡ!\n\nየሚፈልጉትን አገልግሎት ከታች ያሉትን ትዕዛዞች በመጠቀም ይምረጡ።\n\n/register - አባል ለመሆን\n/news - ዜናዎችን ለማየት\n/releases - ጋዜጣዊ መግለጫዎች\n/policies - የፓርቲውን ፖሊሲዎች ለማወቅ\n/analysis - ልዩ ትንታኔ ለማንበብ"
    await update.message.reply_text(help_text)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not NEWS_ARTICLES: await update.message.reply_text("ለጊዜው ምንም አዲስ ዜና የለም።"); return
    message = "📰 **የቅርብ ጊዜ ዜናዎች**\n\n" + "\n\n".join([f"🔹 **{a['title']}**\n   📅 _{a['date']}_\n\n{a['summary']}\n--------------------" for a in NEWS_ARTICLES[:3]])
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def releases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not PRESS_RELEASES: await update.message.reply_text("ለጊዜው ምንም አዲስ መግለጫ የለም።"); return
    message = "📢 **ጋዜጣዊ መግለጫዎች**\n\n" + "\n\n".join([f"📄 **{r['title']}**\n   📅 _{r['date']}_\n\n{r['content']}\n--------------------" for r in PRESS_RELEASES[:3]])
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔍 **ልዩ ትንታኔ**\n\n{SPECIAL_ANALYSIS}", parse_mode=ParseMode.MARKDOWN)

async def policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(p['title'], callback_data=key)] for key, p in POLICY_INFO.items()]
    await update.message.reply_text('እባክዎ መረጃ የሚፈልጉበትን የፖሊሲ አይነት ይምረጡ:', reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    policy = POLICY_INFO.get(query.data);
    if policy: await query.edit_message_text(text=f"**{policy['title']}**\n\n{policy['details']}", parse_mode=ParseMode.MARKDOWN)

# --- REGISTRATION CONVERSATION ---
async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); await update.message.reply_text("ወደ ምዝገባው ሂደት እንኳን በደህና መጡ።\n\nእባክዎ ለምዝገባ የሚሆን <b>ፎቶዎን</b> ይላኩ።\nለማቋረጥ /cancel ይላኩ።", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove()); return PHOTO
async def received_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file(); photo_path = f"{update.effective_user.id}.jpg"; await photo_file.download_to_drive(photo_path)
    context.user_data['photo_path'] = photo_path; await update.message.reply_text("ፎቶዎ ተቀብሏል። እባክዎ ሙሉ ስምዎን <b>በአማርኛ</b> ያስገቡ።", parse_mode=ParseMode.HTML); return NAME_AM
async def received_name_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name_am'] = update.message.text; await update.message.reply_text("እሺ። አሁን ሙሉ ስምዎን <b>በእንግሊዝኛ</b> ያስገቡ።", parse_mode=ParseMode.HTML); return NAME_EN
async def received_name_en(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name_en'] = update.message.text; await update.message.reply_text("የትውልድ ቀንዎን ያስገቡ (ለምሳሌ፡ 12/05/1985)"); return DOB
async def received_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dob'] = update.message.text; await update.message.reply_text("ፆታዎን ይምረጡ:", reply_markup=ReplyKeyboardMarkup([['ወንድ'], ['ሴት']], one_time_keyboard=True, resize_keyboard=True)); return GENDER
async def received_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gender'] = update.message.text; await update.message.reply_text("ዜግነትዎን ይምረጡ:", reply_markup=ReplyKeyboardMarkup([['ኢትዮጵያዊ'], ['ሌላ']], one_time_keyboard=True, resize_keyboard=True)); return NATIONALITY
async def received_nationality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nationality'] = update.message.text; await update.message.reply_text("የሚኖሩበትን ክልል ከታች ካሉት አማራጮች ይምረጡ:", reply_markup=ReplyKeyboardMarkup(REGIONS_KEYBOARD, one_time_keyboard=True, resize_keyboard=True)); return REGION_AM
async def received_region_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['region_am'] = update.message.text; await update.message.reply_text("ክፍለ ከተማ / ዞን <b>በአማርኛ</b> ያስገቡ:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove()); return SUB_CITY_AM
async def received_sub_city_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['sub_city_am'] = update.message.text; await update.message.reply_text("ወረዳዎን ያስገቡ:"); return WOREDA_AM
async def received_woreda_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['woreda_am'] = update.message.text; await update.message.reply_text("ቀበሌዎን ያስገቡ:"); return KEBELE
async def received_kebele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['kebele'] = update.message.text; await update.message.reply_text("ስልክ ቁጥርዎን ያስገቡ:"); return PHONE
async def received_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text; await update.message.reply_text("የኢሜይል አድራሻ አለዎት?", reply_markup=ReplyKeyboardMarkup([['አዎ አለኝ'], ['የለኝም']], one_time_keyboard=True, resize_keyboard=True)); return EMAIL_CHOICE
async def received_email_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'አዎ' in update.message.text: await update.message.reply_text("እባክዎ ኢሜይልዎን ያስገቡ:", reply_markup=ReplyKeyboardRemove()); return EMAIL
    else: context.user_data['email'] = ""; await update.message.reply_text("ወርሃዊ የድጋፍ መዋጮዎን በብር ይምረጡ:", reply_markup=ReplyKeyboardMarkup([['10'],['20'],['50'],['100']], one_time_keyboard=True, resize_keyboard=True)); return SUPPORT_AMOUNT
async def received_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text; await update.message.reply_text("ወርሃዊ የድጋፍ መዋጮዎን በብር ይምረጡ:", reply_markup=ReplyKeyboardMarkup([['10'], ['20'], ['50'], ['100']], one_time_keyboard=True, resize_keyboard=True)); return SUPPORT_AMOUNT
async def received_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['support_amount'] = update.message.text; await update.message.reply_text("እናመሰግናለን። መረጃዎ እየተጠቃለለ ነው...", reply_markup=ReplyKeyboardRemove())
    ud = context.user_data; ud['region_en'] = translate_text(ud.get('region_am')); ud['sub_city_en'] = translate_text(ud.get('sub_city_am'))
    today = datetime.date.today(); ud['membership_date_gc'] = today.strftime("%d/%m/%Y"); ud['membership_date_ec'] = get_ethiopian_date(today); ud['id_number'] = get_next_id()
    summary = "<b>እባክዎ መረጃዎን ያረጋግጡ:</b>\n\n" + "\n".join([f"<b>{k.replace('_', ' ').title()}:</b> {v}" for k,v in ud.items() if k!='photo_path' and v]) + "\n\nመረጃው ትክክል ነው?"
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([['አዎ, ላክ'], ['አይ, ልሰርዝ']], one_time_keyboard=True, resize_keyboard=True), parse_mode=ParseMode.HTML); return CONFIRMATION

async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == 'አዎ, ላክ':
        await update.message.reply_text("በጣም ጥሩ! የመጨረሻው ሰነድ እየተዘጋጀ ነው...", reply_markup=ReplyKeyboardRemove())
        async def forward_to_admins(pdf_path):
            try:
                caption = f"✅ **አዲስ ተመዝጋቢ**\n\n**ስም:** {context.user_data.get('name_am')}\n**ID:** {context.user_data.get('id_number')}\n**ስልክ:** {context.user_data.get('phone')}"
                await context.bot.send_document(chat_id=ADMIN_CHANNEL_ID, document=open(pdf_path, 'rb'), caption=caption, parse_mode=ParseMode.MARKDOWN)
            except Exception as e: print(f"Failed to forward: {e}")
        try:
            save_to_csv(context.user_data); pdf_filename = generate_membership_pdf(context.user_data)
            await forward_to_admins(pdf_filename)
            await update.message.reply_document(document=open(pdf_filename, 'rb'), caption="ምዝገባዎ በተሳካ ሁኔታ ተጠናቋል!")
            os.remove(pdf_filename); os.remove(context.user_data['photo_path'])
        except Exception as e: await update.message.reply_text(f"ይቅርታ፣ ስህተት አጋጥሟል: {e}")
    else: os.remove(context.user_data['photo_path']); await update.message.reply_text("ምዝገባው ተሰርዟል።", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear(); return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'photo_path' in context.user_data and os.path.exists(context.user_data['photo_path']): os.remove(context.user_data['photo_path'])
    context.user_data.clear(); await update.message.reply_text("ምዝገባው ተሰርዟል።", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

# --- ዋናውን የቦት ማስጀመሪያ ተግባር ---
def main() -> None:
    """ይህ ፈንክሽን ቦቱን ገንብቶ ያስጀምራል"""
    if not TELEGRAM_API_TOKEN or not ADMIN_CHANNEL_ID:
        print("❌ ስህተት: TELEGRAM_API_TOKEN እና ADMIN_CHANNEL_ID በ Environment Variables ውስጥ መቀመጥ አለባቸው።")
        return

    application = Application.builder().token(TELEGRAM_API_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_command)],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, received_photo)], NAME_AM: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_name_am)],
            NAME_EN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_name_en)], DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_dob)],
            GENDER: [MessageHandler(filters.Regex('^(ወንድ|ሴት)$'), received_gender)], NATIONALITY: [MessageHandler(filters.Regex('^(ኢትዮጵያዊ|ሌላ)$'), received_nationality)],
            REGION_AM: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_region_am)], SUB_CITY_AM: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_sub_city_am)],
            WOREDA_AM: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_woreda_am)], KEBELE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_kebele)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_phone)], EMAIL_CHOICE: [MessageHandler(filters.Regex('^(አዎ አለኝ|የለኝም)$'), received_email_choice)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_email)], SUPPORT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_support)],
            CONFIRMATION: [MessageHandler(filters.Regex('^(አዎ, ላክ|አይ, ልሰርዝ)$'), confirmation)],
        }, fallbacks=[CommandHandler('cancel', cancel)], per_message=False
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(CommandHandler("releases", releases_command))
    application.add_handler(CommandHandler("analysis", analysis_command))
    application.add_handler(CommandHandler("policies", policy_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("✅ የቴሌግራም ቦት እየተነሳ ነው (Polling)...")
    application.run_polling()

if __name__ == '__main__':
    keep_alive()  # የድር ሰርቨሩን (ለUptimeRobot) ከበስተጀርባ ያስነሳል
    main()        # የቴሌግራም ቦቱን ያስነሳል
