import os


DEFAULT_FASTAPI_BASE_URL = os.getenv("GATE_FASTAPI_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_APARTMENT_NO = int(os.getenv("APARTMENT_NO", "1"))
DEFAULT_TIMEOUT = float(os.getenv("GATE_REQUEST_TIMEOUT", "3"))


def build_api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def should_open_gate(check_result: dict) -> bool:
    return bool(check_result.get("gate_open", False))


def check_plate(
        plate: str,
        session=None,
        base_url: str = DEFAULT_FASTAPI_BASE_URL,
        apartment_no: int = DEFAULT_APARTMENT_NO,
        timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    if session is None:
        import requests
        session = requests

    response = session.post(
        build_api_url(base_url, "/api/check-plate"),
        json={
            "plate": plate,
            "apartment_no": apartment_no,
        },
        timeout=timeout,
    )
    data = response.json()
    is_registered = bool(data.get("is_registered", data.get("is_resident", False)))
    gate_open = bool(data.get("gate_open", False))
    return {
        "plate": data.get("plate", plate),
        "apartment_no": data.get("apartment_no", apartment_no),
        "is_resident": bool(data.get("is_resident", is_registered)),
        "is_registered": is_registered,
        "is_resident_vehicle": bool(data.get("is_resident_vehicle", False)),
        "is_visitor": bool(data.get("is_visitor", False)),
        "gate_open": gate_open,
        "reason": data.get("reason", ""),
    }


def save_entry_log(
        plate: str,
        check_result: dict,
        session=None,
        base_url: str = DEFAULT_FASTAPI_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
) -> None:
    if session is None:
        import requests
        session = requests

    session.post(
        build_api_url(base_url, "/api/entry-log"),
        json={
            "c_number": plate,
            "is_resident": bool(check_result.get("is_registered", check_result.get("is_resident", False))),
            "gate_open": should_open_gate(check_result),
        },
        timeout=timeout,
    )
