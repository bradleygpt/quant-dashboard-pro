"""
Authentication Module - Supabase Backend
Handles login, signup, session management, permissions, and usage tracking.

Design:
- Email/password authentication
- Session stored in Streamlit session_state
- User tier system: free / beta / pro / admin
- AI usage tracking per user (for rate limiting)
- All app features gated behind login
"""

import os
import streamlit as st
from datetime import datetime, timedelta, timezone

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


# ── Configuration ──────────────────────────────────────────────────

def _get_secret(name):
    """Get secret from env or Streamlit secrets."""
    val = os.getenv(name)
    if val:
        return val
    try:
        return st.secrets.get(name)
    except Exception:
        return None


SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_ANON_KEY")

# Default AI usage limits per tier
AI_LIMITS = {
    "free": 0,        # No AI
    "beta": 20,       # Beta users get AI during testing
    "pro": 200,       # Pro tier
    "admin": 9999,    # Admin unlimited
}

# Admin email (you)
ADMIN_EMAIL = _get_secret("ADMIN_EMAIL") or "bradley.hartnett@gmail.com"


# ── Supabase Client ─────────────────────────────────────────────────

@st.cache_resource
def get_supabase() -> "Client":
    """Singleton Supabase client."""
    if not SUPABASE_AVAILABLE:
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Supabase connection failed: {e}")
        return None


def is_auth_configured():
    """Check if Supabase is properly configured."""
    return SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY


# ── Session Helpers ─────────────────────────────────────────────────

def _init_session_state():
    defaults = {
        "auth_user": None,
        "auth_session": None,
        "auth_profile": None,
        "auth_checked": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def is_logged_in():
    """Check if a user is currently logged in."""
    _init_session_state()
    return st.session_state.auth_user is not None


def get_current_user():
    """Get the current logged-in user dict."""
    _init_session_state()
    return st.session_state.auth_user


def get_current_profile():
    """Get the current user's profile (tier, usage, etc.)."""
    _init_session_state()
    return st.session_state.auth_profile


def get_user_tier():
    """Get current user's tier. Returns 'free' if not logged in."""
    profile = get_current_profile()
    if not profile:
        return "free"
    return profile.get("tier", "free")


# ── Signup / Login / Logout ─────────────────────────────────────────

def sign_up(email, password, display_name=None):
    """Register a new user."""
    sb = get_supabase()
    if not sb:
        return {"error": "Authentication not configured"}

    try:
        response = sb.auth.sign_up({"email": email, "password": password})
        if response.user:
            # Create profile row
            tier = "admin" if email == ADMIN_EMAIL else "beta"  # Beta during testing phase
            profile_data = {
                "user_id": response.user.id,
                "email": email,
                "display_name": display_name or email.split("@")[0],
                "tier": tier,
                "ai_calls_today": 0,
                "ai_calls_total": 0,
                "last_ai_call_date": datetime.now(timezone.utc).date().isoformat(),
            }
            try:
                sb.table("profiles").insert(profile_data).execute()
            except Exception as pe:
                # Profile table insert may fail but account is created
                pass
            return {"user": response.user, "session": response.session, "message": "Account created. Please log in."}
        return {"error": "Signup failed"}
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "user already" in msg.lower():
            return {"error": "Email already registered. Try logging in."}
        if "password" in msg.lower():
            return {"error": "Password too weak. Use at least 6 characters."}
        return {"error": f"Signup failed: {msg[:200]}"}


def sign_in(email, password):
    """Authenticate a user."""
    sb = get_supabase()
    if not sb:
        return {"error": "Authentication not configured"}

    try:
        response = sb.auth.sign_in_with_password({"email": email, "password": password})
        if response.user and response.session:
            _init_session_state()
            st.session_state.auth_user = {
                "id": response.user.id,
                "email": response.user.email,
            }
            st.session_state.auth_session = {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
            }
            # Load profile
            profile = _load_profile(response.user.id)
            if not profile:
                # Create if missing (legacy users)
                tier = "admin" if response.user.email == ADMIN_EMAIL else "beta"
                profile_data = {
                    "user_id": response.user.id,
                    "email": response.user.email,
                    "display_name": response.user.email.split("@")[0],
                    "tier": tier,
                    "ai_calls_today": 0,
                    "ai_calls_total": 0,
                    "last_ai_call_date": datetime.now(timezone.utc).date().isoformat(),
                }
                try:
                    sb.table("profiles").insert(profile_data).execute()
                    profile = profile_data
                except Exception:
                    profile = {"tier": tier, "ai_calls_today": 0}
            st.session_state.auth_profile = profile
            return {"success": True, "user": response.user}
        return {"error": "Invalid credentials"}
    except Exception as e:
        msg = str(e).lower()
        if "invalid" in msg or "credentials" in msg:
            return {"error": "Invalid email or password"}
        return {"error": f"Login failed: {str(e)[:200]}"}


def sign_out():
    """Log the user out."""
    sb = get_supabase()
    if sb:
        try:
            sb.auth.sign_out()
        except Exception:
            pass
    _init_session_state()
    st.session_state.auth_user = None
    st.session_state.auth_session = None
    st.session_state.auth_profile = None


# ── Profile Management ────────────────────────────────────────────

def _load_profile(user_id):
    """Load a user's profile from Supabase."""
    sb = get_supabase()
    if not sb:
        return None
    try:
        response = sb.table("profiles").select("*").eq("user_id", user_id).limit(1).execute()
        if response.data:
            return response.data[0]
    except Exception:
        pass
    return None


def refresh_profile():
    """Reload the current user's profile."""
    user = get_current_user()
    if user:
        profile = _load_profile(user["id"])
        if profile:
            st.session_state.auth_profile = profile
            return profile
    return None


# ── AI Usage Tracking & Gating ────────────────────────────────────

def can_use_ai():
    """Check if current user can make an AI call."""
    if not is_logged_in():
        return False, "Login required"

    profile = get_current_profile()
    if not profile:
        return False, "Profile not loaded"

    tier = profile.get("tier", "free")
    limit = AI_LIMITS.get(tier, 0)

    if limit == 0:
        return False, f"AI not available on {tier} tier. Upgrade to beta or pro."

    # Reset daily counter if new day
    today = datetime.now(timezone.utc).date().isoformat()
    last_call_date = profile.get("last_ai_call_date", "")
    calls_today = profile.get("ai_calls_today", 0) if last_call_date == today else 0

    if calls_today >= limit:
        return False, f"Daily AI limit reached ({limit}/day for {tier} tier). Resets at UTC midnight."

    return True, f"{calls_today}/{limit} AI calls used today"


def log_ai_call(feature_name="general"):
    """Log an AI call for the current user. Increments counter."""
    sb = get_supabase()
    user = get_current_user()
    if not sb or not user:
        return

    try:
        today = datetime.now(timezone.utc).date().isoformat()
        profile = get_current_profile() or {}
        last_call_date = profile.get("last_ai_call_date", "")

        # Reset counter if new day
        if last_call_date != today:
            calls_today = 1
        else:
            calls_today = profile.get("ai_calls_today", 0) + 1

        calls_total = profile.get("ai_calls_total", 0) + 1

        sb.table("profiles").update({
            "ai_calls_today": calls_today,
            "ai_calls_total": calls_total,
            "last_ai_call_date": today,
        }).eq("user_id", user["id"]).execute()

        # Log event
        try:
            sb.table("ai_usage_log").insert({
                "user_id": user["id"],
                "feature": feature_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass  # Log table optional

        # Update session profile
        if st.session_state.get("auth_profile"):
            st.session_state.auth_profile["ai_calls_today"] = calls_today
            st.session_state.auth_profile["ai_calls_total"] = calls_total
            st.session_state.auth_profile["last_ai_call_date"] = today
    except Exception as e:
        pass  # Silent fail on logging


# ── UI Components ─────────────────────────────────────────────────

def render_login_page():
    """Render the login/signup page. Call this instead of the app when not logged in."""
    st.markdown(
        '<div style="text-align:center;padding:40px 0 20px 0;">'
        '<h1 style="background:linear-gradient(90deg,#00D4AA,#00A3FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:2.5em;margin:0;">Quant Strategy Dashboard Pro</h1>'
        '<p style="color:#888;font-size:1.1em;margin-top:8px;">Sector-relative scoring, AI research, doppelganger analysis, portfolio optimization.</p>'
        '</div>',
        unsafe_allow_html=True
    )

    if not is_auth_configured():
        st.error("Authentication is not configured. Contact the administrator.")
        st.caption("Admin: Set SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit secrets.")
        return

    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                if not email or not password:
                    st.error("Please enter email and password.")
                else:
                    with st.spinner("Logging in..."):
                        result = sign_in(email, password)
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success("Logged in!")
                        st.rerun()

    with tab_signup:
        with st.form("signup_form"):
            email_s = st.text_input("Email", key="signup_email", placeholder="you@example.com")
            display_name = st.text_input("Display Name (optional)", key="signup_display")
            password_s = st.text_input("Password (minimum 6 characters)", type="password", key="signup_password")
            password_confirm = st.text_input("Confirm Password", type="password", key="signup_confirm")
            submitted_s = st.form_submit_button("Create Account", use_container_width=True)
            if submitted_s:
                if not email_s or not password_s:
                    st.error("Please enter email and password.")
                elif password_s != password_confirm:
                    st.error("Passwords do not match.")
                elif len(password_s) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    with st.spinner("Creating account..."):
                        result = sign_up(email_s, password_s, display_name or None)
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(result.get("message", "Account created!"))
                        st.info("Please log in with your new credentials.")

    st.markdown("---")
    st.caption("By signing up, you agree that this tool is for informational purposes only and does not constitute financial advice.")


def render_user_sidebar():
    """Render user info in sidebar when logged in."""
    if not is_logged_in():
        return
    user = get_current_user()
    profile = get_current_profile() or {}
    tier = profile.get("tier", "free")
    display = profile.get("display_name") or user.get("email", "").split("@")[0]

    tier_colors = {"free": "#888", "beta": "#00A3FF", "pro": "#00D4AA", "admin": "#FF6B6B"}
    tier_color = tier_colors.get(tier, "#888")

    st.sidebar.markdown(
        f'<div style="padding:12px;background:#1A1F2E;border-radius:6px;margin-bottom:10px;">'
        f'<div style="color:#fff;font-weight:600;">{display}</div>'
        f'<div style="color:#aaa;font-size:0.85em;">{user.get("email", "")}</div>'
        f'<div style="margin-top:6px;"><span style="background:{tier_color};color:#fff;padding:2px 10px;border-radius:4px;font-size:0.8em;font-weight:600;text-transform:uppercase;">{tier}</span></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # AI usage display
    limit = AI_LIMITS.get(tier, 0)
    if limit > 0:
        today = datetime.now(timezone.utc).date().isoformat()
        last_call_date = profile.get("last_ai_call_date", "")
        calls_today = profile.get("ai_calls_today", 0) if last_call_date == today else 0
        pct = (calls_today / limit) * 100 if limit > 0 else 0
        st.sidebar.caption(f"AI usage today: {calls_today}/{limit}")
        st.sidebar.progress(min(1.0, calls_today / limit) if limit > 0 else 0)

    if st.sidebar.button("Logout", use_container_width=True):
        sign_out()
        st.rerun()
