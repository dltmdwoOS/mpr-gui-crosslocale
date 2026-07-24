from __future__ import annotations

SYSTEM_PROMPT_TEMPLATE_VERSION = "cross_locale_system_v1"

ENGLISH_FIXED_PROMPT = (
    "You are a GUI reasoning assistant. Inspect the GUI image and answer the "
    "multiple-choice question. Respond with exactly one label: A, B, C, or D."
)

QUERY_ALIGNED_PROMPTS = {
    "en": ENGLISH_FIXED_PROMPT,
    "zh": "你是一个 GUI 推理助手。请查看 GUI 图像并回答选择题。只输出一个标签：A、B、C 或 D。",
    "fr": "Vous etes un assistant de raisonnement GUI. Examinez l'image GUI et repondez a la question a choix multiple. Repondez avec un seul libelle : A, B, C ou D.",
    "ru": "Вы помощник для рассуждений о GUI. Изучите изображение GUI и ответьте на вопрос с вариантами. Ответьте ровно одной меткой: A, B, C или D.",
    "ja": "あなたはGUI推論アシスタントです。GUI画像を確認し、多肢選択問題に答えてください。A、B、C、Dのいずれか1つのラベルだけを出力してください。",
    "th": "คุณเป็นผู้ช่วยให้เหตุผลเกี่ยวกับ GUI โปรดตรวจดูภาพ GUI แล้วตอบคำถามแบบปรนัย ให้ตอบด้วยป้ายกำกับเดียวเท่านั้น: A, B, C หรือ D",
}


def build_system_prompt(mode: str, question_language: str) -> tuple[str, str, str]:
    if mode == "english_fixed":
        return ENGLISH_FIXED_PROMPT, "en", SYSTEM_PROMPT_TEMPLATE_VERSION
    if mode == "query_aligned":
        if question_language not in QUERY_ALIGNED_PROMPTS:
            raise ValueError(f"No query-aligned system prompt for {question_language!r}")
        return (
            QUERY_ALIGNED_PROMPTS[question_language],
            question_language,
            SYSTEM_PROMPT_TEMPLATE_VERSION,
        )
    raise ValueError(f"Unknown system prompt mode: {mode}")
