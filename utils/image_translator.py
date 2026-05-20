"""
OpenAI gpt-image-1 API를 사용한 이미지 번역 + 리사이즈 + ZIP 패키징 유틸리티
"""

import base64
import io
import time
import zipfile
from PIL import Image
import openai


# ── 상수 ────────────────────────────────────────────────────────────
MAX_RETRIES = 3
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _detect_orientation(image_bytes: bytes) -> str:
    """이미지 방향을 감지하여 적절한 API 사이즈를 반환한다."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.width > img.height:
        return "1536x1024"   # 가로형
    return "1024x1536"       # 세로형 (기본)


MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def translate_image(
    client: openai.OpenAI,
    image_bytes: bytes,
    filename: str,
    prompt: str,
    size: str | None = None,
) -> tuple[bytes | None, str | None]:
    """
    OpenAI images.edit API로 이미지 속 중국어를 한국어로 번역한다.

    Returns:
        (translated_bytes, None)  — 성공
        (None, error_message)     — 실패
    """
    # 파일 크기 검증
    if len(image_bytes) > MAX_FILE_SIZE:
        return None, f"파일 크기 초과 ({len(image_bytes) / 1024 / 1024:.1f}MB > 50MB)"

    # 사이즈 자동 감지
    if size is None:
        size = _detect_orientation(image_bytes)

    # 확장자에서 MIME 타입 결정
    ext = ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ".png"
    mime_type = MIME_MAP.get(ext, "image/png")

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.images.edit(
                model="gpt-image-2",
                image=(filename, io.BytesIO(image_bytes), mime_type),
                prompt=prompt,
                size=size,
            )
            image_base64 = response.data[0].b64_json
            return base64.b64decode(image_base64), None

        except openai.AuthenticationError:
            return None, "API 키가 유효하지 않습니다. 키를 확인해주세요."

        except openai.RateLimitError as e:
            last_error = f"요청 한도 초과: {e}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            continue

        except openai.BadRequestError as e:
            return None, f"이미지 처리 오류: {e}"

        except openai.APITimeoutError:
            last_error = "API 응답 시간 초과"
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            continue

        except openai.APIError as e:
            return None, f"API 오류: {e}"

    return None, last_error


def resize_to_width(image_bytes: bytes, target_width: int = 780) -> bytes:
    """이미지를 지정 가로폭으로 비율 유지 리사이즈한다."""
    img = Image.open(io.BytesIO(image_bytes))

    if img.width == target_width:
        return image_bytes

    ratio = target_width / img.width
    new_height = int(img.height * ratio)
    img_resized = img.resize((target_width, new_height), Image.LANCZOS)

    buf = io.BytesIO()
    img_resized.save(buf, format="PNG")
    return buf.getvalue()


def create_zip(images: list[tuple[str, bytes]]) -> bytes:
    """(파일명, 이미지 bytes) 리스트를 ZIP bytes로 변환한다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in images:
            # 확장자를 .png로 통일
            name_stem = filename.rsplit(".", 1)[0] if "." in filename else filename
            zf.writestr(f"{name_stem}.png", data)
    return buf.getvalue()
