"""
Seed script — tạo dữ liệu demo cho ứng dụng VNeID.

Cách chạy:
    python scripts/seed_demo_data.py

Script này sẽ:
1. Tạo app VNeID trong DB (nếu chưa có)
2. Tạo sample reviews (positive, negative, mixed)
3. Tạo sample document (.txt) để demo chunking pipeline
4. In ra hướng dẫn các bước demo workflow

Yêu cầu:
    - Database đã được migrate (alembic upgrade head)
    - File .env đã cấu hình DATABASE_URL
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.models import App, Comment, Document
from app.db.session import async_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_demo")

# ── Dữ liệu mẫu ──────────────────────────────────────────────────────

SAMPLE_APP = {
    "package_name": "com.vnpt.vnpttoken.vneid",
    "name": "VNeID — Định danh điện tử",
    "icon_url": "https://play-lh.googleusercontent.com/0VO1WgUGmCiJLlDd9icgG7c5sn9Y6SofE6GdOhl3AvECfQqWkZQvC40UQYqNQqYqNQ",
    "avg_rating": 4.2,
    "rating_count": 15234,
}

SAMPLE_REVIEWS = [
    {
        "author_name": "Nguyễn Văn An",
        "rating": 5,
        "app_version": "2.3.0",
        "content": (
            "Ứng dụng rất tiện lợi, giúp tôi đăng nhập các dịch vụ công một cách nhanh chóng. "
            "Tích hợp VNeID và giấy tờ xe rất hữu ích. Giao diện thân thiện, dễ sử dụng."
        ),
        "overall_sentiment": "positive",
    },
    {
        "author_name": "Trần Thị Bình",
        "rating": 2,
        "app_version": "2.3.0",
        "content": (
            "Ứng dụng thường xuyên bị lỗi đăng nhập. Mỗi lần muốn dùng là phải đăng nhập lại, "
            "rất bất tiện. Mong nhà phát triển sửa lỗi sớm. Cũng mong có thêm tính năng chat hỗ trợ."
        ),
        "overall_sentiment": "negative",
    },
    {
        "author_name": "Lê Văn Cường",
        "rating": 4,
        "app_version": "2.2.0",
        "content": (
            "Tốt, nhưng cần cải thiện tốc độ tải. Nhiều khi vào app bị chậm, nhất là giờ cao điểm. "
            "Tích hợp thêm nhiều dịch vụ công nữa thì tốt. Cảm ơn đội ngũ phát triển!"
        ),
        "overall_sentiment": "mixed",
    },
    {
        "author_name": "Phạm Thị Dung",
        "rating": 5,
        "app_version": None,
        "content": (
            "Rất hài lòng với ứng dụng. Đã dùng được hơn 6 tháng, các tính năng hoạt động ổn định. "
            "Việc tích hợp thông tin bảo hiểm y tế và bằng lái xe rất tiện. 5 sao!"
        ),
        "overall_sentiment": "positive",
    },
    {
        "author_name": "Hoàng Văn Em",
        "rating": 1,
        "app_version": "2.3.0",
        "content": (
            "Thường xuyên bị crash khi mở app trên Android 14. Đã báo cáo lỗi từ 2 tuần trước "
            "nhưng chưa thấy fix. Rất thất vọng! Nếu không sửa sẽ gỡ app."
        ),
        "overall_sentiment": "negative",
    },
    {
        "author_name": "Đặng Thị Phương",
        "rating": 3,
        "app_version": None,
        "content": (
            "Tạm ổn, nhưng cần bổ sung thêm tính năng. Ví dụ: hiển thị lịch sử đăng nhập, "
            "thông báo khi giấy tờ sắp hết hạn. Mong sớm được cập nhật."
        ),
        "overall_sentiment": "mixed",
    },
    {
        "author_name": "Bùi Quốc Anh",
        "rating": 4,
        "app_version": "2.3.0",
        "content": (
            "Ứng dụng hữu ích, giúp tôi không cần mang nhiều giấy tờ khi đi đường. "
            "Tuy nhiên, QR code đôi khi load chậm ở vùng có sóng yếu. Mong cải thiện."
        ),
        "overall_sentiment": "positive",
    },
    {
        "author_name": "Vũ Thị Mai",
        "rating": 2,
        "app_version": None,
        "content": (
            "Giao diện chưa thân thiện, nhiều thao tác phức tạp. Tôi là người lớn tuổi, "
            "mong có chế độ đơn giản hơn cho người cao tuổi. Cũng nên có hướng dẫn chi tiết bằng video."
        ),
        "overall_sentiment": "negative",
    },
]

SAMPLE_DOCUMENT_CONTENT = """# Hướng dẫn sử dụng ứng dụng VNeID

## Giới thiệu

VNeID là ứng dụng định danh điện tử do Bộ Công an Việt Nam phát triển,
giúp người dân thực hiện các thủ tục hành chính công trực tuyến và xuất trình
giấy tờ tùy thân điện tử.

## Các tính năng chính

### 1. Đăng nhập dịch vụ công
Người dùng có thể đăng nhập vào Cổng dịch vụ công Quốc gia bằng tài khoản VNeID.
Chỉ cần quét mã QR hoặc nhập thông tin đăng nhập.

### 2. Xuất trình giấy tờ
- Căn cước công dân điện tử
- Giấy phép lái xe
- Bảo hiểm y tế
- Các giấy tờ tùy thân khác

### 3. Thông báo
Nhận thông báo khi:
- Giấy tờ sắp hết hạn
- Có cập nhật mới từ cơ quan chức năng
- Yêu cầu xác thực định kỳ

## Yêu cầu hệ thống

- Android 8.0 trở lên
- Kết nối Internet
- CCCD gắn chip (để đăng ký lần đầu)

## Hỗ trợ

Mọi thắc mắc vui lòng liên hệ:
- Hotline: 1900.xxx.xxx
- Email: support@vneid.gov.vn
"""


# ── Helper functions ─────────────────────────────────────────────────


async def get_or_create_app(session) -> App:
    """Tim app VNeID trong DB, neu chua co thi tao moi."""
    from sqlalchemy import select

    stmt = select(App).where(App.package_name == SAMPLE_APP["package_name"])
    result = await session.execute(stmt)
    app = result.scalar_one_or_none()

    if app:
        logger.info("App VNeID da ton tai (id=%s)", app.id)
        return app

    app = App(
        package_name=SAMPLE_APP["package_name"],
        name=SAMPLE_APP["name"],
        icon_url=SAMPLE_APP["icon_url"],
        avg_rating=SAMPLE_APP["avg_rating"],
        rating_count=SAMPLE_APP["rating_count"],
    )
    session.add(app)
    await session.flush()
    logger.info("Da tao app VNeID (id=%s)", app.id)
    return app


async def seed_reviews(session, app: App) -> list[Comment]:
    """Tao sample reviews cho app."""
    from sqlalchemy import func, select

    count_stmt = select(func.count()).select_from(Comment).where(
        Comment.app_id == app.id,
        Comment.author_type == "user",
    )
    result = await session.execute(count_stmt)
    existing_count = result.scalar()

    if existing_count > 0:
        logger.info("Da co %s reviews, bo qua seed reviews", existing_count)
        return []

    created: list[Comment] = []
    for i, review_data in enumerate(SAMPLE_REVIEWS, start=1):
        comment = Comment(
            app_id=app.id,
            review_parent_id=None,
            type="review",
            author_type="user",
            author_name=review_data["author_name"],
            rating=review_data["rating"],
            content=review_data["content"],
            app_version=review_data.get("app_version"),
            overall_sentiment=review_data["overall_sentiment"],
            absa_status="pending",
            bot_reply_status="pending",
        )
        session.add(comment)
        created.append(comment)
        logger.info("  Tao review #%s: %s (rating=%s)", i, review_data["author_name"], review_data["rating"])

    await session.flush()
    logger.info("Da tao %s reviews cho app VNeID", len(created))
    return created


async def seed_document(session) -> Document | None:
    """Tao sample document .txt de demo chunking pipeline."""
    from sqlalchemy import select

    stmt = select(Document).where(Document.filename == "Huong_dan_VNeID.txt")
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc:
        logger.info("Document mau da ton tai (id=%s, status=%s)", doc.id, doc.status)
        return doc

    # Luu file (async de khong block event loop)
    doc_dir = settings.upload_path
    doc_dir.mkdir(parents=True, exist_ok=True)
    file_path = doc_dir / "Huong_dan_VNeID.txt"
    content_bytes = SAMPLE_DOCUMENT_CONTENT.encode("utf-8")
    await asyncio.to_thread(file_path.write_bytes, content_bytes)

    # Tao DB record
    doc = Document(
        filename="Huong_dan_VNeID.txt",
        file_path=str(file_path),
        mime_type="text/plain",
        size=len(content_bytes),
        version=1,
        status="uploaded",
        metadata_json={
            "title": "Huong dan su dung VNeID",
            "author": "Bo Cong an",
            "description": "Tai lieu huong dan cac tinh nang chinh cua ung dung VNeID",
        },
    )
    session.add(doc)
    await session.flush()
    logger.info("Da tao document mau (id=%s, path=%s, size=%s bytes)", doc.id, file_path, doc.size)
    return doc


# ── Chunking demo ────────────────────────────────────────────────────


async def run_chunking(document_id: int) -> None:
    """Chay chunking pipeline cho mot document cu the.

    Args:
        document_id: ID cua document can xu ly.
    """
    from app.db.repository.chunk import ChunkRepository
    from app.db.repository.document import DocumentRepository
    from app.services.chunking.chunker import ChunkingService

    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)
        chunker = ChunkingService()

        doc = await doc_repo.get(document_id)
        if doc is None:
            logger.error("Khong tim thay document id=%s", document_id)
            return

        logger.info("Bat dau chunking cho document id=%s (file: %s)", doc.id, doc.filename)
        chunks = await chunker.process_document(doc, session)
        await session.commit()

        logger.info("Chunking hoan tat: %s chunks duoc tao", len(chunks))
        for c in chunks:
            logger.info("  Chunk #%s: %s ky tu", c.chunk_index, len(c.content))


# ── Seed all ─────────────────────────────────────────────────────────


async def seed_all() -> dict:
    """Run full seed process.

    Returns:
        Dict voi ket qua seed (app_id, review_count, document_id).
    """
    logger.info("=" * 60)
    logger.info("Bat dau seed du lieu demo cho VNeID...")
    logger.info("=" * 60)

    result = {"app_id": None, "review_count": 0, "document_id": None}

    async with async_session_factory() as session:
        # 1. Tao app
        app = await get_or_create_app(session)
        result["app_id"] = app.id

        # 2. Tao reviews
        reviews = await seed_reviews(session, app)
        result["review_count"] = len(reviews)

        # 3. Tao document mau
        doc = await seed_document(session)
        if doc:
            result["document_id"] = doc.id

        await session.commit()

    logger.info("=" * 60)
    logger.info("Seed hoan tat!")
    logger.info("   App ID: %s", result["app_id"])
    logger.info("   Reviews: %s", result["review_count"])
    logger.info("   Document ID: %s", result["document_id"])
    logger.info("=" * 60)

    return result


# ── Demo instruction ─────────────────────────────────────────────────


def print_demo_guide(result: dict) -> None:
    """In huong dan cac buoc demo workflow."""
    package_name = SAMPLE_APP["package_name"]
    doc_id = result.get("document_id")

    border = "=" * 62
    print()
    print(border)
    print("  HUONG DAN DEMO WORKFLOW")
    print(border)
    print()
    print(f"  1. Chay server:")
    print(f"     uv run uvicorn app.main:app --reload")
    print()
    print(f"  2. Kiem tra app VNeID:")
    print(f"     GET http://localhost:8000/api/apps/{package_name}")
    print()
    print(f"  3. Xem reviews:")
    print(f"     GET http://localhost:8000/api/apps/{package_name}/reviews")
    print()

    if doc_id:
        print(f"  4. Upload document (da tao san file tai uploads/):")
        print(f"     POST http://localhost:8000/api/v1/documents/upload")
        print(f"     -> Chon file 'Huong_dan_VNeID.txt'")
        print()
        print(f"  5. Chay chunking pipeline cho document id={doc_id}:")
        print(f"     python -c \"from scripts.seed_demo_data import run_chunking;")
        print(f"     import asyncio; asyncio.run(run_chunking({doc_id}))\"")
        print()

    print(f"  6. Tao review thu cong (tren Swagger):")
    print(f"     POST /api/apps/{package_name}/reviews")
    print(f"     -> Xem bot_reply_status = 'pending'")
    print()
    print(f"  7. Chay job sinh bot reply (can ZAI_API_KEY - GLM):")
    print(f"     python -m app.jobs.generate_review_replies --limit 5")
    print()
    print(f"  8. Kiem tra bot reply da duoc tao:")
    print(f"     GET /api/apps/{package_name}/reviews")
    print(f"     -> Xem comments co author_type='bot'")
    print()
    print(f"  9. Kiem tra Qdrant collection (neu co Qdrant):")
    print(f"     GET http://localhost:6333/collections/documents")
    print()
    print(f"  10. Kiem tra BM25 index (neu da chay chunking):")
    print(f"     -> Kiem tra file data/bm25_index")
    print()
    print(border)
    print("  Mẹo: Swagger UI tai http://localhost:8000/docs")
    print(border)
    print()


# ── Main ─────────────────────────────────────────────────────────────


async def main() -> None:
    """Entry point."""
    result = await seed_all()

    if result["app_id"] is None:
        logger.error("Seed that bai!")
        return

    print_demo_guide(result)


if __name__ == "__main__":
    asyncio.run(main())
