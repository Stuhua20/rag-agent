from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import chat_service as chat_service_module
from app.services import query_understanding_service as query_understanding_service_module


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
MANAGED_PROMPTS = (
    "system/base.md",
    "query/planner.md",
    "query/translator.md",
    "rag/answer.md",
    "rag/no_source.md",
)
MANAGED_PROMPT_SET = frozenset(MANAGED_PROMPTS)
REQUIRED_PLACEHOLDERS = {
    "query/planner.md": ("{conversation_context}", "{metadata}", "{question}"),
    "query/translator.md": ("{target_language}", "{queries}"),
    "rag/answer.md": (
        "{conversation_context}", "{query_plan}", "{resolved_question}",
        "{evidence_report}", "{context}", "{question}",
    ),
}

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class PromptPayload(BaseModel):
    content: str


def _prompt_path(path: str) -> Path:
    if path not in MANAGED_PROMPT_SET:
        raise HTTPException(status_code=400, detail="不是受管理的运行时提示词文件")

    full_path = (PROMPTS_DIR / path).resolve()
    if PROMPTS_DIR.resolve() not in full_path.parents:
        raise HTTPException(status_code=400, detail="提示词路径无效")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="提示词不存在")
    return full_path


def _clear_prompt_caches() -> None:
    chat_service_module._load_prompt.cache_clear()
    query_understanding_service_module._load_prompt.cache_clear()


def _validate_prompt_content(path: str, content: str) -> None:
    if not content.strip():
        raise HTTPException(status_code=400, detail="提示词内容不能为空")

    missing = [placeholder for placeholder in REQUIRED_PLACEHOLDERS.get(path, ()) if placeholder not in content]
    if missing:
        raise HTTPException(status_code=400, detail=f"提示词缺少必需变量：{', '.join(missing)}")


@router.get("")
def list_prompts() -> list[dict]:
    prompts = []
    for relative_path in MANAGED_PROMPTS:
        file_path = PROMPTS_DIR / relative_path
        if not file_path.is_file():
            continue
        prompts.append(
            {
                "path": relative_path,
                "name": file_path.stem,
                "group": file_path.parent.relative_to(PROMPTS_DIR).as_posix(),
            }
        )
    return prompts


@router.get("/{path:path}")
def get_prompt(path: str) -> dict:
    full_path = _prompt_path(path)
    return {"path": path, "content": full_path.read_text(encoding="utf-8")}


@router.put("/{path:path}")
def update_prompt(path: str, payload: PromptPayload) -> dict:
    full_path = _prompt_path(path)
    _validate_prompt_content(path, payload.content)
    full_path.write_text(payload.content, encoding="utf-8")
    _clear_prompt_caches()
    return {"path": path, "content": payload.content}
