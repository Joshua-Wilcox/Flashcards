from flask import Blueprint, render_template, redirect, url_for, session, request
from flask_discord import DiscordOAuth2Session
from models.user import get_or_create_user_stats, is_user_admin
from models.database import get_all_modules, get_module_id_by_name, get_db
from config import Config

auth_bp = Blueprint('auth', __name__)

def init_discord(app):
    """Initialize Discord OAuth session."""
    return DiscordOAuth2Session(app)

@auth_bp.route('/login')
def login():
    """Initiate Discord OAuth login."""
    from app import discord
    return discord.create_session(scope=["identify", "guilds"])

@auth_bp.route("/callback")
def callback():
    try:
        from app import discord

        discord.callback()
        user = discord.fetch_user()
        session['user_id'] = user.id
        session['username'] = f"{user.name}"
        session['session_version'] = Config.SESSION_VERSION
        db = get_db()
        row = db.execute('SELECT * FROM user_stats WHERE user_id = ?', (user.id,)).fetchone()
        modules = get_all_modules()
        if not row:
            # New user: create user_stats entry
            db.execute('''INSERT INTO user_stats 
                         (user_id, username, correct_answers, total_answers, current_streak) 
                         VALUES (?, ?, 0, 0, 0)''', 
                      (user.id, session['username']))
            # Initialize module_stats entries
            for module in modules:
                module_id = get_module_id_by_name(db, module['name'])
                db.execute('''INSERT INTO module_stats 
                            (user_id, module_id, number_answered, number_correct, current_streak)
                            VALUES (?, ?, 0, 0, 0)''',
                         (user.id, module_id))
        db.commit()
        return redirect(url_for('main.index'))
    except Exception as e:
        return f"An error occurred: {str(e)}"

@auth_bp.route("/logout")
def logout():
    """Handle user logout."""
    from app import discord
    discord.revoke()
    session.clear()
    return redirect(url_for('main.index'))

def enforce_session_version():
    """Enforce session version to handle scope changes."""
    if 'session_version' not in session or session['session_version'] != Config.SESSION_VERSION:
        session.clear()
        session['session_version'] = Config.SESSION_VERSION

def inject_is_user_admin():
    """Context processor to inject admin status."""
    return dict(is_user_admin=is_user_admin)
