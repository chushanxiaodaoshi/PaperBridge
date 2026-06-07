import os
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.model = os.getenv("QWEN_MODEL", "qwen-plus")
        self.base_url = os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        if not self.api_key:
            raise ValueError("没有找到 DASHSCOPE_API_KEY，请检查 .env 文件。")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def ask(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )

        return response.choices[0].message.content