import json

import requests


def is_responses_endpoint(endpoint):
    clean = (endpoint or "").rstrip("/").lower()
    return clean.endswith("/v1/responses") or "/v1/responses" in clean


def build_payload(endpoint, model, system_prompt, user_input, stream, max_tokens=None, temperature=None, top_p=None):
    if is_responses_endpoint(endpoint):
        payload = {
            "model": model,
            "instructions": system_prompt,
            "input": user_input,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_output_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        return payload

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        "stream": stream,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    return payload


def extract_full_text(data):
    if not isinstance(data, dict):
        return ""

    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()

    if isinstance(data.get("response"), str):
        return data["response"].strip()

    if isinstance(data.get("content"), str):
        return data["content"].strip()

    message = data.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
            if isinstance(choice.get("text"), str):
                return choice["text"].strip()
            delta = choice.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"].strip()
            if isinstance(delta, str):
                return delta.strip()

    output = data.get("output")
    if isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, dict):
                for key in ["text", "content", "delta"]:
                    if isinstance(item.get(key), str):
                        parts.append(item[key])
                content = item.get("content")
                if isinstance(content, list):
                    for sub in content:
                        if isinstance(sub, dict):
                            if isinstance(sub.get("text"), str):
                                parts.append(sub["text"])
                            elif isinstance(sub.get("content"), str):
                                parts.append(sub["content"])
                            elif isinstance(sub.get("delta"), str):
                                parts.append(sub["delta"])
        if parts:
            return "".join(parts).strip()

    return ""


def extract_stream_text(data):
    if not isinstance(data, dict):
        return ""

    if data.get("type") == "response.output_text.delta" and isinstance(data.get("delta"), str):
        return data["delta"]

    if isinstance(data.get("delta"), str):
        return data["delta"]

    if isinstance(data.get("content"), str):
        return data["content"]

    if isinstance(data.get("text"), str):
        return data["text"]

    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            delta = choice.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]
            if isinstance(delta, str):
                return delta
            if isinstance(choice.get("text"), str):
                return choice["text"]

    output = data.get("output")
    if isinstance(output, str):
        return output

    if isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, dict):
                for key in ["delta", "content", "text"]:
                    if isinstance(item.get(key), str):
                        parts.append(item[key])
                content = item.get("content")
                if isinstance(content, list):
                    for sub in content:
                        if isinstance(sub, dict):
                            for key in ["text", "content", "delta"]:
                                if isinstance(sub.get(key), str):
                                    parts.append(sub[key])
        if parts:
            return "".join(parts)

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
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = build_payload(
        endpoint=endpoint,
        model=model,
        system_prompt=system_prompt,
        user_input=user_input,
        stream=True,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )

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
        payload = build_payload(
            endpoint=endpoint,
            model=model,
            system_prompt=system_prompt,
            user_input=user_input,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        if response.status_code >= 400:
            body = response.text.strip()
            raise requests.HTTPError(f"{response.status_code} {response.reason}: {body}", response=response)
        text = extract_full_text(response.json())
        if text:
            yield text