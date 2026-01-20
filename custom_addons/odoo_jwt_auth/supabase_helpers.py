from ./controllers/supabase_client import supabase

# --- Get Supabase Auth user UUID by email ---
def supabase_get_user_by_email(email):  # rename it
    users = supabase.auth.admin.list_users(per_page=1000)
    for u in users.users:
        if u.email and u.email.lower() == email.lower():
            return u
    return None


# --- Get profile by user_id ---
def supabase_get_profile_by_user_id(user_id):
    res = (
        supabase
        .from_("profiles")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None

