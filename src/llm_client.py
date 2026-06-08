import os
import time
import threading

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(dotenv_path=".env")


class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.model = os.getenv("LLM_MODEL", "qwen-plus")
        self.base_url = os.getenv(
            "LLM_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        if not self.api_key:
            raise RuntimeError(
                "没有读取到 LLM_API_KEY，请检查 .env 文件，"
                "或在 Web 页面中输入 API Key。"
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _start_heartbeat(self, stop_event, label="大模型正在分析"):
        def run():
            seconds = 0
            while not stop_event.wait(10):
                seconds += 10
                print(f"[LLM] {label}，已等待 {seconds} 秒，请稍等...", flush=True)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def ask(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        temperature: float = 0.3,
    ):
        prompt_len = len(prompt)
        print(
            f"[LLM] 开始请求大模型：model={self.model}，base_url={self.base_url}，输入长度约 {prompt_len} 字符",
            flush=True
        )

        stop_event = threading.Event()
        heartbeat_thread = self._start_heartbeat(stop_event)

        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )

            elapsed = time.time() - start_time
            print(f"[LLM] Qwen 返回完成，用时 {elapsed:.1f} 秒", flush=True)

            return response.choices[0].message.content

        except Exception as e:
            msg = str(e)

            if "Arrearage" in msg or "overdue-payment" in msg:
                raise RuntimeError(
                    "\nDashScope / 阿里百炼账号当前不可用：可能欠费、余额不足、免费额度用完，或账号状态异常。\n"
                    "请到 DashScope 控制台检查账户余额、免费额度和 API Key 状态。\n"
                    "如果只是想继续生成音频/视频，可以在 app 中跳过所有需要 Qwen 的步骤。\n"
                ) from e

            raise

        finally:
            stop_event.set()
