# -*- coding: utf-8 -*-
from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

old_env = '    env = os.environ.copy()\n    env["PYTHONUNBUFFERED"] = "1"\n'
new_env = '    env = os.environ.copy()\n    env["PYTHONUNBUFFERED"] = "1"\n    env["PYTHONIOENCODING"] = "utf-8"\n    env["PYTHONUTF8"] = "1"\n'

if old_env in text:
    text = text.replace(old_env, new_env, 1)
elif 'env["PYTHONIOENCODING"] = "utf-8"' not in text:
    raise RuntimeError("找不到 run_pipeline 里的 env 设置位置。")

start = text.find("def run_cmd(cmd, env):")
if start == -1:
    raise RuntimeError("找不到 def run_cmd(cmd, env)。")

end = text.find("\n\n\ndef build_pipeline_commands", start)
if end == -1:
    raise RuntimeError("找不到 run_cmd 结束位置。")

new_run_cmd = 'def run_cmd(cmd, env):\n    env = env.copy()\n    env["PYTHONIOENCODING"] = "utf-8"\n    env["PYTHONUTF8"] = "1"\n\n    process = subprocess.Popen(\n        cmd,\n        stdout=subprocess.PIPE,\n        stderr=subprocess.STDOUT,\n        text=False,          # 关键：不要让系统默认 GBK 自动解码\n        env=env,\n        bufsize=0,\n    )\n\n    buffer = b""\n\n    while True:\n        chunk = process.stdout.read(1)\n        if not chunk:\n            break\n\n        buffer += chunk\n\n        if chunk in (b"\\n", b"\\r"):\n            raw = buffer\n            buffer = b""\n\n            try:\n                line = raw.decode("utf-8")\n            except UnicodeDecodeError:\n                try:\n                    line = raw.decode("gbk")\n                except UnicodeDecodeError:\n                    line = raw.decode("utf-8", errors="replace")\n\n            yield line\n\n    if buffer:\n        try:\n            line = buffer.decode("utf-8")\n        except UnicodeDecodeError:\n            try:\n                line = buffer.decode("gbk")\n            except UnicodeDecodeError:\n                line = buffer.decode("utf-8", errors="replace")\n        yield line\n\n    process.wait()\n\n    if process.returncode != 0:\n        raise RuntimeError(f"命令失败：{\' \'.join(cmd)}")\n'

text = text[:start] + new_run_cmd + text[end:]

path.write_text(text, encoding="utf-8")
print("已修改 app.py：run_cmd 改为字节读取，手动 UTF-8/GBK 兼容解码。")
