from __future__ import annotations

from urllib.parse import urlsplit


def normalize_site_base_url(value: str) -> str:
    raw_url = value.strip()
    if not raw_url:
        raise ValueError("站点地址不能为空。")

    if raw_url.startswith("//"):
        candidate = f"https:{raw_url}"
    elif "://" in raw_url:
        candidate = raw_url
    else:
        if raw_url.lower().startswith(("http:/", "https:/")):
            raise ValueError("站点地址格式无效。")
        candidate = f"https://{raw_url}"
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError("站点地址格式无效。") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("站点地址仅支持 http 或 https 协议。")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("站点地址缺少有效域名。")
    if any(character.isspace() or character in "/\\?#" for character in hostname):
        raise ValueError("站点地址域名无效。")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("站点地址端口无效。") from exc

    normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    port_suffix = f":{port}" if port is not None else ""
    return f"{scheme}://{normalized_host}{port_suffix}"
