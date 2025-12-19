"""
Minimal Telegram Bot for Vercel + Neon Testing
This webhook handles incoming Telegram updates and responds with a test message.
"""

import os
import json
import psycopg2
from http.server import BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.parse import urlencode

# Environment variables (set in Vercel dashboard)
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')  # Automatically injected by Vercel+Neon

def send_telegram_message(chat_id, text):
    """Send a message to Telegram chat"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    req = Request(url, data=urlencode(data).encode(), method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    
    with urlopen(req) as response:
        return json.loads(response.read().decode())

def test_database_connection():
    """Test Neon PostgreSQL connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()
        
        # Test query
        cur.execute("SELECT version();")
        db_version = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return {"success": True, "version": db_version}
    except Exception as e:
        return {"success": False, "error": str(e)}

class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler"""
    
    def do_POST(self):
        """Handle incoming Telegram webhook"""
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            update = json.loads(body.decode())
            
            # Extract message data
            if 'message' in update:
                message = update['message']
                chat_id = message['chat']['id']
                text = message.get('text', '')
                user = message.get('from', {})
                username = user.get('username', 'Unknown')
                
                # Handle /start command
                if text == '/start':
                    response_text = (
                        "🏰 <b>Guild Bot Test</b>\n\n"
                        f"✅ Webhook is working!\n"
                        f"👤 User: @{username}\n"
                        f"💬 Chat ID: {chat_id}\n\n"
                        "Testing database connection..."
                    )
                    send_telegram_message(chat_id, response_text)
                    
                    # Test database
                    db_result = test_database_connection()
                    
                    if db_result['success']:
                        db_text = (
                            "✅ <b>Database Connected!</b>\n\n"
                            f"<code>{db_result['version'][:50]}...</code>\n\n"
                            "🎉 Infrastructure test PASSED!\n"
                            "Ready for feature development."
                        )
                    else:
                        db_text = (
                            "❌ <b>Database Connection Failed</b>\n\n"
                            f"Error: <code>{db_result['error']}</code>"
                        )
                    
                    send_telegram_message(chat_id, db_text)
                
                # Echo any other message
                else:
                    echo_text = f"📨 You said: <b>{text}</b>\n\nUse /start to test the bot."
                    send_telegram_message(chat_id, echo_text)
            
            # Return success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True}).encode())
            
        except Exception as e:
            # Log error and return 500
            print(f"Error: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
    
    def do_GET(self):
        """Health check endpoint"""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Telegram Bot Webhook is running!')
