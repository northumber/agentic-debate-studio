# Agentic Debate Studio

A desktop debate interface built with Python and Tkinter for running structured multi-agent conversations across different LLM providers.

It lets multiple agents debate a question turn by turn, streams the conversation live, and generates a final synthesis at the end. The app supports LM Studio, OpenAI-compatible endpoints, and Anthropic through separate API adapters.

## Features

- Modern dark grayscale UI
- Live streamed debate view
- Final synthesis panel
- Preset-based multi-agent personalities
- Separate provider adapters in the `api` folder
- Supports:
  - LM Studio legacy
  - OpenAI-compatible chat completions
  - OpenAI-compatible responses endpoints
  - Anthropic messages API
- Configurable:
  - endpoint
  - provider
  - model
  - timeout
  - rounds
  - max tokens
  - temperature
  - top p
  - API key

## Project Structure

```text
.
├── agentic_gui.py
├── config.txt
├── presets
│   └── various_presets.txt
└── api
    ├── __init__.py
    ├── lm_studio.py
    ├── openai.py
    └── anthropic.py
```

## Requirements

- Python 3.10+
- `requests`

Install dependencies:

```bash
pip install requests
```

## Run

```bash
python agentic_gui.py
```

## Configuration

The app reads settings from `config.txt`.

Example:

```text
provider=auto
endpoint=http://localhost:1234/v1/chat/completions
model=mistral-small-3.2-24b-instruct-2506
timeout=300
rounds=3
api_key=
max_tokens=4096
temperature=0.7
top_p=1.0
```

## Provider Modes

### Auto

`provider=auto` selects the adapter based on the endpoint.

Detection rules:

- `.../api/v1/chat` → LM Studio legacy
- `.../v1/messages` → Anthropic
- anything else → OpenAI-compatible

### LM Studio Legacy

Use this if your LM Studio server exposes:

```text
http://localhost:1234/api/v1/chat
```

Config:

```text
provider=lm_studio
endpoint=http://localhost:1234/api/v1/chat
```

Important:

- this legacy endpoint does **not** accept `max_tokens`
- advanced generation settings are intentionally not sent there

### LM Studio OpenAI-Compatible

Recommended for LM Studio.

Config:

```text
provider=openai
endpoint=http://localhost:1234/v1/chat/completions
```

or:

```text
provider=auto
endpoint=http://localhost:1234/v1/chat/completions
```

This mode supports:

- `max_tokens`
- `temperature`
- `top_p`

### OpenAI-Compatible Chat Completions

Use with providers that expose:

```text
https://your-provider.com/v1/chat/completions
```

Config:

```text
provider=openai
endpoint=https://your-provider.com/v1/chat/completions
model=your-model
api_key=your-key
```

### OpenAI-Compatible Responses API

If your provider exposes:

```text
https://your-provider.com/v1/responses
```

Use:

```text
provider=openai
endpoint=https://your-provider.com/v1/responses
model=your-model
api_key=your-key
```

### Anthropic

Use:

```text
provider=anthropic
endpoint=https://api.anthropic.com/v1/messages
model=claude-sonnet-4-20250514
api_key=your-key
```

Anthropic requests include:

- `x-api-key`
- `anthropic-version`
- `max_tokens`

## Presets

Presets live in the `presets` folder and define the debate agents and prompts.

Example preset:

```text
[meta]
name=Two Philosophers
description=Analytic Philosopher 1 vs existential Philosopher 2 with final synthesis.

[agent1]
name=Philosopher 1
system<<END
You are Philosopher 1. Your personality is analytic, skeptical, rational, precise, and systematic.
END

[agent2]
name=Philosopher 2
system<<END
You are Philosopher 2. Your personality is existential, humanistic, intuitive, imaginative, and dialectical.
END

[prompts]
opening_prompt<<END
Original question:
{question}

You are starting the dialogue. State your position clearly and defend it. End by asking {other_name} one pointed philosophical question.
END

reply_prompt<<END
Original question:
{question}

Dialogue so far:
{transcript}

Continue as {name}. Respond directly to {other_name}'s latest claims. Strengthen your own position. End by asking {other_name} one pointed philosophical question.
END

synthesis_system<<END
You are a synthesis agent. Read the full exchange and produce:
1. The strongest point made by Philosopher 1
2. The strongest point made by Philosopher 2
3. The central disagreement
4. A synthesized final answer to the original question
END

synthesis_prompt<<END
Original question:
{question}

Full dialogue:
{transcript}
END
```

## How It Works

1. The app loads the selected preset
2. Each agent takes turns responding to the same question
3. The conversation is streamed live into the debate panel
4. After the final round, a synthesis agent produces a final summary

## UI Notes

The interface includes:

- provider selector
- endpoint field
- model field
- timeout
- rounds
- max tokens
- temperature
- top p
- API key
- preset selector
- question editor
- live debate panel
- synthesis panel

## Troubleshooting

### 400 Bad Request: `Unrecognized key(s) in object: 'max_tokens'`

This usually happens when using LM Studio legacy:

```text
http://localhost:1234/api/v1/chat
```

That endpoint does not accept `max_tokens`.

Fix options:

- use the legacy LM Studio adapter:
  ```text
  provider=lm_studio
  endpoint=http://localhost:1234/api/v1/chat
  ```
- or switch to the OpenAI-compatible LM Studio endpoint:
  ```text
  provider=openai
  endpoint=http://localhost:1234/v1/chat/completions
  ```

### Anthropic request fails

Make sure you have:

- `provider=anthropic`
- a valid `api_key`
- endpoint set to:
  ```text
  https://api.anthropic.com/v1/messages
  ```

### OpenAI-compatible request fails

Check:

- endpoint path is correct
- model name is valid for your provider
- API key is present if required
- use `/v1/chat/completions` or `/v1/responses` depending on the server

### No presets appear

Make sure the `presets` folder exists and contains at least one valid `.txt` preset file.

## Example Configurations

### LM Studio Legacy

```text
provider=lm_studio
endpoint=http://localhost:1234/api/v1/chat
model=mistral-small-3.2-24b-instruct-2506
timeout=300
rounds=3
api_key=
max_tokens=4096
temperature=0.7
top_p=1.0
```

### LM Studio OpenAI-Compatible

```text
provider=openai
endpoint=http://localhost:1234/v1/chat/completions
model=mistral-small-3.2-24b-instruct-2506
timeout=300
rounds=3
api_key=
max_tokens=4096
temperature=0.7
top_p=1.0
```

### OpenAI-Compatible Remote Provider

```text
provider=openai
endpoint=https://api.openai.com/v1/chat/completions
model=gpt-4.1
timeout=300
rounds=3
api_key=your-key
max_tokens=4096
temperature=0.7
top_p=1.0
```

### Anthropic

```text
provider=anthropic
endpoint=https://api.anthropic.com/v1/messages
model=claude-sonnet-4-20250514
timeout=300
rounds=3
api_key=your-key
max_tokens=4096
temperature=0.7
top_p=1.0
```

## Notes

- `rounds` has no artificial maximum in the UI
- LM Studio legacy intentionally ignores advanced generation fields
- provider-specific request formatting is handled in the `api` folder
- errors from the server are surfaced in the UI dialog to help debugging
