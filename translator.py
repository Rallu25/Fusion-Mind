import requests


def translate_text(text: str, target_language: str) -> str:
    if not text:
        return ""

    url = "https://api.mymemory.translated.net/get"

    params = {
        "q": text,
        "langpair": f"en|{target_language}"
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(
            f"MyMemory API error {response.status_code}: {response.text}"
        )

    try:
        data = response.json()
    except Exception:
        raise Exception(f"MyMemory returned non-JSON response: {response.text}")

    translated = data.get("responseData", {}).get("translatedText", "")
    if not translated:
        raise Exception(f"Unexpected MyMemory response: {data}")

    return translated