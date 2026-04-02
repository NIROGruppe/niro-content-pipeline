"""
Miro API wrapper — read board items, find free space, create visual elements.
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


MIRO_API_TOKEN = _secret("MIRO_API_TOKEN")
BASE_URL = "https://api.miro.com/v2"


def _headers():
    return {
        "Authorization": f"Bearer {MIRO_API_TOKEN}",
        "Content-Type": "application/json",
    }


def parse_board_id(board_input: str) -> str:
    """Extract board ID from URL or raw ID input."""
    if "miro.com" in board_input:
        # URL format: https://miro.com/app/board/uXjVK1234abcd=/
        parts = board_input.rstrip("/").split("/")
        for i, p in enumerate(parts):
            if p == "board" and i + 1 < len(parts):
                return parts[i + 1]
    return board_input.strip()


def get_board_items(board_id: str) -> list:
    """Get all items on a board to find occupied areas."""
    items = []
    cursor = None
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            f"{BASE_URL}/boards/{board_id}/items",
            headers=_headers(), params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("data", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return items


def find_free_area(items: list, width: int = 2400, height: int = 1800) -> tuple:
    """Find a free area on the board that doesn't overlap with existing items.
    Returns (x, y) for the top-left corner of the free area."""
    if not items:
        return (0, 0)

    # Collect bounding boxes of all items
    occupied = []
    for item in items:
        pos = item.get("position", {})
        geo = item.get("geometry", {})
        x = pos.get("x", 0)
        y = pos.get("y", 0)
        w = geo.get("width", 200)
        h = geo.get("height", 200)
        occupied.append({
            "left": x - w / 2,
            "right": x + w / 2,
            "top": y - h / 2,
            "bottom": y + h / 2,
        })

    if not occupied:
        return (0, 0)

    # Place to the right of all existing content, with padding
    max_right = max(b["right"] for b in occupied)
    min_top = min(b["top"] for b in occupied)

    return (int(max_right + 400), int(min_top))


def create_frame(board_id: str, x: int, y: int, width: int, height: int,
                 title: str) -> dict:
    """Create a frame (container) on the board."""
    resp = requests.post(
        f"{BASE_URL}/boards/{board_id}/frames",
        headers=_headers(),
        json={
            "data": {"title": title, "type": "freeform"},
            "position": {"origin": "center", "x": x + width // 2, "y": y + height // 2},
            "geometry": {"width": width, "height": height},
            "style": {"fillColor": "#f5f5f5"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_shape(board_id: str, x: int, y: int, width: int, height: int,
                 content: str, fill_color: str = "#1a1a2e",
                 text_color: str = "#ffffff", font_size: str = "24",
                 shape: str = "round_rectangle") -> dict:
    """Create a shape with text on the board."""
    resp = requests.post(
        f"{BASE_URL}/boards/{board_id}/shapes",
        headers=_headers(),
        json={
            "data": {"content": content, "shape": shape},
            "position": {"origin": "center", "x": x, "y": y},
            "geometry": {"width": width, "height": height},
            "style": {
                "fillColor": fill_color,
                "fontFamily": "open_sans",
                "fontSize": font_size,
                "textAlign": "center",
                "textAlignVertical": "middle",
                "color": text_color,
                "borderWidth": "0",
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_sticky_note(board_id: str, x: int, y: int,
                       content: str, color: str = "light_yellow",
                       width: int = 300) -> dict:
    """Create a sticky note. Colors: light_yellow, light_green, light_blue,
    light_pink, violet, dark_blue, light_gray, yellow, green, blue, red, black."""
    resp = requests.post(
        f"{BASE_URL}/boards/{board_id}/sticky_notes",
        headers=_headers(),
        json={
            "data": {"content": content, "shape": "square"},
            "position": {"origin": "center", "x": x, "y": y},
            "geometry": {"width": width},
            "style": {"fillColor": color, "textAlign": "left", "textAlignVertical": "top"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_connector(board_id: str, start_id: str, end_id: str,
                     color: str = "#333333") -> dict:
    """Create an arrow connector between two items."""
    resp = requests.post(
        f"{BASE_URL}/boards/{board_id}/connectors",
        headers=_headers(),
        json={
            "startItem": {"id": start_id},
            "endItem": {"id": end_id},
            "style": {
                "strokeColor": color,
                "strokeWidth": "2",
                "startStrokeCap": "none",
                "endStrokeCap": "stealth",
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_text(board_id: str, x: int, y: int, content: str,
                font_size: str = "14", color: str = "#1a1a2e",
                width: int = 400) -> dict:
    """Create a text element on the board."""
    resp = requests.post(
        f"{BASE_URL}/boards/{board_id}/texts",
        headers=_headers(),
        json={
            "data": {"content": content},
            "position": {"origin": "center", "x": x, "y": y},
            "geometry": {"width": width},
            "style": {
                "color": color,
                "fontFamily": "open_sans",
                "fontSize": font_size,
                "textAlign": "left",
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
