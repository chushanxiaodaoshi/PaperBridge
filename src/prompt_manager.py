import json
from pathlib import Path


PROMPT_ROOT = Path("prompts")
DEFAULT_DIR = PROMPT_ROOT / "defaults"
CUSTOM_DIR = PROMPT_ROOT / "custom"
MANIFEST_PATH = PROMPT_ROOT / "prompt_manifest.json"


def ensure_dirs():
    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)


def safe_prompt_filename(prompt_id: str):
    return (
        prompt_id
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    ) + ".txt"


def default_path(prompt_id: str):
    ensure_dirs()
    return DEFAULT_DIR / safe_prompt_filename(prompt_id)


def custom_path(prompt_id: str):
    ensure_dirs()
    return CUSTOM_DIR / safe_prompt_filename(prompt_id)


def read_text(path: Path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_default_prompt(prompt_id: str, text: str):
    """
    写入默认 prompt。
    这是从源码中提取出来的默认版本，可以被刷新覆盖。
    """
    path = default_path(prompt_id)
    path.write_text(text or "", encoding="utf-8")
    return path


def get_default_prompt(prompt_id: str):
    return read_text(default_path(prompt_id))


def get_custom_prompt(prompt_id: str):
    return read_text(custom_path(prompt_id))


def get_effective_prompt(prompt_id: str, fallback: str = ""):
    """
    实际生效 prompt：
    优先 custom；
    custom 不存在或为空，则使用 default；
    default 也没有，则使用 fallback。
    """
    custom = get_custom_prompt(prompt_id).strip()
    if custom:
        return custom

    default = get_default_prompt(prompt_id).strip()
    if default:
        return default

    return fallback


def save_custom_prompt(prompt_id: str, text: str):
    """
    用户保存 prompt：
    - 如果为空：删除 custom，回退 default
    - 如果和 default 完全一致：也删除 custom，避免重复保存
    - 否则写入 custom
    """
    ensure_dirs()

    text = text or ""
    stripped = text.strip()

    cpath = custom_path(prompt_id)
    default = get_default_prompt(prompt_id).strip()

    if not stripped or stripped == default:
        if cpath.exists():
            cpath.unlink()
        return {
            "mode": "default",
            "path": str(default_path(prompt_id)),
            "message": "已回退默认 prompt。"
        }

    cpath.write_text(text, encoding="utf-8")

    return {
        "mode": "custom",
        "path": str(cpath),
        "message": f"已保存自定义 prompt：{cpath}"
    }


def load_manifest():
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest):
    ensure_dirs()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_prompt_for_ui(prompt_id: str):
    default = get_default_prompt(prompt_id)
    custom = get_custom_prompt(prompt_id)

    if custom.strip():
        return {
            "mode": "custom",
            "text": custom,
            "default": default,
            "custom": custom,
        }

    return {
        "mode": "default",
        "text": default,
        "default": default,
        "custom": "",
    }
