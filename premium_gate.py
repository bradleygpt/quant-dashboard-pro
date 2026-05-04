"""
Premium Gating Module
=====================

Handles the basic vs premium tier distinction for the dashboard.

Phase 1 (current, no monetization):
- All content visible to everyone
- Premium tabs marked with ✨ prefix
- Premium sections show "Premium feature - free during beta" banner
- Anonymous users see sign-up CTA in sidebar
- Signed-up users (basic OR premium) see no banner
- One-click "Activate Premium (free during beta)" button

Phase 2 (future, paid):
- Same architecture, just swap activate_premium() to route to Stripe checkout
- Banner becomes a real wall: "Premium feature - upgrade to access"

Tier mapping:
- free = Basic user
- beta = Premium user (free during beta)
- pro = Future paid premium tier
- admin = You

Premium status: tier in ['beta', 'pro', 'admin']
"""

import streamlit as st

try:
    from auth import (
        is_logged_in,
        get_user_tier,
        get_current_user,
        get_current_profile,
        sign_up,
        sign_in,
        sign_out,
        is_auth_configured,
    )
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False


def is_premium():
    """Return True if current user has premium access (beta/pro/admin tier)."""
    if not AUTH_AVAILABLE or not is_logged_in():
        return False
    tier = get_user_tier()
    return tier in ("beta", "pro", "admin")


def premium_label(tab_name):
    """Add ✨ prefix to a tab name to mark it as premium.

    Used in tab definitions: tabs = st.tabs([..., premium_label('Swing Trader'), ...])
    """
    return f"✨ {tab_name}"


def premium_banner(feature_name="this feature"):
    """Render a 'Premium feature - free during beta' banner.

    Shown above premium content when user is NOT premium.
    Returns nothing (the banner is decorative; content always renders).

    Use at the top of premium tab content:
        with tab_swing:
            premium_banner("Swing Trader")
            # ... rest of swing trader code (always renders)
    """
    if is_premium():
        return  # No banner for premium users

    if not AUTH_AVAILABLE or not is_auth_configured():
        # Auth not configured - show simpler message
        st.info(
            f"✨ **{feature_name}** is a Premium feature. "
            "All content is accessible during beta."
        )
        return

    if not is_logged_in():
        st.info(
            f"✨ **{feature_name}** is a Premium feature. "
            "All content is accessible during the public beta. "
            "Sign up in the sidebar to track your usage and activate Premium for free."
        )
    else:
        # Logged in but on basic tier
        st.info(
            f"✨ **{feature_name}** is a Premium feature. "
            "Free during beta — click below to activate."
        )
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("✨ Activate Premium", key=f"activate_{feature_name}", type="primary"):
                _activate_premium_for_current_user()
                st.rerun()


def premium_section(feature_name):
    """Context manager-style wrapper for a premium section within a tab.

    Currently identical to premium_banner — same visual treatment.
    Reserved for future where premium SECTIONS may differ from premium TABS.
    """
    premium_banner(feature_name)


def _activate_premium_for_current_user():
    """Upgrade current user from free → beta tier (Phase 1: free activation)."""
    if not AUTH_AVAILABLE or not is_logged_in():
        return False

    user = get_current_user()
    if not user:
        return False

    user_id = user.get("id")
    if not user_id:
        return False

    try:
        from auth import get_supabase
        sb = get_supabase()
        if sb is None:
            return False
        sb.table("user_profiles").update({"tier": "beta"}).eq("id", user_id).execute()
        # Refresh local cache
        from auth import refresh_profile
        refresh_profile()
        st.success("✨ Premium activated! All Premium features unlocked.")
        return True
    except Exception as e:
        st.error(f"Could not activate Premium: {str(e)[:100]}")
        return False


def render_auth_sidebar():
    """Render auth UI in the sidebar.

    - Anonymous: shows sign in / sign up buttons
    - Signed in basic: shows account info + 'Activate Premium' button
    - Signed in premium: shows account info + 'Premium' badge

    Use this in app.py at the top of the sidebar.
    """
    if not AUTH_AVAILABLE:
        st.sidebar.caption("Auth module not loaded")
        return

    if not is_auth_configured():
        st.sidebar.caption("Auth not configured")
        return

    if is_logged_in():
        _render_logged_in_sidebar()
    else:
        _render_anonymous_sidebar()


def _render_anonymous_sidebar():
    """Sidebar for users who haven't signed in."""
    st.sidebar.markdown("### 👤 Account")
    st.sidebar.caption(
        "Sign up to track usage and unlock Premium features (free during beta)."
    )

    mode = st.sidebar.radio(
        "Choose:",
        options=["Sign In", "Sign Up"],
        horizontal=True,
        label_visibility="collapsed",
        key="sidebar_auth_mode",
    )

    email = st.sidebar.text_input(
        "Email",
        key="sidebar_auth_email",
        placeholder="you@example.com"
    )
    password = st.sidebar.text_input(
        "Password",
        type="password",
        key="sidebar_auth_password",
        placeholder="••••••••",
    )

    if mode == "Sign Up":
        display_name = st.sidebar.text_input(
            "Display name (optional)",
            key="sidebar_auth_displayname",
            placeholder="Your name",
        )
        if st.sidebar.button("Create Account", type="primary", use_container_width=True):
            if email and password and len(password) >= 6:
                with st.sidebar:
                    with st.spinner("Creating account..."):
                        result = sign_up(email, password, display_name=display_name)
                if result.get("success"):
                    st.sidebar.success("✓ Account created!")
                    st.rerun()
                else:
                    st.sidebar.error(result.get("error", "Sign up failed"))
            else:
                st.sidebar.warning("Enter email and password (6+ chars)")
    else:
        if st.sidebar.button("Sign In", type="primary", use_container_width=True):
            if email and password:
                with st.sidebar:
                    with st.spinner("Signing in..."):
                        result = sign_in(email, password)
                if result.get("success"):
                    st.sidebar.success("✓ Signed in!")
                    st.rerun()
                else:
                    st.sidebar.error(result.get("error", "Invalid credentials"))
            else:
                st.sidebar.warning("Enter email and password")


def _render_logged_in_sidebar():
    """Sidebar for signed-in users."""
    user = get_current_user()
    profile = get_current_profile() or {}
    tier = profile.get("tier", "free")
    display = profile.get("display_name") or user.get("email", "").split("@")[0]
    email = user.get("email", "")

    # Tier visual treatment
    tier_display_map = {
        "free": ("Basic", "#888888"),
        "beta": ("✨ Premium", "#00A3FF"),
        "pro": ("⭐ Pro", "#00D4AA"),
        "admin": ("🛠️ Admin", "#FF6B6B"),
    }
    tier_label, tier_color = tier_display_map.get(tier, ("Basic", "#888"))

    st.sidebar.markdown(
        f'<div style="padding:12px;background:#1A1F2E;border-radius:8px;margin-bottom:10px;border:1px solid {tier_color}33;">'
        f'<div style="color:#fff;font-weight:600;font-size:1em;">{display}</div>'
        f'<div style="color:#aaa;font-size:0.8em;margin-bottom:6px;">{email}</div>'
        f'<div><span style="background:{tier_color};color:#fff;padding:3px 10px;border-radius:4px;font-size:0.78em;font-weight:600;">{tier_label}</span></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # If user is on free tier, offer Premium activation
    if tier == "free":
        st.sidebar.caption("Activate Premium to unlock advanced features (free during beta)")
        if st.sidebar.button("✨ Activate Premium", use_container_width=True, type="primary"):
            _activate_premium_for_current_user()
            st.rerun()

    if st.sidebar.button("Sign Out", use_container_width=True):
        sign_out()
        st.rerun()


# Convenience export for app.py
__all__ = [
    "is_premium",
    "premium_label",
    "premium_banner",
    "premium_section",
    "render_auth_sidebar",
]
