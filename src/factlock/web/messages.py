"""Korean messages for fixed error codes. Messages never include submitted content."""

GUIDELINE_MESSAGES = {
    "guideline_unreadable": "엑셀 파일을 읽을 수 없습니다. .xlsx 파일인지 확인해 주세요.",
    "guideline_too_large": "파일이 2MB를 넘습니다.",
    "guideline_missing_required": "'필수' 키워드 줄을 찾지 못했습니다.",
    "guideline_missing_emphasis": "'강조내용' 줄이나 번호가 붙은 항목을 찾지 못했습니다.",
}
AI_MESSAGES = {
    "live_writer_not_configured": "연결된 AI가 없습니다.",
    "ai_not_configured": "연결된 AI가 없습니다.",
    "documents_off": "문서 저장소를 쓸 수 없습니다.",
    "stored_requested": "AI를 부르지 않도록 선택했습니다.",
    "stored_draft_missing": "이 타깃은 저장된 초안이 없습니다. AI가 연결되어야 초안을 만들 수 있습니다.",
    "no_matching_products": "회사 자료에서 이 고객에게 맞는 제품을 찾지 못했습니다.",
    "claude_cli_signed_out": "Claude Code 로그인이 만료되었습니다. 터미널에서 claude를 실행해 다시 로그인해 주세요.",
    "claude_cli_timeout": "AI 응답이 너무 오래 걸렸습니다.",
    "codex_cli_timeout": "AI 응답이 너무 오래 걸렸습니다.",
    "claude_auth_failed": "API 키 인증에 실패했습니다.",
    "claude_rate_limited": "AI 요청 한도에 걸렸습니다.",
    "claude_unreachable": "AI 서버에 연결하지 못했습니다.",
    "claude_refused": "AI가 요청을 거절했습니다.",
}
DOCUMENT_MESSAGES = {
    "document_too_large": "파일이 30MB를 넘습니다.",
    "document_type_unsupported": "읽을 수 있는 형식은 PDF, PPTX, DOCX, XLSX, TXT, MD입니다.",
    "document_unreadable": "파일을 읽지 못했습니다. 암호가 걸렸거나 손상된 파일일 수 있습니다.",
    "document_has_no_text": "글자를 찾지 못했습니다. 그림으로만 된 문서일 수 있습니다.",
}
ASSET_MESSAGES = {
    "asset_too_large": "이미지가 10MB를 넘습니다.",
    "asset_type_unsupported": "PNG, JPG, WEBP 이미지만 넣을 수 있습니다.",
    "asset_caption_missing": "무엇이 보이는 이미지인지 설명을 두 글자 이상 적어 주세요.",
    "asset_library_full": "자료함이 가득 찼습니다. 쓰지 않는 자료를 지워 주세요.",
}
AI_DEFAULT = "AI가 답하지 못했습니다. 잠시 뒤 다시 시도해 주세요."


def ai_message(code: str) -> str:
    return AI_MESSAGES.get(code, AI_DEFAULT) if code else ""
