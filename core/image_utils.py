"""
Sniffing del content-type di un'immagine dai magic byte — estratto da
`ui/views/maps_view.py::_data_uri()` (Multiplayer passo 8, §6.4) perché
serve anche a `network/host_server.py::WorldHostServer.handle_map_image()`
per la rotta `GET /map/<id>/image`, la prima rotta non-JSON del progetto:
un solo punto che sa riconoscere JPEG/PNG/GIF, non due copie della stessa
logica destinate a divergere.
"""

from __future__ import annotations


def sniff_mime(data: bytes) -> str:
    """Riconosce JPEG/PNG/GIF dai primi byte; JPEG come ripiego (stesso
    comportamento di sempre in `_data_uri()`, mai un tipo generico che i
    browser/Flet potrebbero rifiutare)."""
    try:
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:4] == b"GIF8":
            return "image/gif"
    except Exception:
        pass
    return "image/jpeg"
