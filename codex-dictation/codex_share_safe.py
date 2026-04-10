from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_KEYS_TO_MASK = {
    "text",
    "input_text",
    "output_text",
    "selection_text",
    "source_text",
    "prompt",
    "raw_text",
    "transcript",
}
WINDOWS_PATH_PATTERN = re.compile(r"(?P<path>(?<![A-Za-z])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>|]+)")
LOCAL_HOST_URL_PATTERN = re.compile(r"(?P<scheme>https?://)(?P<host>localhost|127\.0\.0\.1)(?P<port>:\d+)?", re.IGNORECASE)
LOCAL_HOST_PATTERN = re.compile(r"(?<![\w.-])(?P<host>localhost|127\.0\.0\.1)(?P<port>:\d+)?(?![\w.-])", re.IGNORECASE)
GENERIC_USER_HOME_PATTERN = re.compile(r"(?i)^(?P<drive>[A-Z]:)[/\\]Users[/\\](?P<username>[^/\\]+)(?P<rest>(?:[/\\].*)?)$")
USER_ASSIGNMENT_PATTERN = re.compile(
    r"(?P<prefix>\b(?:user(?:name)?|owner|account)\b\s*[:=]\s*[\"']?)(?P<value>[A-Za-z0-9._-]+)(?P<suffix>[\"']?)",
    re.IGNORECASE,
)


def _normalize_slashes(value: str) -> str:
    return value.replace("\\", "/")


def _masked_text(text: str) -> str:
    return f"<masked-text:{len(text)} chars>"


def _known_usernames(home: Path | None = None) -> set[str]:
    candidates = {
        (home or Path.home()).name,
        os.environ.get("USERNAME", ""),
        Path(os.environ.get("USERPROFILE", "")).name if os.environ.get("USERPROFILE") else "",
    }
    return {value.casefold() for value in candidates if value}


def _sanitize_path(path_text: str, *, project_root: Path | None = None, home: Path | None = None) -> str:
    candidate = Path(path_text)
    root = (project_root or PROJECT_ROOT).resolve()
    resolved_home = (home or Path.home()).resolve()
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
        return relative.as_posix()
    except ValueError:
        pass
    try:
        relative = candidate.resolve(strict=False).relative_to(resolved_home)
        return f"<user-home>/{relative.as_posix()}" if relative.parts else "<user-home>"
    except ValueError:
        pass
    normalized = _normalize_slashes(path_text)
    generic_match = GENERIC_USER_HOME_PATTERN.match(normalized)
    if generic_match:
        rest = generic_match.group("rest").lstrip("/\\")
        return f"<user-home>/{rest.replace('\\', '/')}" if rest else "<user-home>"
    return candidate.name or "<abs-path>"


def mask_share_safe_text(text: str, *, project_root: Path | None = None) -> str:
    if not text:
        return text

    def replace_url(match: re.Match[str]) -> str:
        scheme = match.group("scheme")
        port = match.group("port") or ""
        return f"{scheme}<local-host>{port}"

    def replace_host(match: re.Match[str]) -> str:
        port = match.group("port") or ""
        return f"<local-host>{port}"

    def replace_path(match: re.Match[str]) -> str:
        return _sanitize_path(match.group("path"), project_root=project_root)

    def replace_user_assignment(match: re.Match[str]) -> str:
        value = match.group("value")
        if value.casefold() not in _known_usernames():
            return match.group(0)
        return f"{match.group('prefix')}<user-name>{match.group('suffix')}"

    masked = LOCAL_HOST_URL_PATTERN.sub(replace_url, text)
    masked = LOCAL_HOST_PATTERN.sub(replace_host, masked)
    masked = WINDOWS_PATH_PATTERN.sub(replace_path, masked)
    return USER_ASSIGNMENT_PATTERN.sub(replace_user_assignment, masked)


def sanitize_for_sharing(
    value: Any,
    *,
    project_root: Path | None = None,
    mask_text_fields: bool = False,
    current_key: str = "",
) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_for_sharing(
                item,
                project_root=project_root,
                mask_text_fields=mask_text_fields,
                current_key=str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            sanitize_for_sharing(
                item,
                project_root=project_root,
                mask_text_fields=mask_text_fields,
                current_key=current_key,
            )
            for item in value
        ]
    if isinstance(value, str):
        if mask_text_fields and current_key.lower() in TEXT_KEYS_TO_MASK:
            return _masked_text(value)
        return mask_share_safe_text(value, project_root=project_root)
    return value


def render_share_safe_text(text: str, *, project_root: Path | None = None) -> str:
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return mask_share_safe_text(text, project_root=project_root)
        return json.dumps(
            sanitize_for_sharing(payload, project_root=project_root),
            ensure_ascii=False,
            indent=2,
        )
    return mask_share_safe_text(text, project_root=project_root)


def write_share_safe_json(
    payload: Any,
    output_path: Path,
    *,
    project_root: Path | None = None,
    mask_text_fields: bool = False,
) -> Path:
    sanitized = sanitize_for_sharing(
        payload,
        project_root=project_root,
        mask_text_fields=mask_text_fields,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def export_share_safe_file(
    input_path: Path,
    output_path: Path | None = None,
    *,
    project_root: Path | None = None,
    mask_text_fields: bool = False,
) -> Path:
    destination = output_path or input_path.with_name(f"{input_path.stem}.share-safe{input_path.suffix}")
    original = input_path.read_text(encoding="utf-8")
    stripped = original.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(original)
        except json.JSONDecodeError:
            destination.write_text(mask_share_safe_text(original, project_root=project_root), encoding="utf-8")
            return destination
        return write_share_safe_json(
            payload,
            destination,
            project_root=project_root,
            mask_text_fields=mask_text_fields,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(mask_share_safe_text(original, project_root=project_root), encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="로그/결과물을 공유용으로 마스킹합니다.")
    parser.add_argument("--input", type=Path, required=True, help="원본 파일 경로")
    parser.add_argument("--output", type=Path, help="출력 파일 경로")
    parser.add_argument("--mask-text", action="store_true", help="text/prompt 계열 문자열 값을 추가로 마스킹")
    args = parser.parse_args()

    output = export_share_safe_file(
        args.input,
        args.output,
        project_root=PROJECT_ROOT,
        mask_text_fields=args.mask_text,
    )
    print(output.as_posix())


if __name__ == "__main__":
    main()
