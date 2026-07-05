# API Build Plan - ChPlay API (Python)

## 🎯 API Endpoint

### GET `/api/apps/{package_name}/reviews`

Lấy reviews và comments cho một app cụ thể theo package_name.

#### Request Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Trang hiện tại |
| `pageSize` | int | 20 | Số items trên mỗi trang |

#### Response Format (200 OK)
```json
{
  "total": 3,
  "page": 1,
  "pageSize": 20,
  "reviews": [
    {
      "id": 1,
      "reviewId": null,
      "type": "review",
      "author": {
        "type": "user",
        "name": "Người dùng VNeID 1",
        "avatar": "https://ui-avatars.com/api/?name=V1"
      },
      "rating": 2,
      "content": "...",
      "createdAt": "2026-06-26T10:00:00+07:00",
      "absaStatus": "labeled",
      "botReplyStatus": "pending"
    }
  ],
  "comments": [
    {
      "id": 5,
      "reviewId": 4,
      "type": "comment",
      "author": {
        "type": "bot",
        "name": "Bot Support"
      },
      "content": "...",
      "createdAt": "2026-06-28T11:02:00+07:00",
      "absaStatus": null,
      "botReplyStatus": null
    }
  ]
}
```

---

## 🗄️ Database Tables

### apps
- `id` (bigint, PK)
- `package_name` (varchar) - Unique
- `name` (varchar)
- `icon_url` (varchar, nullable)
- `avg_rating` (numeric, nullable)
- `rating_count` (bigint, nullable)
- `created_at` (timestamp)

### comments
- `id` (bigint, PK)
- `app_id` (bigint, FK)
- `review_id` (bigint, nullable)
- `author_type` (varchar) - 'user' or 'bot'
- `author_name` (varchar)
- `rating` (smallint, 1-5, nullable)
- `content` (text)
- `overall_sentiment` (varchar, nullable)
- `absa_status` (varchar, default: 'pending')
- `bot_reply_status` (varchar, default: 'pending')
- `app_version` (varchar, nullable)
- `source_review_id` (varchar, nullable)
- `created_at` (timestamp)

### comment_aspects (ABSA)
- `id` (bigint, PK)
- `comment_id` (bigint, FK)
- `aspect` (varchar)
- `sentiment` (varchar) - 'positive', 'negative', 'neutral'
- `confidence_score` (numeric)
- `model_version` (varchar)
- `created_at` (timestamp)

---

## 📝 Implementation Steps

### 1. Create Models (SQLAlchemy/ORM)
```python
# models/app.py
class App(Base):
    __tablename__ = 'apps'
    id = Column(BigInteger, primary_key=True)
    package_name = Column(String, unique=True)
    name = Column(String)
    icon_url = Column(String, nullable=True)
    avg_rating = Column(Numeric, nullable=True)
    rating_count = Column(BigInteger, nullable=True)
    created_at = Column(DateTime)
    comments = relationship("Comment", back_populates="app")

# models/comment.py
class Comment(Base):
    __tablename__ = 'comments'
    id = Column(BigInteger, primary_key=True)
    app_id = Column(BigInteger, ForeignKey('apps.id'))
    review_id = Column(BigInteger, nullable=True)
    author_type = Column(String, default='user')
    author_name = Column(String)
    rating = Column(SmallInteger, nullable=True)
    content = Column(Text)
    overall_sentiment = Column(String, nullable=True)
    absa_status = Column(String, default='pending')
    bot_reply_status = Column(String, default='pending')
    app_version = Column(String, nullable=True)
    source_review_id = Column(String, nullable=True)
    created_at = Column(DateTime)
    app = relationship("App", back_populates="comments")
    aspects = relationship("CommentAspect", back_populates="comment")

# models/comment_aspect.py
class CommentAspect(Base):
    __tablename__ = 'comment_aspects'
    id = Column(BigInteger, primary_key=True)
    comment_id = Column(BigInteger, ForeignKey('comments.id'))
    aspect = Column(String)
    sentiment = Column(String)
    confidence_score = Column(Numeric)
    model_version = Column(String)
    created_at = Column(DateTime)
    comment = relationship("Comment", back_populates="aspects")
```

### 2. Create Schemas (Pydantic)
```python
# schemas/review.py
class AuthorSchema(BaseModel):
    type: str
    name: str
    avatar: Optional[str] = None

class ReviewSchema(BaseModel):
    id: int
    reviewId: Optional[int]
    type: str
    author: AuthorSchema
    rating: Optional[int]
    content: str
    createdAt: datetime
    absaStatus: Optional[str]
    botReplyStatus: Optional[str]

class GetReviewsResponseSchema(BaseModel):
    total: int
    page: int
    pageSize: int
    reviews: List[ReviewSchema]
    comments: List[ReviewSchema]
```

### 3. Create Service
```python
# services/app_service.py
class AppService:
    def get_reviews(self, package_name: str, page: int = 1, page_size: int = 20):
        app = db.query(App).filter(App.package_name == package_name).first()
        if not app:
            raise HTTPException(status_code=404, detail="App not found")
        
        offset = (page - 1) * page_size
        
        comments = db.query(Comment).filter(
            Comment.app_id == app.id
        ).order_by(Comment.created_at.desc()).offset(offset).limit(page_size).all()
        
        total = db.query(Comment).filter(Comment.app_id == app.id).count()
        
        reviews = [c for c in comments if c.rating is not None]
        comment_list = [c for c in comments if c.review_id is not None]
        
        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "reviews": reviews,
            "comments": comment_list
        }
```

### 4. Create API Route
```python
# routes/apps.py
@router.get("/apps/{package_name}/reviews")
def get_reviews(
    package_name: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100)
):
    return app_service.get_reviews(package_name, page, pageSize)
```

---

## 🚀 Summary

✅ 1 API endpoint duy nhất: `GET /api/apps/{package_name}/reviews`
✅ Query database, phân trang, lấy reviews + comments
✅ No tests, no complex validation
✅ Done!
