"""
Minimal Telegram Bot for Vercel + Neon Testing
This webhook handles incoming Telegram updates and responds with a test message.
"""

import os
import json
import psycopg2
from http.server import BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

# Environment variables (set in Vercel dashboard)
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()

def send_telegram_message(chat_id, text):
    """Send a message to Telegram chat with error handling"""
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_TOKEN environment variable is not set")
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    data = json.dumps(payload).encode('utf-8')
    
    req = Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    
    try:
        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            return result
    except HTTPError as e:
        error_body = e.read().decode()
        print(f"Telegram API Error {e.code}: {error_body}")
        raise Exception(f"Telegram API returned {e.code}: {error_body}")
    except URLError as e:
        print(f"Network Error: {e.reason}")
        raise Exception(f"Network error: {e.reason}")

def test_database_connection():
    """Test Neon PostgreSQL connection"""
    if not DATABASE_URL:
        return {"success": False, "error": "DATABASE_URL not set"}
    
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=10)
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
            # Check environment variables first
            if not BOT_TOKEN:
                raise ValueError("TELEGRAM_TOKEN is not configured. Check Vercel environment variables.")
            
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            print(f"Received update: {body.decode()[:200]}...")  # Log first 200 chars
            
            update = json.loads(body.decode())
            
            # Extract message data
            if 'message' in update:
                message = update['message']
                chat_id = message['chat']['id']
                text = message.get('text', '')
                user = message.get('from', {})
                username = user.get('username', 'Unknown')
                first_name = user.get('first_name', 'User')
                
                print(f"Processing message from {username}: {text}")
                
                # Handle /start command
                if text == '/start':
                    response_text = (
                        "🏰 <b>Guild Bot Test</b>\n\n"
                        f"✅ Webhook is working!\n"
                        f"👤 User: {first_name} (@{username})\n"
                        f"💬 Chat ID: <code>{chat_id}</code>\n\n"
                        "Testing database connection..."
                    )
                    send_telegram_message(chat_id, response_text)
                    
                    # Test database
                    db_result = test_database_connection()
                    
                    if db_result['success']:
                        db_text = (
                            "✅ <b>Database Connected!</b>\n\n"
                            f"<code>{db_result['version'][:80]}...</code>\n\n"
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
                    echo_text = (
                        f"📨 You said: <b>{text}</b>\n\n"
                        f"Use /start to test the bot.\n\n"
                        f"<i>Bot token is configured correctly!</i>"
                    )
                    send_telegram_message(chat_id, echo_text)
            
            # Return success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True}).encode())
            
        except ValueError as e:
            # Configuration error
            print(f"Configuration Error: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {
                'error': 'Configuration Error',
                'message': str(e),
                'hint': 'Check Vercel Environment Variables'
            }
            self.wfile.write(json.dumps(error_response).encode())
            
        except Exception as e:
            # General error
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {
                'error': 'Internal Server Error',
                'message': str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_GET(self):
        """Health check endpoint"""
        status = {
            'status': 'running',
            'bot_token_configured': bool(BOT_TOKEN),
            'database_configured': bool(DATABASE_URL),
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status, indent=2).encode())
