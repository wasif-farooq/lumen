"""Benchmark lumen: GPU vs CPU-only.

    LUMEN_CPU_ONLY=0 uv run python scripts/bench.py
    LUMEN_CPU_ONLY=1 uv run python scripts/bench.py

Test files: LUMEN_BENCH_IMAGES="a.jpg:b.pdf" and LUMEN_BENCH_VIDEO=clip.mp4 (defaults below).

CPU energy (Wh) is shown only if the Intel RAPL counter is readable:
    sudo chmod o+r /sys/class/powercap/intel-rapl:0/energy_uj   # until next reboot
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import ollama

from lumen.core.settings import settings
from lumen.agent import Session
from lumen.caption import PROMPT, _render
from lumen.media import describe_frames

HOME = Path.home()
IMAGES = [Path(p).expanduser() for p in os.environ.get(
    "LUMEN_BENCH_IMAGES", "~/Pictures/id-card.jpg:~/Pictures/receipt.jpeg:~/Documents/scanned-letter.pdf:~/Pictures/logo.png"
).split(":")]
VIDEO = Path(os.environ.get("LUMEN_BENCH_VIDEO", "~/Videos/clip.mp4")).expanduser()
TURNS = [
    "find my CV",
    "show me that file",
    "what files do I have about tax?",
    "open the first one",
    "find the ERP accounting process flows pdf and tell me what it covers in one line",
]


RAPL = Path("/sys/class/powercap/intel-rapl:0")


def cpu_energy_j() -> float | None:
    """CPU package energy counter in joules, or None if not readable (needs the chmod above)."""
    try:
        return int((RAPL / "energy_uj").read_text()) / 1e6
    except (OSError, ValueError):
        return None


def ollama_cpu_seconds() -> float:
    """CPU time used by all ollama processes (server + model runners)."""
    tick = os.sysconf("SC_CLK_TCK")
    total = 0.0
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if not any(k in (p / "comm").read_text() for k in ("ollama", "llama-server")):
                continue
            f = (p / "stat").read_text().rsplit(")", 1)[1].split()
            total += (int(f[11]) + int(f[12])) / tick
        except OSError:
            continue
    return total


class GpuPower(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.running = [], True

    def run(self):
        while self.running:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                capture_output=True, text=True,
            ).stdout.strip()
            try:
                self.samples.append(float(out))
            except ValueError:
                pass
            time.sleep(0.5)

    def stop(self) -> float:
        self.running = False
        return sum(self.samples) / len(self.samples) if self.samples else 0.0


def measure(name, fn):
    gpu = GpuPower()
    gpu.start()
    cpu0, e0, t0 = ollama_cpu_seconds(), cpu_energy_j(), time.time()
    extra = fn()
    secs = time.time() - t0
    cpu = ollama_cpu_seconds() - cpu0
    e1 = cpu_energy_j()
    watts = gpu.stop()
    cpu_wh = None
    if e0 is not None and e1 is not None:
        if e1 < e0:  # counter wrapped around
            e1 += int((RAPL / "max_energy_range_uj").read_text()) / 1e6
        cpu_wh = (e1 - e0) / 3600
    gpu_wh = watts * secs / 3600
    energy = f"energy CPU {cpu_wh:.3f} Wh + GPU {gpu_wh:.3f} Wh" if cpu_wh is not None else f"GPU {gpu_wh:.3f} Wh"
    print(f"  {name:<22} {secs:6.1f}s  model CPU time {cpu:6.1f}s  GPU avg {watts:5.1f} W  {energy}  {extra or ''}", flush=True)
    return {"secs": round(secs, 1), "model_cpu_s": round(cpu, 1), "gpu_w": round(watts, 1),
            "gpu_wh": round(gpu_wh, 4), "cpu_wh": cpu_wh and round(cpu_wh, 4), "extra": extra}


def main():
    mode = "CPU only" if settings.cpu_only else "GPU"
    client = ollama.Client(host=settings.ollama_host)
    model = settings.agent_model
    # Start cold so both modes pay the same load cost
    for m in client.ps().models:
        client.generate(model=m.model, prompt="", keep_alive=0)
    time.sleep(3)
    print(f"== {mode} ({model})" + ("" if cpu_energy_j() is not None else
          "  [CPU energy not readable: see the chmod in this file's docstring]"), flush=True)
    res = {"mode": mode}

    res["load"] = measure("model load", lambda: client.generate(
        model=model, prompt="hi", keep_alive="10m", options=settings.ollama_options(num_predict=1, num_ctx=settings.num_ctx)
    ) and None)
    placement = next((m for m in client.ps().models if m.model == model), None)
    res["placement"] = f"{placement.size_vram / 2**30:.1f} GB on GPU of {placement.size / 2**30:.1f} GB" if placement else "?"
    print(f"  placement: {res['placement']}")

    def chat():
        s = Session()
        per_turn, tools = [], 0
        for t in TURNS:
            t0 = time.time()
            for kind, _ in s.stream(t):
                tools += kind == "tool_call"
            per_turn.append(round(time.time() - t0, 1))
        return f"per turn {per_turn}, {tools} tool calls"
    res["chat"] = measure("chat (5 turns)", chat)

    def gen_speed():
        r = client.generate(model=model, prompt="Write 120 words about file search.", think=False,
                            options=settings.ollama_options(num_predict=160, temperature=0, num_ctx=settings.num_ctx))
        return f"{r.eval_count / (r.eval_duration / 1e9):.1f} tok/s generation, prompt {r.prompt_eval_count / (r.prompt_eval_duration / 1e9):.0f} tok/s"
    res["speed"] = measure("token speed", gen_speed)

    def captions():
        lens = []
        for p in IMAGES:
            kind = "scanned document page" if p.suffix == ".pdf" else "image"
            r = client.chat(model=model, think=False, keep_alive="10m",
                            messages=[{"role": "user", "content": PROMPT.format(kind=kind), "images": [_render(str(p))]}],
                            options=settings.ollama_options(num_predict=200, num_ctx=4096, temperature=0))
            lens.append(len(r.message.content))
        return f"{len(IMAGES)} images, avg {sum(lens) // len(lens)} chars"
    res["captions"] = measure("captions (4 images)", captions)

    res["video"] = measure("video frames (1)", lambda: describe_frames(str(VIDEO), 12.96)[:60])

    Path(sys.argv[1] if len(sys.argv) > 1 else "/dev/null").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
