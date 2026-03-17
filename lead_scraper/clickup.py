"""
ClickUp Integration — sync leads with ClickUp list, dedup, create tasks.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


CLICKUP_API_KEY = _secret("CLICKUP_API_KEY")
CLICKUP_BASE = "https://api.clickup.com/api/v2"


def _headers():
    return {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}


def get_workspaces() -> list:
    """Get all ClickUp workspaces (teams)."""
    resp = requests.get(f"{CLICKUP_BASE}/team", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("teams", [])


def get_spaces(team_id: str) -> list:
    """Get all spaces in a workspace."""
    resp = requests.get(f"{CLICKUP_BASE}/team/{team_id}/space", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("spaces", [])


def get_folders(space_id: str) -> list:
    """Get all folders in a space."""
    resp = requests.get(f"{CLICKUP_BASE}/space/{space_id}/folder", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("folders", [])


def get_lists(folder_id: str = None, space_id: str = None) -> list:
    """Get lists from a folder or directly from a space (folderless lists)."""
    if folder_id:
        resp = requests.get(f"{CLICKUP_BASE}/folder/{folder_id}/list", headers=_headers(), timeout=15)
    elif space_id:
        resp = requests.get(f"{CLICKUP_BASE}/space/{space_id}/list", headers=_headers(), timeout=15)
    else:
        return []
    resp.raise_for_status()
    return resp.json().get("lists", [])


def get_tasks(list_id: str, page: int = 0) -> list:
    """Get all tasks from a ClickUp list (paginated)."""
    all_tasks = []
    while True:
        resp = requests.get(
            f"{CLICKUP_BASE}/list/{list_id}/task",
            headers=_headers(),
            params={"page": page, "include_closed": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        tasks = resp.json().get("tasks", [])
        if not tasks:
            break
        all_tasks.extend(tasks)
        page += 1
        if len(tasks) < 100:  # ClickUp default page size
            break
    return all_tasks


def get_custom_fields(list_id: str) -> list:
    """Get custom fields for a ClickUp list."""
    resp = requests.get(f"{CLICKUP_BASE}/list/{list_id}/field", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("fields", [])


def _extract_existing_contacts(tasks: list, fields: list) -> dict:
    """Extract existing contact data from ClickUp tasks for dedup.

    Returns dict mapping lowercase name → task data.
    Also builds email set for email-based dedup.
    """
    field_map = {f["id"]: f["name"].lower() for f in fields}

    contacts = {}
    emails_seen = set()

    for task in tasks:
        name = task.get("name", "").strip().lower()
        email = ""

        # Check custom fields for email
        for cf in task.get("custom_fields", []):
            field_name = field_map.get(cf["id"], "")
            value = cf.get("value", "")
            if value and "email" in field_name:
                email = str(value).lower()

        if name:
            contacts[name] = task
        if email:
            emails_seen.add(email)

    return {"by_name": contacts, "emails": emails_seen}


def dedup_leads(leads: list, list_id: str) -> dict:
    """Check leads against existing ClickUp tasks. Returns new and duplicate leads."""
    tasks = get_tasks(list_id)
    fields = get_custom_fields(list_id)
    existing = _extract_existing_contacts(tasks, fields)

    new_leads = []
    duplicates = []

    for lead in leads:
        name_lower = lead["name"].strip().lower()
        email_lower = (lead.get("email") or "").strip().lower()

        is_dup = False

        # Check by name (fuzzy: check if either contains the other)
        for existing_name in existing["by_name"]:
            if name_lower in existing_name or existing_name in name_lower:
                is_dup = True
                break

        # Check by email
        if not is_dup and email_lower and email_lower in existing["emails"]:
            is_dup = True

        if is_dup:
            duplicates.append(lead)
        else:
            new_leads.append(lead)

    return {"new": new_leads, "duplicates": duplicates, "total_existing": len(tasks)}


def create_task(list_id: str, lead: dict, custom_field_mapping: dict = None) -> dict:
    """Create a ClickUp task from a lead.

    custom_field_mapping: dict mapping field names to field IDs, e.g.:
        {"email": "abc123", "phone": "def456", "website": "ghi789"}
    """
    payload = {
        "name": lead["name"],
        "description": (
            f"**Kontakt aus Lead Scraper**\n\n"
            f"- Email: {lead.get('email', '—')}\n"
            f"- Telefon: {lead.get('phone', '—')}\n"
            f"- Website: {lead.get('website', '—')}\n"
            f"- Adresse: {lead.get('address', '—')}\n"
            f"- Quelle: {lead.get('source', '—')}\n"
            f"- Suchbegriff: {lead.get('search_term', '—')}"
        ),
        "status": "to do",
    }

    # Set custom fields if mapping provided
    if custom_field_mapping:
        custom_fields = []
        for field_name, field_id in custom_field_mapping.items():
            value = lead.get(field_name, "")
            if value:
                custom_fields.append({"id": field_id, "value": value})
        if custom_fields:
            payload["custom_fields"] = custom_fields

    resp = requests.post(
        f"{CLICKUP_BASE}/list/{list_id}/task",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def push_leads_to_clickup(leads: list, list_id: str,
                           custom_field_mapping: dict = None) -> dict:
    """Push multiple leads to ClickUp. Returns success/failure counts."""
    created = 0
    failed = 0
    errors = []

    for lead in leads:
        try:
            create_task(list_id, lead, custom_field_mapping)
            created += 1
        except Exception as e:
            failed += 1
            errors.append(f"{lead['name']}: {e}")

    return {"created": created, "failed": failed, "errors": errors}


def auto_detect_field_mapping(list_id: str) -> dict:
    """Auto-detect custom field mapping by matching field names."""
    fields = get_custom_fields(list_id)

    mapping = {}
    for field in fields:
        name_lower = field["name"].lower()
        field_id = field["id"]

        if "email" in name_lower or "e-mail" in name_lower:
            mapping["email"] = field_id
        elif "telefon" in name_lower or "phone" in name_lower or "tel" == name_lower:
            mapping["phone"] = field_id
        elif "website" in name_lower or "url" in name_lower or "webseite" in name_lower:
            mapping["website"] = field_id
        elif "adresse" in name_lower or "address" in name_lower:
            mapping["address"] = field_id

    return mapping
