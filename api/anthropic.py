import json

import requests


def extract_full_text(data):
    if not isinstance(data, dict):
        return ""

    if data.get("type") == "message":
        content = data.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            if parts:
                return "".join(parts).strip()

    if isinstance(data.get("content"), str):
        return data["content"].strip()

    return ""


def extract_stream_text(data):
    if not isinstance(data, dict):
        return ""

    if data.get("type") == "content_block_delta":
        delta = data.get("delta")
        if isinstance(delta, dict) and delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
            return delta["text"]

    if data.get("type") == "message_delta":
        delta = data.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("text"), str):
            return delta["text"]

    if isinstance(data.get("delta"), str):
        return data["delta"]

    if isinstance(data.get("text"), str):
        return data["text"]

    return ""


def iter_sse_events(response):
    event_name = None
    data_lines = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue

        line = raw_line.rstrip("\r")

        if line == "":
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue

        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue

    if data_lines:
        yield event_name, "\n".join(data_lines)


def stream_completion(endpoint, api_key, model, system_prompt, user_input, timeout, stop_event, max_tokens=None, temperature=None, top_p=None):
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model": model,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_input}
        ],
        "stream": True,
        "max_tokens": max_tokens if max_tokens is not None else 1024,
    }

    if temperature is not None:
        payload["temperature"] = temperature

    if top_p is not None:
        payload["top_p"] = top_p

    received_any = False
    accumulated = ""

    with requests.post(endpoint, headers=headers, json=payload, stream=True, timeout=timeout) as response:
        if response.status_code >= 400:
            body = response.text.strip()
            raise requests.HTTPError(f"{response.status_code} {response.reason}: {body}", response=response)

        for event_name, data_str in iter_sse_events(response):
            if stop_event.is_set():
                return

            if not data_str:
                continue

            if data_str == "[DONE]":
                return

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            piece = extract_stream_text(data)
            if not piece:
                continue

            if accumulated and piece.startswith(accumulated):
                delta = piece[len(accumulated):]
                accumulated = piece
            else:
                delta = piece
                accumulated += piece

            if delta:
                received_any = True
                yield delta

    if not received_any and not stop_event.is_set():
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_input}
            ],
            "stream": False,
            "max_tokens": max_tokens if max_tokens is not None else 1024,
        }

        if temperature is not None:
            payload["temperature"] = temperature

        if top_p is not None:
            payload["top_p"] = top_p

        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        if response.status_code >= 400:
            body = response.text.strip()
            raise requests.HTTPError(f"{response.status_code} {response.reason}: {body}", response=response)
        text = extract_full_text(response.json())
        if text:
            yield text