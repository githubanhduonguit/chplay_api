# API Build Plan - ChPlay API (Python)

## 🎯 API Endpoint

### GET `/api/apps/{package_name}`

Lấy thông tin chi tiết của một app theo package_name.

#### Request Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `package_name` | string | Yes | Package name của app (e.g., com.vnpt.vnpttoken.vneid) |

#### Response Format (200 OK)
```json
{
  "id": 1,
  "packageName": "com.vnpt.vnpttoken.vneid",
  "name": "VNeID",
  "icon": "https://play-lh.googleusercontent.com/vneid-icon",
  "rating": {
    "average": 2.3,
    "count": 185000
  },
  "developer": {
    "name": "Bộ Công an"
  },
  "installs": "10M+",
  "category": "Productivity",
  "createdAt": "2022-07-01T00:00:00+07:00"
}
```

#### Response Fields
- `id`: App ID
- `packageName`: Unique package name
- `name`: App display name
- `icon`: URL to app icon
- `rating`: Object containing:
  - `average`: Average rating (0-5)
  - `count`: Total number of ratings
- `developer`: Object containing:
  - `name`: Developer/company name
- `installs`: Installation count range (e.g., "10M+", "1M+")
- `category`: App category (e.g., "Productivity", "Social")
- `createdAt`: ISO 8601 timestamp when app was listed

#### Error Cases
- **404 Not Found**: If app with package_name doesn't exist
- **400 Bad Request**: If package_name is invalid/empty

---

## 🗄️ Database Tables

### apps
| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint | Primary key |
| `package_name` | varchar(256) | Unique package name |
| `name` | varchar(512) | App display name |
| `icon_url` | varchar(1024) | URL to icon image |
| `avg_rating` | numeric(3,2) | Average rating (0-5) |
| `rating_count` | bigint | Total ratings count |
| `developer_name` | varchar(256) | Developer/company name |
| `installs` | varchar(32) | Install count range |
| `category` | varchar(128) | App category |
| `created_at` | timestamp | When app was listed |

---

## 📝 Implementation Steps

### 1. Update App Model
```python
# app/db/models/app.py
class App(BaseMixin, Base):
    __tablename__ = "apps"
    
    package_name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    icon_url: Mapped[str | None] = mapped_column(String(1024))
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int | None] = mapped_column(Integer)
    developer_name: Mapped[str | None] = mapped_column(String(256))
    installs: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

### 2. Create Schemas
```python
# app/schemas/app.py
class RatingSchema(BaseModel):
    average: float
    count: int

class DeveloperSchema(BaseModel):
    name: str | None = None

class AppDetailSchema(BaseModel):
    id: int
    packageName: str
    name: str
    icon: str | None
    rating: RatingSchema
    developer: DeveloperSchema
    installs: str | None
    category: str | None
    createdAt: datetime
```

### 3. Create Service
```python
# app/services/app_service.py
class AppService:
    async def get_app_detail(self, package_name: str) -> AppDetailSchema:
        # Query app by package_name
        app = await db.query(App).filter(App.package_name == package_name).first()
        
        if not app:
            raise HTTPException(404, "App not found")
        
        # Map to response schema
        return AppDetailSchema(
            id=app.id,
            packageName=app.package_name,
            name=app.name,
            icon=app.icon_url,
            rating=RatingSchema(
                average=app.avg_rating,
                count=app.rating_count
            ),
            developer=DeveloperSchema(name=app.developer_name),
            installs=app.installs,
            category=app.category,
            createdAt=app.created_at
        )
```

### 4. Create Route
```python
# app/api/routes/apps.py
@router.get("/apps/{package_name}", response_model=AppDetailSchema)
async def get_app_detail(
    package_name: str,
    db: AsyncSession = Depends(get_db),
) -> AppDetailSchema:
    service = AppService(db)
    return await service.get_app_detail(package_name)
```

---

## 🚀 Implementation Checklist

- [ ] Update `app/db/models/app.py` - Add new columns (developer_name, installs, category)
- [ ] Create `app/schemas/app.py` - Add RatingSchema, DeveloperSchema, AppDetailSchema
- [ ] Update `app/services/app_service.py` - Add get_app_detail() method
- [ ] Update `app/api/routes/apps.py` - Add GET /apps/{package_name} endpoint
- [ ] Update `app/main.py` - Ensure router is registered
- [ ] Test with sample data
- [ ] Document in Swagger/OpenAPI

---

## 📋 Summary

✅ 1 API endpoint: `GET /api/apps/{package_name}`
✅ Returns app detail with rating, developer, installs, category
✅ Uses existing App model with new fields
✅ Simple service layer for data mapping
✅ Async operations with proper error handling
