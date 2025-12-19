import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from core.db import (
    get_user_state, update_user_state, 
    add_transaction, get_balances, init_db
)
from core.ui import (
    Views, TOASTS, 
    get_main_menu_keyboard, get_finances_keyboard, 
    get_cancel_keyboard, generate_ascii_tree
)
from core.parser import parse_expense_text

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
    await query.answer(TOASTS['loading'], show_alert=False)
    
    # Logic Routing
    if data == 'btn_back_home':
        # Reset State
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

    elif data == 'btn_add_expense':
        # Set State -> Prompt User
        # We store the message_id so we can edit THIS message later when they type
        update_user_state(user_id, chat_id, 'AWAITING_INPUT', {'msg_id': query.message.message_id})
        
        await query.edit_message_text(
            text=Views.AWAITING_INPUT,
            reply_markup=get_cancel_keyboard(),
            parse_mode=ParseMode.HTML
        )
        
    elif data == 'btn_refresh_finances':
        balances = get_balances()
        tree_view = generate_ascii_tree(balances)
        # Using edit_message_text with same content might throw error if unchanged, 
        # so we catch it or ignore. simplified here.
        try:
            await query.edit_message_text(
                text=f"<b>💰 Finances</b>\n\n{tree_view}\n\n<i>Last updated: Just now</i>",
                reply_markup=get_finances_keyboard(),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass # Message content was same

# --- Message Handler (Text Input) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text
    
    # 1. Delete user's message to keep chat clean (The "App" feel)
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")

    # 2. Check User State
    user_record = get_user_state(user_id)
    state = user_record['state']
    state_data = user_record.get('data', {})
    dashboard_msg_id = state_data.get('msg_id')

    if state == 'AWAITING_INPUT':
        # Parse logic
        parsed = parse_expense_text(text)
        
        if parsed:
            # Success: Save to DB
            add_transaction(user_id, parsed['amount'], parsed['description'], parsed['involved_users'])
            
            # Reset State
            update_user_state(user_id, chat_id, 'DASHBOARD', {'msg_id': dashboard_msg_id})
            
            # Edit the original Dashboard message
            success_text = (
                f"<b>✅ Recorded:</b> ${parsed['amount']:.2f} for {parsed['description']}\n\n"
                f"{Views.WELCOME}"
            )
            
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
                    # If edit fails (message too old), send new one
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=success_text,
                        reply_markup=get_main_menu_keyboard(),
                        parse_mode=ParseMode.HTML
                    )
        else:
            # Failure: Parsing failed
            # We don't change state, we just notify user
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
        # System Reset
        init_db() # Lazy init check
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=Views.WELCOME,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        # Save this message ID so we can edit it later
        update_user_state(user_id, chat_id, 'DASHBOARD', {'msg_id': msg.message_id})
