from __future__ import annotations

from dataclasses import dataclass

from codex_dictation_utils import command_key


def _command_aliases(*values: str) -> set[str]:
    out = set()
    for value in values:
        cleaned = "".join(ch for ch in value.strip().lower() if ch not in " \t\r\n.,!?;:\"'")
        if cleaned:
            out.add(cleaned)
    return out


ENTER_COMMANDS = _command_aliases("보내", "보내요", "보네", "보네요", "보내줘", "보내 줘", "보내줘요", "보내 줘요")
CUT_COMMANDS = _command_aliases("잘라", "잘라내기", "오려내기")
COPY_COMMANDS = _command_aliases("복사", "복사해", "복사해줘")
PASTE_COMMANDS = _command_aliases("붙여넣기", "붙여 넣기", "붙여넣어", "붙여 넣어")
PASTE_UNDO_COMMANDS = _command_aliases("취소", "붙여넣기 취소", "붙여 넣기 취소", "붙인 거 지워", "붙인 거 취소")
REPLACE_UNDO_COMMANDS = _command_aliases("되돌려", "교체 취소", "바꾼 거 취소")
CLEAR_ALL_COMMANDS = _command_aliases(
    "다 지워",
    "다 지어",
    "다 치워",
    "다 지워줘",
    "다 치워줘",
    "전부 지워",
    "전부 지어",
    "전부 치워",
    "전체 지워",
    "전체 지어",
    "전체 치워",
    "모두 지워",
    "모두 지어",
    "모두 치워",
    "싹 지워",
    "싹 지어",
    "몽땅 지워",
)
CLEAR_FOCUSED_INPUT_COMMANDS = _command_aliases("전체 비워", "전부 비워", "입력창 비워")
WINDOW_MAXIMIZE_COMMANDS = _command_aliases("최대화", "창 최대화", "창 크게")
WINDOW_MINIMIZE_COMMANDS = _command_aliases("최소화", "창 최소화", "창 작게")
WINDOW_RESTORE_COMMANDS = _command_aliases("복원", "원래대로", "창 복원")
ESCAPE_COMMANDS = _command_aliases("이스케이프", "이스케이프 눌러", "나가기", "전체화면 나가기", "전체 화면 나가기")
PLAY_PAUSE_COMMANDS = _command_aliases("일시정지", "일시 정지", "재생", "재생해", "재생해줘", "멈춰", "멈춰줘", "멈춤", "플레이", "플레이해", "플레이 해")
SEEK_FORWARD_COMMANDS = _command_aliases("앞으로 감기", "앞으로감기", "앞으로 감아", "앞으로감아", "앞으로 넘겨", "앞으로넘겨")
SEEK_BACKWARD_COMMANDS = _command_aliases("뒤로 감기", "뒤로감기", "뒤로 감아", "뒤로감아", "뒤로 넘겨", "뒤로넘겨")
AI_CORRECTION_COMMANDS = _command_aliases("정정", "정정해", "정정 해", "교정", "교정해", "교정 해")
DELETE_SOUND_ALIASES = _command_aliases("지워", "지어", "치워", "지워요", "지어요", "치워요", "지워줘", "지어줘", "치워줘", "지워줘요", "치워줘요", "지우", "치우")
CORRECTION_PREFIXES = ("다시 말해줘 ", "다시말해줘 ", "다시 말해 ", "다시말해 ", "다시 해 ", "다시해 ", "다시 ", "다시, ")
LANGUAGE_SWITCH_COMMANDS = {
    **{key: "auto" for key in _command_aliases("자동", "자동으로", "자동 감지", "자동감지", "오토")},
    **{key: "ko" for key in _command_aliases("한국어", "한국어로", "한글", "한글로")},
    **{key: "en" for key in _command_aliases("영어", "영어로", "잉글리시")},
}
COMMAND_PROMPT = (
    "보내 보내요 보네 보내줘 지워 지어 치워 지워요 다 지워 다 치워 전부 지워 전체 지워 모두 지워 전체 비워 "
    "전부 비워 입력창 비워 다시 다시 말해 다시 말해줘 정정 정정해 교정 복사 붙여넣기 붙여 넣기 잘라 잘라내기 취소 "
    "되돌려 자동 한국어 영어 최대화 최소화 복원 이스케이프 나가기 일시정지 재생 앞으로 감기 뒤로 감기"
)
SLOT_NUMBER_WORDS = {
    "1": 1,
    "일": 1,
    "하나": 1,
    "한": 1,
    "2": 2,
    "이": 2,
    "둘": 2,
    "두": 2,
    "3": 3,
    "삼": 3,
    "셋": 3,
    "세": 3,
    "4": 4,
    "사": 4,
    "넷": 4,
    "네": 4,
    "5": 5,
    "오": 5,
    "다섯": 5,
    "6": 6,
    "육": 6,
    "여섯": 6,
    "7": 7,
    "칠": 7,
    "일곱": 7,
    "8": 8,
    "팔": 8,
    "여덟": 8,
    "9": 9,
    "구": 9,
    "아홉": 9,
    "10": 10,
    "십": 10,
    "열": 10,
}
DELETE_COUNT_WORDS = {
    "한": 1,
    "하나": 1,
    "한번": 1,
    "한 번": 1,
    "두": 2,
    "둘": 2,
    "두번": 2,
    "두 번": 2,
    "세": 3,
    "셋": 3,
    "세번": 3,
    "세 번": 3,
    "네": 4,
    "넷": 4,
    "네번": 4,
    "네 번": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
}


@dataclass
class CorrectionTarget:
    kind: str
    source_text: str


def parse_language_switch_text(text: str) -> str | None:
    return LANGUAGE_SWITCH_COMMANDS.get(command_key(text))


def parse_correction_text(text: str) -> str:
    raw = text.strip()
    lowered = raw.lower()
    for prefix in CORRECTION_PREFIXES:
        if lowered.startswith(prefix):
            return raw[len(prefix) :].strip(" \t\r\n.,!?;:\"'")
    return ""


def parse_slot_command_text(text: str) -> tuple[str, int] | None:
    raw = text.strip().lower()
    compact = command_key(text)
    for token, slot in SLOT_NUMBER_WORDS.items():
        if raw in {f"{token}번 복사", f"복사 {token}번"} or compact in {f"{token}번복사", f"복사{token}번"}:
            return ("copy", slot)
        if raw in {f"{token}번 잘라", f"{token}번 잘라내기", f"잘라 {token}번"} or compact in {f"{token}번잘라", f"{token}번잘라내기", f"잘라{token}번"}:
            return ("cut", slot)
        if raw in {f"{token}번 붙여넣기", f"{token}번 붙여 넣기", f"붙여넣기 {token}번", f"붙여 넣기 {token}번"} or compact in {f"{token}번붙여넣기", f"붙여넣기{token}번"}:
            return ("paste", slot)
    return None


def parse_media_command_text(text: str) -> tuple[str, int] | None:
    raw = text.strip().lower()
    compact = command_key(text)
    if compact in ESCAPE_COMMANDS:
        return ("escape", 1)
    if compact in PLAY_PAUSE_COMMANDS:
        return ("play_pause", 1)
    if compact in SEEK_FORWARD_COMMANDS:
        return ("forward", 1)
    if compact in SEEK_BACKWARD_COMMANDS:
        return ("backward", 1)
    for token, count in SLOT_NUMBER_WORDS.items():
        raw_patterns = (
            f"{token}번 앞으로 감기",
            f"{token} 번 앞으로 감기",
            f"앞으로 감기 {token}번",
            f"앞으로 감기 {token} 번",
            f"{token}번 앞으로 감아",
            f"{token} 번 앞으로 감아",
            f"앞으로 감아 {token}번",
            f"앞으로 감아 {token} 번",
            f"{token}번 뒤로 감기",
            f"{token} 번 뒤로 감기",
            f"뒤로 감기 {token}번",
            f"뒤로 감기 {token} 번",
            f"{token}번 뒤로 감아",
            f"{token} 번 뒤로 감아",
            f"뒤로 감아 {token}번",
            f"뒤로 감아 {token} 번",
        )
        compact_patterns = (
            f"{token}번앞으로감기",
            f"앞으로감기{token}번",
            f"{token}번앞으로감아",
            f"앞으로감아{token}번",
            f"{token}번뒤로감기",
            f"뒤로감기{token}번",
            f"{token}번뒤로감아",
            f"뒤로감아{token}번",
        )
        if raw in raw_patterns or compact in compact_patterns:
            if "뒤로" in raw or "뒤로" in compact:
                return ("backward", count)
            return ("forward", count)
    return None


def parse_delete_count_text(text: str) -> int:
    raw = text.strip().lower()
    compact = command_key(text)
    if compact in DELETE_SOUND_ALIASES:
        return 1
    for suffix in ("번지워", "번지어", "번치워", "개지워", "개지어", "개치워"):
        if compact.endswith(suffix):
            count_text = compact[: -len(suffix)]
            if count_text.isdigit():
                return max(1, int(count_text))
    for key, value in DELETE_COUNT_WORDS.items():
        for suffix in (" 번 지워", " 번 지어", " 번 치워", "개 지워", "개 지어", "개 치워", "번만 지워", "번만 지어", "번만 치워"):
            if raw == f"{key}{suffix}":
                return value
        for suffix in ("번지워", "번지어", "번치워", "개지워", "개지어", "개치워", "번만지워", "번만지어", "번만치워"):
            if compact == f"{key}{suffix}":
                return value
    return 0


def is_voice_command_text(text: str) -> bool:
    key = command_key(text)
    if not key:
        return False
    if parse_slot_command_text(text):
        return True
    if key in ENTER_COMMANDS or key in COPY_COMMANDS or key in CUT_COMMANDS or key in PASTE_COMMANDS:
        return True
    if key in PASTE_UNDO_COMMANDS or key in REPLACE_UNDO_COMMANDS or key in CLEAR_FOCUSED_INPUT_COMMANDS or key in CLEAR_ALL_COMMANDS:
        return True
    if key in AI_CORRECTION_COMMANDS:
        return True
    if key in WINDOW_MAXIMIZE_COMMANDS or key in WINDOW_MINIMIZE_COMMANDS or key in WINDOW_RESTORE_COMMANDS:
        return True
    if parse_language_switch_text(text):
        return True
    if parse_media_command_text(text):
        return True
    if parse_delete_count_text(text):
        return True
    if parse_correction_text(text):
        return True
    return False
