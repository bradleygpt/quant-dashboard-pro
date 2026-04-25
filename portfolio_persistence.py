"""
Portfolio Persistence Module
Saves user portfolios to Supabase, loads on login, supports multiple named portfolios.

Schema (run portfolio_schema.sql in Supabase first):
- portfolios table: id, user_id, name, holdings (jsonb), created_at, updated_at
"""

import json
from datetime import datetime, timezone
import streamlit as st
from auth import get_supabase, get_current_user, is_logged_in


def save_portfolio(name, holdings, portfolio_id=None):
    """
    Save or update a user's portfolio.

    Args:
        name: Portfolio name (e.g. "Main Account")
        holdings: List of dicts with ticker, shares, cost_basis
        portfolio_id: If provided, updates existing. If None, creates new.

    Returns:
        {success: True, portfolio_id: ...} or {error: ...}
    """
    if not is_logged_in():
        return {"error": "Not logged in"}

    sb = get_supabase()
    if not sb:
        return {"error": "Database not configured"}

    user = get_current_user()
    user_id = user["id"]

    # Sanitize holdings (remove None, ensure types)
    clean_holdings = []
    for h in holdings:
        if not h.get("ticker"):
            continue
        clean_holdings.append({
            "ticker": str(h["ticker"]).upper(),
            "shares": float(h.get("shares", 0)),
            "cost_basis": float(h["cost_basis"]) if h.get("cost_basis") is not None else None,
        })

    if not clean_holdings:
        return {"error": "No valid holdings to save"}

    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        if portfolio_id:
            # Update existing
            response = sb.table("portfolios").update({
                "name": name,
                "holdings": clean_holdings,
                "updated_at": now_iso,
            }).eq("id", portfolio_id).eq("user_id", user_id).execute()
            return {"success": True, "portfolio_id": portfolio_id, "updated": True}
        else:
            # Create new
            response = sb.table("portfolios").insert({
                "user_id": user_id,
                "name": name,
                "holdings": clean_holdings,
                "created_at": now_iso,
                "updated_at": now_iso,
            }).execute()
            if response.data and len(response.data) > 0:
                return {"success": True, "portfolio_id": response.data[0]["id"], "created": True}
            return {"error": "Insert returned no data"}
    except Exception as e:
        return {"error": f"Save failed: {str(e)[:200]}"}


def load_portfolios():
    """Load all portfolios for the current user, ordered by most recently updated."""
    if not is_logged_in():
        return []
    sb = get_supabase()
    if not sb:
        return []
    user = get_current_user()
    try:
        response = sb.table("portfolios").select("*").eq("user_id", user["id"]).order("updated_at", desc=True).execute()
        return response.data or []
    except Exception as e:
        return []


def delete_portfolio(portfolio_id):
    """Delete a portfolio."""
    if not is_logged_in():
        return {"error": "Not logged in"}
    sb = get_supabase()
    if not sb:
        return {"error": "Database not configured"}
    user = get_current_user()
    try:
        sb.table("portfolios").delete().eq("id", portfolio_id).eq("user_id", user["id"]).execute()
        return {"success": True}
    except Exception as e:
        return {"error": f"Delete failed: {str(e)[:200]}"}


def get_portfolio_by_id(portfolio_id):
    """Load a specific portfolio by ID."""
    if not is_logged_in():
        return None
    sb = get_supabase()
    if not sb:
        return None
    user = get_current_user()
    try:
        response = sb.table("portfolios").select("*").eq("id", portfolio_id).eq("user_id", user["id"]).limit(1).execute()
        if response.data:
            return response.data[0]
    except Exception:
        pass
    return None
