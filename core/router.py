import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Database Logic
from core.db import (
    get_user_state, update_user_state, 
    add_transaction, get_balances, init_db,
    get_all_users, register_user
)

# UI & Visuals
from core.ui import (
    Views, TOASTS, 
    get_main_menu_keyboard, get_finances_keyboard, 
    get_cancel_keyboard, generate_ascii_tree,
    get_members_keyboard, get_settings_keyboard
)

# Input Parser
from core.parser import parse_expense_text

# Configure Logger
logger = logging.getLogger(__name__)

async def route_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main entry point for every webhook.
    """
    # 1. Handle Button Clicks (Callback Queries)
    if update.callback_query:
        await handle_callback(update, context)
        return

    # 2. Handle Text Messages
    if update.message and update.message.text:
        await handle_message(update, context)
        return

# --- Callback Handler (Button Clicks) ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data
    
    # Send immediate feedback (Toast)
    # We use different toasts for different actions
    toast_msg = TOASTS['loading']
    if data == 'btn_join': toast_msg = "📝 Signing the ledger..."
    
    try:
        await query.answer(toast_msg, show_alert=False)
    except Exception:
        pass # Ignore if answer fails (e.g. network blip)
    
    # --- ROUTING LOGIC ---
    
    if data == 'btn_back_home':
        # Reset State to Dashboard
        update_user_state(user_id, chat_id, 'DASHBOARD', {'msg_id': query.message.message_id})
        await query.edit_message_text(
            text=Views.WELCOME,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )

    elif data == 'btn_finances':
        # Fetch Data -> Render Tree
        balances = get_balances()
        tree_view = generate_ascii_tree(balances)
        
        await query.edit_message_text(
            text=f"<b>💰 Finances</b>\n\n{tree_view}",
            reply_markup=get_finances_keyboard(),
            parse_mode=ParseMode.HTML
        )
    
    elif data == 'btn_refresh_finances':
        balances = get_balances()
        tree_view = generate_ascii_tree(balances)
        try:
            await query.edit_message_text(
                text=f"<b>💰 Finances</b>\n\n{tree_view}\n\n<i>Last updated: Just now</i>",
                reply_markup=get_finances_keyboard(),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass # Ignore "Message is not modified" errors

    elif data == 'btn_add_expense':
        # Set State -> Prompt User
        # We store the message_id so we can edit THIS message later when they type
        update_user_state(user_id, chat_id, 'AWAITING_INPUT', {'msg_id': query.message.message_id})
        
        await query.edit_message_text(
            text=Views.AWAITING_INPUT,
            reply_markup=get_cancel_keyboard(),
            parse_mode=ParseMode.HTML
        )

    elif data == 'btn_members':
        # Fetch Users
        users = get_all_users()
        
        # Build Text List
        if users:
            # Simple list of usernames
            user_list = "\n".join([f"👤 <b>{u['username']}</b>" for u in users])
            text = f"<b>👥 Guild Members</b>\n\n{user_list}"
        else:
            text = "<b>👥 Guild Members</b>\n\n<i>No members found. Be the first to join!</i>"
            
        await query.edit_message_text(
            text=text,
            reply_markup=get_members_keyboard(),
            parse_mode=ParseMode.HTML
        )

    elif data == 'btn_join':
        # Register the user in the DB
        # query.from_user provides the Telegram user info
        username = query.from_user.username or f"User{user_id}"
        full_name = query.from_user.full_name or "Unknown"
        
        register_user(user_id, username, full_name)
        
        # Refresh the Members list immediately to show the new name
        users = get_all_users()
        user_list = "\n".join([f"👤 <b>{u['username']}</b>" for u in users])
        
        # Show a "Success" alert (Pop-up)
        await query.answer("✅ You have joined the Guild!", show_alert=True)
        
        await query.edit_message_text(
            text=f"<b>👥 Guild Members</b>\n\n{user_list}",
            reply_markup=get_members_keyboard(),
            parse_mode=ParseMode.HTML
        )

    elif data == 'btn_settings':
        await query.edit_message_text(
            text=Views.SETTINGS,
            reply_markup=get_settings_keyboard(),
            parse_mode=ParseMode.HTML
        )
    
    elif data == 'btn_history':
        # Placeholder for future history feature
        await query.answer("📜 Detailed history is coming in v1.1!", show_alert=True)

    elif data == 'btn_noop':
        # Used for toggle buttons that are just visual for now
        await query.answer("Feature coming soon!", show_alert=False)

    elif data == 'btn_leave':
        await query.answer("🚫 Leaving is disabled in this version.", show_alert=True)


# --- Message Handler (Text Input) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text
    
    # 1. Attempt to Delete user's message to keep chat clean
    # (Might fail in private chats or if no admin rights, so we catch it)
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")

    # 2. Check User State (Are they adding an expense?)
    user_record = get_user_state(user_id)
    state = user_record['state']
    state_data = user_record.get('data', {})
    dashboard_msg_id = state_data.get('msg_id')

    if state == 'AWAITING_INPUT':
        # NLP Parse Logic
        parsed = parse_expense_text(text)
        
        if parsed:
            # Success: Save to DB
            add_transaction(user_id, parsed['amount'], parsed['description'], parsed['involved_users'])
            
            # Reset State to Dashboard
            update_user_state(user_id, chat_id, 'DASHBOARD', {'msg_id': dashboard_msg_id})
            
            # Prepare Success Message
            success_text = (
                f"<b>✅ Recorded:</b> ${parsed['amount']:.2f} for {parsed['description']}\n\n"
                f"{Views.WELCOME}"
            )
            
            # Edit the original Dashboard message
            if dashboard_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=dashboard_msg_id,
                        text=success_text,
                        reply_markup=get_main_menu_keyboard(),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    # Fallback: Send new message if edit fails (msg too old/deleted)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=success_text,
                        reply_markup=get_main_menu_keyboard(),
                        parse_mode=ParseMode.HTML
                    )
        else:
            # Failure: Could not parse amount
            # We notify the user but keep them in AWAITING_INPUT state
             if dashboard_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=dashboard_msg_id,
                        text=f"⚠️ <b>Could not parse amount.</b>\nTry again: '20 lunch'\n\n{Views.AWAITING_INPUT}",
                        reply_markup=get_cancel_keyboard(),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

    elif text == "/start":
        # System Reset / Initialize
        init_db() # Lazy init check (Create tables if missing)
        
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=Views.WELCOME,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        
        # Save this message ID so we can edit it later
        update_user_state(user_id, chat_id, 'DASHBOARD', {'msg_id': msg.message_id})
