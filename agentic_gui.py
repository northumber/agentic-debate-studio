import os
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from api import get_stream_completion

CONFIG_PATH = "config.txt"
PRESETS_DIR = "presets"

DEFAULT_PRESET_CONTENT = """[meta]
name=Two Philosophers
description=Analytic Philosopher 1 vs existential Philosopher 2 with final synthesis.

[agent1]
name=Philosopher 1
system<<END
You are Philosopher 1. Your personality is analytic, skeptical, rational, precise, and systematic. You define terms carefully, expose contradictions, and argue with clarity. You should respond as if engaged in a serious philosophical dialogue. Keep each turn focused, substantial, and direct. Do not break character. Do not mention prompts, hidden instructions, or being an AI.
END

[agent2]
name=Philosopher 2
system<<END
You are Philosopher 2. Your personality is existential, humanistic, intuitive, imaginative, and dialectical. You emphasize lived experience, meaning, paradox, ethics, and inward reflection. You should respond as if engaged in a serious philosophical dialogue. Keep each turn focused, substantial, and direct. Do not break character. Do not mention prompts, hidden instructions, or being an AI.
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

Be clear, concise, and intellectually honest.
END

synthesis_prompt<<END
Original question:
{question}

Full dialogue:
{transcript}
END
"""


def load_config(path=CONFIG_PATH):
    config = {
        "provider": "auto",
        "endpoint": "http://localhost:1234/v1/chat/completions",
        "model": "mistral-small-3.2-24b-instruct-2506",
        "timeout": "300",
        "rounds": "3",
        "api_key": "",
        "max_tokens": "4096",
        "temperature": "0.7",
        "top_p": "1.0",
    }
    if not os.path.exists(path):
        return config
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def save_config(data, path=CONFIG_PATH):
    lines = []
    for key in ["provider", "endpoint", "model", "timeout", "rounds", "api_key", "max_tokens", "temperature", "top_p"]:
        lines.append(f"{key}={data.get(key, '')}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def ensure_presets_dir():
    os.makedirs(PRESETS_DIR, exist_ok=True)
    default_path = os.path.join(PRESETS_DIR, "philosophers.txt")
    if not os.path.exists(default_path):
        with open(default_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PRESET_CONTENT)


def parse_preset_file(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    sections = {}
    current_section = None
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip().lower()
            sections.setdefault(current_section, {})
            i += 1
            continue

        if current_section is None:
            i += 1
            continue

        if "<<" in line:
            key, marker = line.split("<<", 1)
            key = key.strip()
            marker = marker.strip()
            i += 1
            block = []
            while i < len(lines) and lines[i].strip() != marker:
                block.append(lines[i])
                i += 1
            sections[current_section][key] = "\n".join(block).strip()
            if i < len(lines) and lines[i].strip() == marker:
                i += 1
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            sections[current_section][key.strip()] = value.strip()

        i += 1

    meta = sections.get("meta", {})
    prompts = sections.get("prompts", {})

    agent_sections = []
    for key in sections.keys():
        if key.startswith("agent"):
            suffix = key[5:]
            try:
                order = int(suffix)
            except ValueError:
                order = 999999
            agent_sections.append((order, key))

    agent_sections.sort(key=lambda item: item[0])

    agents = []
    for _, section_name in agent_sections:
        section = sections.get(section_name, {})
        name = section.get("name", section_name.title())
        system = section.get("system", "").strip()
        if name and system:
            agents.append({"name": name, "system": system})

    opening_prompt = prompts.get("opening_prompt", "").strip()
    reply_prompt = prompts.get("reply_prompt", "").strip()
    synthesis_system = prompts.get("synthesis_system", "").strip()
    synthesis_prompt = prompts.get("synthesis_prompt", "").strip()

    if len(agents) < 2:
        raise ValueError(f"Preset '{os.path.basename(path)}' must define at least 2 agents.")

    if not opening_prompt or not reply_prompt or not synthesis_system or not synthesis_prompt:
        raise ValueError(f"Preset '{os.path.basename(path)}' is missing one or more prompt blocks.")

    display_name = meta.get("name", os.path.splitext(os.path.basename(path))[0])
    description = meta.get("description", "")

    return display_name, {
        "description": description,
        "agents": agents,
        "opening_prompt": opening_prompt,
        "reply_prompt": reply_prompt,
        "synthesis_system": synthesis_system,
        "synthesis_prompt": synthesis_prompt,
        "path": path,
    }


def load_presets():
    ensure_presets_dir()
    presets = {}

    for filename in sorted(os.listdir(PRESETS_DIR)):
        if not filename.lower().endswith(".txt"):
            continue
        path = os.path.join(PRESETS_DIR, filename)
        try:
            name, preset = parse_preset_file(path)
            presets[name] = preset
        except Exception:
            continue

    if not presets:
        default_path = os.path.join(PRESETS_DIR, "philosophers.txt")
        with open(default_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PRESET_CONTENT)
        name, preset = parse_preset_file(default_path)
        presets[name] = preset

    return presets


def format_transcript(transcript):
    return "\n\n".join(f"{speaker}:\n{text}" for speaker, text in transcript if text.strip())


def build_prompt(preset, question, transcript, agent_index, is_first_turn):
    agents = preset["agents"]
    agent = agents[agent_index]

    if is_first_turn and agent_index == 0:
        other = agents[(agent_index + 1) % len(agents)]
        return preset["opening_prompt"].format(
            question=question,
            name=agent["name"],
            other_name=other["name"],
            transcript=format_transcript(transcript),
        ).strip()

    other = agents[(agent_index - 1) % len(agents)]
    return preset["reply_prompt"].format(
        question=question,
        name=agent["name"],
        other_name=other["name"],
        transcript=format_transcript(transcript),
    ).strip()


def build_synthesis_prompt(preset, question, transcript):
    return preset["synthesis_prompt"].format(
        question=question,
        transcript=format_transcript(transcript),
    ).strip()


def run_debate(endpoint, provider, api_key, model, timeout, rounds, preset_name, presets, question, ui_queue, stop_event, max_tokens=None, temperature=None, top_p=None):
    try:
        preset = presets[preset_name]
        transcript = []
        stream_completion = get_stream_completion(provider, endpoint)

        ui_queue.put(("status", "Running"))
        ui_queue.put(("clear_synthesis", None))

        for cycle in range(rounds):
            for index, agent in enumerate(preset["agents"]):
                if stop_event.is_set():
                    ui_queue.put(("status", "Stopped"))
                    ui_queue.put(("finished", None))
                    return

                prompt = build_prompt(
                    preset=preset,
                    question=question,
                    transcript=transcript,
                    agent_index=index,
                    is_first_turn=(cycle == 0),
                )

                ui_queue.put(("start_turn", agent["name"]))
                parts = []

                for chunk in stream_completion(
                    endpoint=endpoint,
                    api_key=api_key,
                    model=model,
                    system_prompt=agent["system"],
                    user_input=prompt,
                    timeout=timeout,
                    stop_event=stop_event,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                ):
                    if stop_event.is_set():
                        ui_queue.put(("status", "Stopped"))
                        ui_queue.put(("finished", None))
                        return
                    parts.append(chunk)
                    ui_queue.put(("turn_chunk", chunk))

                final_text = "".join(parts).strip()
                transcript.append((agent["name"], final_text))
                ui_queue.put(("end_turn", None))

        if stop_event.is_set():
            ui_queue.put(("status", "Stopped"))
            ui_queue.put(("finished", None))
            return

        synthesis_prompt = build_synthesis_prompt(preset, question, transcript)
        ui_queue.put(("start_synthesis", "Synthesis"))

        for chunk in stream_completion(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            system_prompt=preset["synthesis_system"],
            user_input=synthesis_prompt,
            timeout=timeout,
            stop_event=stop_event,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        ):
            if stop_event.is_set():
                ui_queue.put(("status", "Stopped"))
                ui_queue.put(("finished", None))
                return
            ui_queue.put(("synthesis_chunk", chunk))

        ui_queue.put(("end_synthesis", None))
        ui_queue.put(("status", "Completed"))
        ui_queue.put(("finished", None))

    except Exception as e:
        ui_queue.put(("error", str(e)))
        ui_queue.put(("finished", None))


class AgenticGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Agentic Debate Studio")
        self.geometry("1420x920")
        self.minsize(1180, 780)

        self.colors = {
            "bg": "#090909",
            "panel": "#111111",
            "panel_alt": "#171717",
            "panel_soft": "#1D1D1D",
            "text": "#F5F5F5",
            "muted": "#A3A3A3",
            "border": "#2A2A2A",
            "border_soft": "#202020",
            "primary": "#E7E5E4",
            "primary_hover": "#F5F5F4",
            "primary_text": "#111111",
            "button": "#1E1E1E",
            "button_hover": "#2A2A2A",
            "button_text": "#F5F5F5",
            "danger": "#262626",
            "danger_hover": "#333333",
            "danger_text": "#F5F5F5",
            "selection": "#3A3A3A",
            "code_bg": "#0C0C0C",
        }

        self.config_data = load_config()
        self.presets = load_presets()
        self.ui_queue = queue.Queue()
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.turn_history = []
        self.live_turn_name = ""
        self.live_turn_text = ""
        self.synthesis_started = False
        self.synthesis_buffer = ""
        self.speaker_tags = {}

        preset_names = list(self.presets.keys())
        default_preset = preset_names[0] if preset_names else ""

        self.provider_var = tk.StringVar(value=self.config_data.get("provider", "auto"))
        self.endpoint_var = tk.StringVar(value=self.config_data.get("endpoint", ""))
        self.model_var = tk.StringVar(value=self.config_data.get("model", ""))
        self.timeout_var = tk.StringVar(value=self.config_data.get("timeout", "300"))
        self.rounds_var = tk.StringVar(value=self.config_data.get("rounds", "3"))
        self.api_key_var = tk.StringVar(value=self.config_data.get("api_key", ""))
        self.max_tokens_var = tk.StringVar(value=self.config_data.get("max_tokens", "4096"))
        self.temperature_var = tk.StringVar(value=self.config_data.get("temperature", "0.7"))
        self.top_p_var = tk.StringVar(value=self.config_data.get("top_p", "1.0"))
        self.preset_var = tk.StringVar(value=default_preset)
        self.status_var = tk.StringVar(value="Idle")
        self.description_var = tk.StringVar(value=self.presets.get(default_preset, {}).get("description", ""))

        self._build_ui()
        self.after(50, self.process_ui_queue)

    def _build_ui(self):
        self.configure(bg=self.colors["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure(
            "App.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        )

        style.configure(
            "Primary.TButton",
            background=self.colors["primary"],
            foreground=self.colors["primary_text"],
            borderwidth=0,
            focusthickness=0,
            focuscolor=self.colors["primary"],
            relief="flat",
            padding=(18, 11),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", self.colors["primary_hover"]),
                ("disabled", self.colors["border"]),
            ],
            foreground=[
                ("disabled", self.colors["muted"]),
            ],
        )

        style.configure(
            "Secondary.TButton",
            background=self.colors["button"],
            foreground=self.colors["button_text"],
            borderwidth=0,
            focusthickness=0,
            focuscolor=self.colors["button"],
            relief="flat",
            padding=(16, 11),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("active", self.colors["button_hover"]),
                ("disabled", self.colors["border"]),
            ],
            foreground=[
                ("disabled", self.colors["muted"]),
            ],
        )

        style.configure(
            "Danger.TButton",
            background=self.colors["danger"],
            foreground=self.colors["danger_text"],
            borderwidth=0,
            focusthickness=0,
            focuscolor=self.colors["danger"],
            relief="flat",
            padding=(16, 11),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Danger.TButton",
            background=[
                ("active", self.colors["danger_hover"]),
                ("disabled", self.colors["border"]),
            ],
            foreground=[
                ("disabled", self.colors["muted"]),
            ],
        )

        style.configure(
            "App.TEntry",
            fieldbackground=self.colors["panel_alt"],
            foreground=self.colors["text"],
            background=self.colors["panel_alt"],
            insertcolor=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            relief="flat",
            padding=10,
        )

        style.configure(
            "App.TCombobox",
            fieldbackground=self.colors["panel_alt"],
            background=self.colors["panel_alt"],
            foreground=self.colors["text"],
            arrowcolor=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            relief="flat",
            padding=10,
        )
        style.map(
            "App.TCombobox",
            fieldbackground=[("readonly", self.colors["panel_alt"])],
            foreground=[("readonly", self.colors["text"])],
            background=[("readonly", self.colors["panel_alt"])],
            selectbackground=[("readonly", self.colors["panel_alt"])],
            selectforeground=[("readonly", self.colors["text"])],
        )

        shell = tk.Frame(self, bg=self.colors["bg"])
        shell.pack(fill="both", expand=True, padx=20, pady=20)

        top_card = tk.Frame(
            shell,
            bg=self.colors["panel"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["border_soft"],
        )
        top_card.pack(fill="x")

        top_inner = tk.Frame(top_card, bg=self.colors["panel"])
        top_inner.pack(fill="x", padx=18, pady=18)

        row1 = tk.Frame(top_inner, bg=self.colors["panel"])
        row1.pack(fill="x")

        tk.Label(
            row1,
            text="Provider",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")

        self.provider_combo = ttk.Combobox(
            row1,
            textvariable=self.provider_var,
            values=["auto", "lm_studio", "openai", "anthropic"],
            state="readonly",
            width=16,
            style="App.TCombobox",
        )
        self.provider_combo.pack(side="left", padx=(10, 16))

        tk.Label(
            row1,
            text="Endpoint",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")

        self.endpoint_entry = ttk.Entry(row1, textvariable=self.endpoint_var, style="App.TEntry")
        self.endpoint_entry.pack(side="left", fill="x", expand=True, padx=(10, 16))

        tk.Label(
            row1,
            text="Model",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")

        self.model_entry = ttk.Entry(row1, textvariable=self.model_var, width=28, style="App.TEntry")
        self.model_entry.pack(side="left", padx=(10, 0))

        row2 = tk.Frame(top_inner, bg=self.colors["panel"])
        row2.pack(fill="x", pady=(14, 0))

        tk.Label(
            row2,
            text="Timeout",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.timeout_entry = ttk.Entry(row2, textvariable=self.timeout_var, width=8, style="App.TEntry")
        self.timeout_entry.pack(side="left", padx=(10, 16))

        tk.Label(
            row2,
            text="Rounds",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.rounds_entry = ttk.Entry(row2, textvariable=self.rounds_var, width=8, style="App.TEntry")
        self.rounds_entry.pack(side="left", padx=(10, 16))

        tk.Label(
            row2,
            text="Max Tokens",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.max_tokens_entry = ttk.Entry(row2, textvariable=self.max_tokens_var, width=10, style="App.TEntry")
        self.max_tokens_entry.pack(side="left", padx=(10, 16))

        tk.Label(
            row2,
            text="Temperature",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.temperature_entry = ttk.Entry(row2, textvariable=self.temperature_var, width=8, style="App.TEntry")
        self.temperature_entry.pack(side="left", padx=(10, 16))

        tk.Label(
            row2,
            text="Top P",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.top_p_entry = ttk.Entry(row2, textvariable=self.top_p_var, width=8, style="App.TEntry")
        self.top_p_entry.pack(side="left", padx=(10, 16))

        tk.Label(
            row2,
            text="API Key",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        self.api_key_entry = ttk.Entry(row2, textvariable=self.api_key_var, width=22, style="App.TEntry", show="*")
        self.api_key_entry.pack(side="left", padx=(10, 0))

        row3 = tk.Frame(top_inner, bg=self.colors["panel"])
        row3.pack(fill="x", pady=(14, 0))

        tk.Label(
            row3,
            text="Preset",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")

        self.preset_combo = ttk.Combobox(
            row3,
            textvariable=self.preset_var,
            values=list(self.presets.keys()),
            state="readonly",
            width=30,
            style="App.TCombobox",
        )
        self.preset_combo.pack(side="left", padx=(10, 10))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_change)

        self.reload_presets_button = ttk.Button(
            row3,
            text="Reload Presets",
            command=self.reload_presets,
            style="Secondary.TButton",
        )
        self.reload_presets_button.pack(side="left")

        desc_wrap = tk.Frame(row3, bg=self.colors["panel"])
        desc_wrap.pack(side="left", fill="x", expand=True, padx=(16, 0))

        tk.Label(
            desc_wrap,
            textvariable=self.description_var,
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x")

        question_card = tk.Frame(
            shell,
            bg=self.colors["panel"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["border_soft"],
        )
        question_card.pack(fill="x", pady=(16, 0))

        tk.Label(
            question_card,
            text="Question",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        self.question_text = ScrolledText(
            question_card,
            height=5,
            wrap="word",
            font=("Segoe UI", 11),
            bg=self.colors["panel_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["selection"],
            selectforeground=self.colors["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
            padx=14,
            pady=14,
        )
        self.question_text.pack(fill="x", padx=18, pady=(0, 18))
        self.question_text.insert("1.0", "Is free will real?")

        action_row = tk.Frame(shell, bg=self.colors["bg"])
        action_row.pack(fill="x", pady=(16, 16))

        left_actions = tk.Frame(action_row, bg=self.colors["bg"])
        left_actions.pack(side="left")

        self.start_button = ttk.Button(
            left_actions,
            text="Start Debate",
            command=self.start_debate,
            style="Primary.TButton",
        )
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            left_actions,
            text="Stop",
            command=self.stop_debate,
            state="disabled",
            style="Danger.TButton",
        )
        self.stop_button.pack(side="left", padx=(10, 0))

        self.reload_button = ttk.Button(
            left_actions,
            text="Reload Config",
            command=self.reload_config,
            style="Secondary.TButton",
        )
        self.reload_button.pack(side="left", padx=(10, 0))

        self.save_button = ttk.Button(
            left_actions,
            text="Save Config",
            command=self.save_current_config,
            style="Secondary.TButton",
        )
        self.save_button.pack(side="left", padx=(10, 0))

        status_wrap = tk.Frame(action_row, bg=self.colors["bg"])
        status_wrap.pack(side="right")

        tk.Label(
            status_wrap,
            text="Status",
            bg=self.colors["bg"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(0, 8))

        tk.Label(
            status_wrap,
            textvariable=self.status_var,
            bg=self.colors["bg"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")

        body = tk.PanedWindow(
            shell,
            orient="horizontal",
            bg=self.colors["bg"],
            bd=0,
            sashwidth=8,
            sashrelief="flat",
            relief="flat",
        )
        body.pack(fill="both", expand=True)

        left_card = tk.Frame(
            body,
            bg=self.colors["panel"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["border_soft"],
        )
        right_card = tk.Frame(
            body,
            bg=self.colors["panel"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["border_soft"],
        )

        body.add(left_card, minsize=560)
        body.add(right_card, minsize=360)

        tk.Label(
            left_card,
            text="Live Debate",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        tk.Label(
            right_card,
            text="Synthesis",
            bg=self.colors["panel"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", padx=18, pady=(16, 10))

        self.transcript_text = ScrolledText(
            left_card,
            wrap="word",
            font=("Segoe UI", 11),
            bg=self.colors["panel_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["selection"],
            selectforeground=self.colors["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
            padx=18,
            pady=18,
            spacing1=2,
            spacing2=2,
            spacing3=6,
        )
        self.transcript_text.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.synthesis_text = ScrolledText(
            right_card,
            wrap="word",
            font=("Segoe UI", 11),
            bg=self.colors["panel_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["selection"],
            selectforeground=self.colors["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
            padx=18,
            pady=18,
            spacing1=2,
            spacing2=2,
            spacing3=6,
        )
        self.synthesis_text.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        for widget in (self.transcript_text, self.synthesis_text):
            widget.tag_configure("paragraph", font=("Segoe UI", 11), foreground=self.colors["text"])
            widget.tag_configure("strong", font=("Segoe UI Semibold", 11), foreground="#FFFFFF")
            widget.tag_configure("h1", font=("Segoe UI Semibold", 16), foreground="#FFFFFF", spacing1=10, spacing3=6)
            widget.tag_configure("h2", font=("Segoe UI Semibold", 14), foreground="#F1F1F1", spacing1=8, spacing3=4)
            widget.tag_configure("h3", font=("Segoe UI Semibold", 12), foreground="#E5E5E5", spacing1=6, spacing3=3)
            widget.tag_configure("bullet", font=("Segoe UI", 11), foreground=self.colors["text"], lmargin1=18, lmargin2=38)
            widget.tag_configure("number", font=("Segoe UI Semibold", 11), foreground="#D4D4D4", lmargin1=18, lmargin2=38)
            widget.tag_configure("code_label", font=("Consolas", 10, "bold"), foreground="#CFCFCF", lmargin1=18, lmargin2=18, spacing1=6, spacing3=2)
            widget.tag_configure("code_block", font=("Consolas", 10), foreground="#EAEAEA", background=self.colors["code_bg"], lmargin1=18, lmargin2=18, rmargin=18, spacing1=2, spacing3=8)
            widget.tag_configure("code_inline", font=("Consolas", 10), foreground="#D4D4D4", background=self.colors["code_bg"])
            widget.tag_configure("quote", font=("Segoe UI", 11, "italic"), foreground="#C7C7C7", lmargin1=28, lmargin2=28)
            widget.tag_configure("divider", foreground=self.colors["border"])

        self.synthesis_text.tag_configure("synthesis_title", font=("Segoe UI Semibold", 14), foreground="#FFFFFF", spacing1=6, spacing3=10)
        self.synthesis_text.tag_configure("synthesis_body", font=("Segoe UI", 11), foreground="#E7E7E7")

        self.transcript_text.config(state="disabled")
        self.synthesis_text.config(state="disabled")

    def reload_config(self):
        self.config_data = load_config()
        self.provider_var.set(self.config_data.get("provider", "auto"))
        self.endpoint_var.set(self.config_data.get("endpoint", ""))
        self.model_var.set(self.config_data.get("model", ""))
        self.timeout_var.set(self.config_data.get("timeout", "300"))
        self.rounds_var.set(self.config_data.get("rounds", "3"))
        self.api_key_var.set(self.config_data.get("api_key", ""))
        self.max_tokens_var.set(self.config_data.get("max_tokens", "4096"))
        self.temperature_var.set(self.config_data.get("temperature", "0.7"))
        self.top_p_var.set(self.config_data.get("top_p", "1.0"))
        self.status_var.set("Config reloaded")

    def save_current_config(self):
        data = {
            "provider": self.provider_var.get().strip(),
            "endpoint": self.endpoint_var.get().strip(),
            "model": self.model_var.get().strip(),
            "timeout": self.timeout_var.get().strip(),
            "rounds": self.rounds_var.get().strip(),
            "api_key": self.api_key_var.get().strip(),
            "max_tokens": self.max_tokens_var.get().strip(),
            "temperature": self.temperature_var.get().strip(),
            "top_p": self.top_p_var.get().strip(),
        }
        save_config(data)
        self.status_var.set("Config saved")

    def reload_presets(self):
        self.presets = load_presets()
        names = list(self.presets.keys())
        self.preset_combo["values"] = names
        if names and self.preset_var.get() not in self.presets:
            self.preset_var.set(names[0])
        self.on_preset_change()
        self.status_var.set("Presets reloaded")

    def on_preset_change(self, event=None):
        name = self.preset_var.get()
        self.description_var.set(self.presets.get(name, {}).get("description", ""))

    def _ensure_speaker_tags(self, speaker_name):
        if speaker_name in self.speaker_tags:
            return self.speaker_tags[speaker_name]

        palette = [
            ("#FFFFFF", "#E7E7E7"),
            ("#E5E5E5", "#D6D6D6"),
            ("#D4D4D4", "#C7C7C7"),
            ("#F1F1F1", "#DDDDDD"),
            ("#DBDBDB", "#CFCFCF"),
            ("#CFCFCF", "#C2C2C2"),
        ]

        index = len(self.speaker_tags) % len(palette)
        header_color, body_color = palette[index]
        header_tag = f"speaker_header_{len(self.speaker_tags)}"
        body_tag = f"speaker_body_{len(self.speaker_tags)}"

        self.transcript_text.tag_configure(
            header_tag,
            font=("Segoe UI Semibold", 11),
            foreground=header_color,
            spacing1=14,
            spacing3=4,
        )
        self.transcript_text.tag_configure(
            body_tag,
            font=("Segoe UI", 11),
            foreground=body_color,
            lmargin1=18,
            lmargin2=18,
            spacing1=2,
            spacing3=8,
        )

        self.speaker_tags[speaker_name] = (header_tag, body_tag)
        return self.speaker_tags[speaker_name]

    def _insert_inline(self, widget, text, base_tag):
        pattern = re.compile(r"(\*\*.+?\*\*|`[^`\n]+`)")
        position = 0

        for match in pattern.finditer(text):
            if match.start() > position:
                widget.insert("end", text[position:match.start()], (base_tag,))

            token = match.group(0)
            if token.startswith("**") and token.endswith("**") and len(token) > 4:
                widget.insert("end", token[2:-2], (base_tag, "strong"))
            elif token.startswith("`") and token.endswith("`") and len(token) > 2:
                widget.insert("end", token[1:-1], ("code_inline",))
            else:
                widget.insert("end", token, (base_tag,))

            position = match.end()

        if position < len(text):
            widget.insert("end", text[position:], (base_tag,))

    def _insert_markdown(self, widget, text, base_tag):
        lines = text.split("\n")
        in_code_block = False
        code_lang = ""
        code_lines = []

        for line in lines:
            stripped = line.rstrip("\r")
            compact = stripped.strip()

            if compact.startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    code_lang = compact[3:].strip()
                    code_lines = []
                else:
                    if code_lang:
                        widget.insert("end", f"{code_lang.upper()}\n", ("code_label",))
                    code_text = "\n".join(code_lines).rstrip()
                    if code_text:
                        widget.insert("end", code_text, ("code_block",))
                    widget.insert("end", "\n\n")
                    in_code_block = False
                    code_lang = ""
                    code_lines = []
                continue

            if in_code_block:
                code_lines.append(stripped)
                continue

            if compact == "":
                widget.insert("end", "\n")
                continue

            left = stripped.lstrip()

            if left.startswith("### "):
                self._insert_inline(widget, left[4:], "h3")
                widget.insert("end", "\n")
                continue

            if left.startswith("## "):
                self._insert_inline(widget, left[3:], "h2")
                widget.insert("end", "\n")
                continue

            if left.startswith("# "):
                self._insert_inline(widget, left[2:], "h1")
                widget.insert("end", "\n")
                continue

            if left.startswith("> "):
                self._insert_inline(widget, left[2:], "quote")
                widget.insert("end", "\n")
                continue

            number_match = re.match(r"^(\d+)\.\s+(.*)$", left)
            if number_match:
                widget.insert("end", f"{number_match.group(1)}. ", ("number",))
                self._insert_inline(widget, number_match.group(2), base_tag)
                widget.insert("end", "\n")
                continue

            if left.startswith("- ") or left.startswith("* "):
                widget.insert("end", "• ", ("bullet",))
                self._insert_inline(widget, left[2:], base_tag)
                widget.insert("end", "\n")
                continue

            self._insert_inline(widget, stripped, base_tag)
            widget.insert("end", "\n")

        if in_code_block:
            if code_lang:
                widget.insert("end", f"{code_lang.upper()}\n", ("code_label",))
            code_text = "\n".join(code_lines).rstrip()
            if code_text:
                widget.insert("end", code_text, ("code_block",))
            widget.insert("end", "\n")

    def _render_transcript(self):
        self.transcript_text.config(state="normal")
        self.transcript_text.delete("1.0", "end")

        for speaker, text in self.turn_history:
            header_tag, body_tag = self._ensure_speaker_tags(speaker)
            self.transcript_text.insert("end", f"{speaker}\n", (header_tag,))
            self._insert_markdown(self.transcript_text, text, body_tag)
            self.transcript_text.insert("end", "\n")

        if self.live_turn_name:
            header_tag, body_tag = self._ensure_speaker_tags(self.live_turn_name)
            self.transcript_text.insert("end", f"{self.live_turn_name}\n", (header_tag,))
            self._insert_markdown(self.transcript_text, self.live_turn_text, body_tag)
            self.transcript_text.insert("end", "\n")

        self.transcript_text.see("end")
        self.transcript_text.config(state="disabled")

    def _render_synthesis(self):
        self.synthesis_text.config(state="normal")
        self.synthesis_text.delete("1.0", "end")

        if self.synthesis_started:
            self.synthesis_text.insert("end", "Synthesis\n\n", ("synthesis_title",))
            self._insert_markdown(self.synthesis_text, self.synthesis_buffer, "synthesis_body")

        self.synthesis_text.see("end")
        self.synthesis_text.config(state="disabled")

    def start_debate(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        provider = self.provider_var.get().strip()
        endpoint = self.endpoint_var.get().strip()
        model = self.model_var.get().strip()
        api_key = self.api_key_var.get().strip()
        question = self.question_text.get("1.0", "end").strip()
        preset_name = self.preset_var.get().strip()

        if not endpoint:
            messagebox.showerror("Missing endpoint", "Please provide an endpoint.")
            return

        if not model:
            messagebox.showerror("Missing model", "Please provide a model.")
            return

        if not question:
            messagebox.showerror("Missing question", "Please provide a question.")
            return

        if preset_name not in self.presets:
            messagebox.showerror("Invalid preset", "Please select a valid preset.")
            return

        try:
            timeout = int(self.timeout_var.get().strip())
            rounds = int(self.rounds_var.get().strip())
            if timeout < 1 or rounds < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid numbers", "Timeout and rounds must be integers greater than 0.")
            return

        max_tokens = None
        max_tokens_text = self.max_tokens_var.get().strip()
        if max_tokens_text:
            try:
                max_tokens = int(max_tokens_text)
                if max_tokens < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid max tokens", "Max tokens must be an integer greater than 0.")
                return

        temperature = None
        temperature_text = self.temperature_var.get().strip()
        if temperature_text:
            try:
                temperature = float(temperature_text)
                if temperature < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid temperature", "Temperature must be a number greater than or equal to 0.")
                return

        top_p = None
        top_p_text = self.top_p_var.get().strip()
        if top_p_text:
            try:
                top_p = float(top_p_text)
                if top_p <= 0 or top_p > 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid top_p", "Top P must be a number greater than 0 and less than or equal to 1.")
                return

        clean = endpoint.rstrip("/").lower()
        uses_anthropic = provider == "anthropic" or (provider == "auto" and (clean.endswith("/v1/messages") or "/v1/messages" in clean or "anthropic" in clean))
        if uses_anthropic and not api_key:
            messagebox.showerror("Missing API key", "Anthropic requires an API key.")
            return

        self.turn_history = []
        self.live_turn_name = ""
        self.live_turn_text = ""
        self.synthesis_started = False
        self.synthesis_buffer = ""

        self._render_transcript()
        self._render_synthesis()

        self.stop_event.clear()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status_var.set("Starting")

        self.worker_thread = threading.Thread(
            target=run_debate,
            kwargs={
                "endpoint": endpoint,
                "provider": provider,
                "api_key": api_key,
                "model": model,
                "timeout": timeout,
                "rounds": rounds,
                "preset_name": preset_name,
                "presets": self.presets,
                "question": question,
                "ui_queue": self.ui_queue,
                "stop_event": self.stop_event,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            },
            daemon=True,
        )
        self.worker_thread.start()

    def stop_debate(self):
        self.stop_event.set()
        self.status_var.set("Stopping")

    def process_ui_queue(self):
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()

                if event == "status":
                    self.status_var.set(payload)

                elif event == "start_turn":
                    self.live_turn_name = payload
                    self.live_turn_text = ""
                    self._render_transcript()

                elif event == "turn_chunk":
                    self.live_turn_text += payload
                    self._render_transcript()

                elif event == "end_turn":
                    if self.live_turn_name:
                        self.turn_history.append((self.live_turn_name, self.live_turn_text.strip()))
                    self.live_turn_name = ""
                    self.live_turn_text = ""
                    self._render_transcript()

                elif event == "clear_synthesis":
                    self.synthesis_started = False
                    self.synthesis_buffer = ""
                    self._render_synthesis()

                elif event == "start_synthesis":
                    self.synthesis_started = True
                    self.synthesis_buffer = ""
                    self._render_synthesis()

                elif event == "synthesis_chunk":
                    self.synthesis_buffer += payload
                    self._render_synthesis()

                elif event == "end_synthesis":
                    self._render_synthesis()

                elif event == "finished":
                    self.start_button.config(state="normal")
                    self.stop_button.config(state="disabled")

                elif event == "error":
                    self.start_button.config(state="normal")
                    self.stop_button.config(state="disabled")
                    self.status_var.set("Error")
                    messagebox.showerror("Error", payload)

        except queue.Empty:
            pass
        except Exception as e:
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.status_var.set("Error")
            messagebox.showerror("Error", str(e))

        self.after(50, self.process_ui_queue)


def main():
    app = AgenticGUI()
    app.mainloop()


if __name__ == "__main__":
    main()