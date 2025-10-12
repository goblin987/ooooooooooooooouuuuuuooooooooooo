# 🚀 PHASE 2: MODERNIZATION AND IMPROVEMENT PLAN
## Making OGbotas 10× Better

**Goal:** Transform the bot into a modern, robust, scalable, and feature-rich application using cutting-edge practices and technologies.

---

## 2.1 ARCHITECTURAL IMPROVEMENTS

### Current Architecture Problems

```
Current Structure (Problematic):
├── OGbotas.py (duplicate of main_bot.py)
├── main_bot.py (monolithic handler file)
├── moderation.py (mixed concerns)
├── recurring_messages.py (UI + Logic + Data)
├── database.py (thin data layer)
├── utils.py (grab bag of utilities)
└── config.py (partial configuration)

Issues:
❌ No clear separation of concerns
❌ Business logic mixed with UI
❌ Direct database access from handlers
❌ No dependency injection
❌ Difficult to test
❌ Hard to extend
```

### Proposed Modern Architecture

```
Proposed Structure (Clean Architecture):

bot/
├── __init__.py
├── main.py                          # Single entry point
│
├── core/                            # Business logic (domain layer)
│   ├── __init__.py
│   ├── models.py                    # Pydantic models
│   ├── entities.py                  # Domain entities
│   ├── use_cases/                   # Business logic
│   │   ├── __init__.py
│   │   ├── moderation.py
│   │   ├── scheduling.py
│   │   └── user_management.py
│   └── exceptions.py                # Custom exceptions
│
├── infrastructure/                   # External services
│   ├── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py           # Connection pool
│   │   ├── repositories.py         # Data access layer
│   │   ├── migrations/             # Alembic migrations
│   │   └── models.py               # SQLAlchemy models
│   ├── cache/
│   │   ├── __init__.py
│   │   └── redis_cache.py          # Redis for caching
│   └── external_apis/
│       └── telegram_api.py         # Telegram wrapper
│
├── presentation/                     # User interface layer
│   ├── __init__.py
│   ├── handlers/                    # Command handlers
│   │   ├── __init__.py
│   │   ├── moderation_handlers.py
│   │   ├── admin_handlers.py
│   │   └── user_handlers.py
│   ├── callbacks/                   # Callback query handlers
│   │   ├── __init__.py
│   │   └── recurring_callbacks.py
│   ├── keyboards/                   # Keyboard layouts
│   │   ├── __init__.py
│   │   └── recurring_keyboards.py
│   └── middlewares/                 # Request middlewares
│       ├── __init__.py
│       ├── auth_middleware.py
│       ├── rate_limit_middleware.py
│       └── logging_middleware.py
│
├── application/                      # Application services
│   ├── __init__.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scheduler_service.py
│   │   ├── notification_service.py
│   │   └── analytics_service.py
│   └── dto.py                       # Data transfer objects
│
├── config/                          # Configuration management
│   ├── __init__.py
│   ├── settings.py                 # Pydantic settings
│   ├── constants.py                # Constants
│   └── localization/               # i18n files
│       ├── en.json
│       └── lt.json
│
├── shared/                          # Shared utilities
│   ├── __init__.py
│   ├── validators.py
│   ├── decorators.py
│   ├── utils.py
│   └── types.py                    # Type definitions
│
└── tests/                           # Test suite
    ├── __init__.py
    ├── unit/
    ├── integration/
    └── e2e/

Additional Files:
├── pyproject.toml                   # Modern Python project config
├── poetry.lock                      # Dependency lock file
├── .env.example                     # Environment template
├── docker-compose.yml              # Docker setup
├── Dockerfile                      # Container definition
├── .github/workflows/              # CI/CD pipelines
│   ├── tests.yml
│   └── deploy.yml
└── docs/                           # Documentation
    ├── API.md
    ├── ARCHITECTURE.md
    └── CONTRIBUTING.md
```

### Key Architectural Patterns

#### 1. **Clean Architecture / Hexagonal Architecture**
- **Benefits:** Testability, maintainability, flexibility
- **Implementation:** Separate domain logic from infrastructure

#### 2. **Repository Pattern**
- **Purpose:** Abstract data access
- **Example:**
```python
class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]:
        pass
    
    @abstractmethod
    async def save(self, user: User) -> None:
        pass
```

#### 3. **Dependency Injection**
- **Purpose:** Loose coupling, easier testing
- **Implementation:** Use `dependency-injector` library

#### 4. **CQRS (Command Query Responsibility Segregation)**
- **Purpose:** Separate read and write operations
- **Use Case:** Different handling for queries vs commands

---

## 2.2 CONFIGURATION MANAGEMENT

### Current Issues
- Hardcoded values throughout code
- No validation of environment variables
- No schema for configuration
- Mixed configuration sources

### Modern Solution: Pydantic Settings

```python
# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
from typing import Optional, List
import secrets

class Settings(BaseSettings):
    """Application settings with validation"""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )
    
    # Bot Configuration
    bot_token: str = Field(..., min_length=40)
    admin_chat_id: int = Field(..., gt=0)
    
    # Server Configuration
    webhook_url: Optional[str] = None
    port: int = Field(default=8000, ge=1024, le=65535)
    host: str = "0.0.0.0"
    
    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./bot_database.db",
        description="Database connection URL"
    )
    database_pool_size: int = Field(default=5, ge=1, le=20)
    
    # Redis Configuration (for caching and rate limiting)
    redis_url: Optional[str] = Field(default=None)
    redis_ttl: int = 3600
    
    # Security
    api_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32)
    )
    allowed_origins: List[str] = ["*"]
    
    # Rate Limiting
    rate_limit_default: int = 5
    rate_limit_admin: int = 20
    rate_limit_window: int = 60  # seconds
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Features
    enable_analytics: bool = True
    enable_scammer_check: bool = True
    enable_recurring_messages: bool = True
    
    # Timezone
    timezone: str = "Europe/Vilnius"
    
    # Message Limits
    max_message_length: int = 4096
    max_media_size_mb: int = 50
    
    @validator('bot_token')
    def validate_bot_token(cls, v):
        if not v.startswith(('bot', 'BOT')):
            if ':' not in v:
                raise ValueError('Invalid bot token format')
        return v
    
    @validator('timezone')
    def validate_timezone(cls, v):
        import pytz
        if v not in pytz.all_timezones:
            raise ValueError(f'Invalid timezone: {v}')
        return v

# Singleton instance
settings = Settings()
```

**Benefits:**
- ✅ Type validation
- ✅ Environment variable parsing
- ✅ Default values
- ✅ Automatic documentation
- ✅ IDE autocomplete

---

## 2.3 TYPE HINTING & READABILITY

### Add Comprehensive Type Hints

```python
# Example: moderation.py refactored with types
from typing import Optional, Union
from telegram import Update
from telegram.ext import ContextTypes

async def resolve_username_to_id(
    context: ContextTypes.DEFAULT_TYPE,
    username_or_id: str,
    chat_id: int
) -> Optional[int]:
    """
    Universal username resolver with multiple fallback methods.
    
    Args:
        context: Bot context
        username_or_id: Username (with/without @) or numeric ID
        chat_id: Chat ID for admin lookup fallback
    
    Returns:
        User ID if found, None otherwise
    
    Raises:
        ValueError: If input format is invalid
    """
    # Implementation...
```

### Create Type Definitions

```python
# shared/types.py
from typing import TypedDict, Literal, NewType

# Strong typing for IDs
UserId = NewType('UserId', int)
ChatId = NewType('ChatId', int)
MessageId = NewType('MessageId', int)

# Typed dictionaries
class UserDict(TypedDict):
    user_id: UserId
    username: str
    first_name: Optional[str]
    last_name: Optional[str]

class BanRecordDict(TypedDict):
    user_id: UserId
    username: str
    chat_id: ChatId
    banned_by: UserId
    reason: str
    timestamp: str

# Enums for status
MessageStatus = Literal["On", "Off"]
RepetitionType = Literal["interval", "daily", "weekly", "monthly"]
```

---

## 2.4 PERFORMANCE & RELIABILITY

### 1. **Async Patterns & Concurrency**

#### Problem: Blocking Operations
Many operations are blocking or not properly async.

#### Solution: Proper Async Patterns

```python
# Use asyncio.gather for parallel operations
async def fetch_user_data(user_ids: List[int]) -> List[UserData]:
    """Fetch multiple users concurrently"""
    tasks = [fetch_single_user(uid) for uid in user_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out exceptions
    return [r for r in results if not isinstance(r, Exception)]

# Use async context managers
from contextlib import asynccontextmanager

@asynccontextmanager
async def database_transaction():
    """Async transaction context"""
    async with get_db_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### 2. **Connection Pooling**

```python
# infrastructure/database/connection.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config.settings import settings

# Create async engine with pool
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    pool_size=settings.database_pool_size,
    max_overflow=10,
    pool_pre_ping=True,  # Check connections before use
    pool_recycle=3600    # Recycle connections every hour
)

# Session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db() -> AsyncSession:
    """Dependency injection for database sessions"""
    async with AsyncSessionLocal() as session:
        yield session
```

### 3. **Caching Layer with Redis**

```python
# infrastructure/cache/redis_cache.py
import redis.asyncio as redis
from typing import Optional, Any
import json
import pickle

class CacheService:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600
    ) -> None:
        """Set value in cache with TTL"""
        await self.redis.setex(
            key,
            ttl,
            json.dumps(value)
        )
    
    async def delete(self, key: str) -> None:
        """Delete key from cache"""
        await self.redis.delete(key)
    
    async def get_user(self, user_id: int) -> Optional[dict]:
        """Get cached user data"""
        return await self.get(f"user:{user_id}")
    
    async def cache_user(self, user_id: int, data: dict) -> None:
        """Cache user data"""
        await self.set(f"user:{user_id}", data, ttl=1800)
```

### 4. **Structured Logging**

```python
# shared/logging_config.py
import logging
import sys
from pythonjsonlogger import jsonlogger
from config.settings import settings

def setup_logging():
    """Configure structured JSON logging"""
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(settings.log_level)
    
    # JSON formatter
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# Usage with context
import contextvars

request_id_var = contextvars.ContextVar('request_id', default=None)

class ContextualLogger:
    """Logger that includes contextual information"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def _add_context(self, extra: dict) -> dict:
        """Add request context to log"""
        request_id = request_id_var.get()
        if request_id:
            extra['request_id'] = request_id
        return extra
    
    def info(self, msg: str, **kwargs):
        self.logger.info(msg, extra=self._add_context(kwargs))
    
    def error(self, msg: str, **kwargs):
        self.logger.error(msg, extra=self._add_context(kwargs))
```

### 5. **Robust Error Handling**

```python
# core/exceptions.py
class BotException(Exception):
    """Base exception for all bot errors"""
    pass

class UserNotFoundError(BotException):
    """User could not be found"""
    pass

class InsufficientPermissionsError(BotException):
    """User lacks required permissions"""
    pass

class RateLimitExceededError(BotException):
    """Rate limit exceeded"""
    pass

class DatabaseError(BotException):
    """Database operation failed"""
    pass

# shared/decorators.py
from functools import wraps
from typing import Callable

def handle_errors(user_message: str = "An error occurred"):
    """Decorator for consistent error handling"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                return await func(update, context)
            except UserNotFoundError:
                await update.message.reply_text("❌ User not found!")
            except InsufficientPermissionsError:
                await update.message.reply_text("❌ Insufficient permissions!")
            except RateLimitExceededError:
                await update.message.reply_text("⏱️ Please slow down!")
            except Exception as e:
                logger.exception(f"Error in {func.__name__}")
                await update.message.reply_text(f"❌ {user_message}")
        return wrapper
    return decorator

# Usage
@handle_errors(user_message="Failed to ban user")
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Implementation...
```

### 6. **Circuit Breaker Pattern**

```python
# shared/circuit_breaker.py
from datetime import datetime, timedelta
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered

class CircuitBreaker:
    """Prevent cascading failures"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self):
        return (
            self.last_failure_time and
            datetime.now() - self.last_failure_time >= timedelta(seconds=self.timeout)
        )
```

---

## 2.5 FEATURE ENHANCEMENTS (10× BETTER!)

### 🤖 **Feature #1: AI-Powered Content Generation**

**Description:** Use LLM APIs to generate varied, engaging recurring messages

```python
# application/services/ai_content_service.py
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from typing import Optional

class AIContentService:
    """Generate AI-powered content for messages"""
    
    def __init__(self, api_key: str, provider: str = "openai"):
        if provider == "openai":
            self.client = AsyncOpenAI(api_key=api_key)
        elif provider == "anthropic":
            self.client = AsyncAnthropic(api_key=api_key)
    
    async def generate_message_variant(
        self,
        base_message: str,
        tone: str = "friendly",
        length: str = "medium"
    ) -> str:
        """
        Generate a variant of the base message with AI
        
        Args:
            base_message: Original message
            tone: Desired tone (friendly, professional, casual)
            length: Desired length (short, medium, long)
        
        Returns:
            Generated message variant
        """
        prompt = f"""
        Rewrite the following message in a {tone} tone, keeping it {length} length.
        Maintain the core meaning but make it fresh and engaging.
        
        Original message: {base_message}
        
        Rewritten message:
        """
        
        response = await self.client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[{
                "role": "user",
                "content": prompt
            }],
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()
    
    async def generate_promotional_content(
        self,
        product_name: str,
        features: list[str],
        target_audience: str
    ) -> dict:
        """Generate complete promotional content"""
        prompt = f"""
        Create promotional content for: {product_name}
        Features: {', '.join(features)}
        Target audience: {target_audience}
        
        Generate:
        1. Catchy headline
        2. Description (2-3 sentences)
        3. Call to action
        4. 3 social media hashtags
        
        Format as JSON.
        """
        
        response = await self.client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    async def generate_welcome_message(
        self,
        group_name: str,
        group_rules: list[str]
    ) -> str:
        """Generate welcoming message for new members"""
        # Implementation...
```

**Integration:**
```python
# In recurring messages
async def save_with_ai_variants(message_text: str) -> None:
    ai_service = AIContentService(settings.openai_api_key)
    
    # Generate 5 variants
    variants = []
    for _ in range(5):
        variant = await ai_service.generate_message_variant(
            message_text,
            tone="friendly"
        )
        variants.append(variant)
    
    # Save all variants and rotate through them
    await save_message_variants(variants)
```

### 📊 **Feature #2: Advanced Analytics Dashboard**

**Description:** Track engagement, user activity, and bot performance

```python
# application/services/analytics_service.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict

@dataclass
class MessageAnalytics:
    message_id: int
    sends: int
    views: int
    clicks: int
    engagement_rate: float
    peak_time: str

class AnalyticsService:
    """Track and analyze bot usage"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def track_message_sent(
        self,
        message_id: int,
        chat_id: int,
        sent_at: datetime
    ):
        """Track when a message was sent"""
        await self.db.execute("""
            INSERT INTO message_analytics 
            (message_id, chat_id, sent_at)
            VALUES (?, ?, ?)
        """, (message_id, chat_id, sent_at))
    
    async def track_button_click(
        self,
        message_id: int,
        user_id: int,
        button_text: str
    ):
        """Track button interactions"""
        await self.db.execute("""
            INSERT INTO button_clicks 
            (message_id, user_id, button_text, clicked_at)
            VALUES (?, ?, ?, ?)
        """, (message_id, user_id, button_text, datetime.now()))
    
    async def get_engagement_metrics(
        self,
        chat_id: int,
        days: int = 7
    ) -> Dict:
        """Get engagement metrics for a chat"""
        since = datetime.now() - timedelta(days=days)
        
        metrics = await self.db.execute("""
            SELECT 
                COUNT(DISTINCT message_id) as messages_sent,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(*) as total_interactions,
                AVG(CASE 
                    WHEN interaction_type = 'click' THEN 1 
                    ELSE 0 
                END) as avg_click_rate
            FROM message_interactions
            WHERE chat_id = ? AND timestamp >= ?
        """, (chat_id, since))
        
        return dict(metrics.fetchone())
    
    async def get_best_posting_times(self, chat_id: int) -> List[int]:
        """Analyze best times to post based on engagement"""
        results = await self.db.execute("""
            SELECT 
                strftime('%H', sent_at) as hour,
                COUNT(*) as engagement
            FROM message_analytics
            WHERE chat_id = ?
            GROUP BY hour
            ORDER BY engagement DESC
            LIMIT 5
        """, (chat_id,))
        
        return [int(row['hour']) for row in results.fetchall()]
    
    async def generate_report(self, chat_id: int) -> str:
        """Generate analytics report"""
        metrics = await self.get_engagement_metrics(chat_id)
        best_times = await self.get_best_posting_times(chat_id)
        
        report = f"""
📊 **Analytics Report**

📬 Messages sent: {metrics['messages_sent']}
👥 Unique users: {metrics['unique_users']}
💬 Total interactions: {metrics['total_interactions']}
📈 Avg click rate: {metrics['avg_click_rate']:.1%}

⏰ Best posting times: {', '.join(f'{h}:00' for h in best_times)}
        """
        
        return report
```

**Bot Command:**
```python
@handle_errors()
async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show analytics dashboard"""
    if not await is_admin(update, context):
        return
    
    analytics = AnalyticsService(context.bot_data['db'])
    report = await analytics.generate_report(update.effective_chat.id)
    
    await update.message.reply_text(report, parse_mode='Markdown')
```

### 🔔 **Feature #3: Smart Notification System**

**Description:** Intelligent notification routing with user preferences

```python
# application/services/notification_service.py
from enum import Enum
from typing import Optional, List

class NotificationPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

class NotificationChannel(Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"

class NotificationService:
    """Smart notification delivery system"""
    
    async def send_notification(
        self,
        user_id: int,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        channels: Optional[List[NotificationChannel]] = None
    ):
        """
        Send notification through appropriate channels based on:
        - User preferences
        - Priority level
        - Time of day
        - User's current status (online/offline)
        """
        # Get user preferences
        prefs = await self.get_user_preferences(user_id)
        
        # Check if user is in "Do Not Disturb" mode
        if prefs.dnd_enabled and priority < NotificationPriority.URGENT:
            await self.queue_for_later(user_id, title, message)
            return
        
        # Determine channels
        if channels is None:
            channels = await self.determine_channels(user_id, priority)
        
        # Send through each channel
        for channel in channels:
            if channel == NotificationChannel.TELEGRAM:
                await self.send_telegram(user_id, title, message)
            elif channel == NotificationChannel.EMAIL:
                await self.send_email(user_id, title, message)
        
        # Track delivery
        await self.track_notification(user_id, title, channels, priority)
    
    async def send_bulk_notification(
        self,
        user_ids: List[int],
        message: str,
        rate_limit: int = 30  # messages per second
    ):
        """Send notifications in batches with rate limiting"""
        import asyncio
        from itertools import islice
        
        def batched(iterable, n):
            it = iter(iterable)
            while batch := list(islice(it, n)):
                yield batch
        
        for batch in batched(user_ids, rate_limit):
            tasks = [
                self.send_notification(uid, "Announcement", message)
                for uid in batch
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(1)  # Rate limiting
```

### 🎯 **Feature #4: A/B Testing System**

**Description:** Test different message variants to optimize engagement

```python
# application/services/ab_testing_service.py
import random
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class MessageVariant:
    id: str
    text: str
    media: Optional[str]
    buttons: Optional[dict]
    impressions: int = 0
    clicks: int = 0

class ABTestingService:
    """A/B test different message variants"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    async def create_test(
        self,
        test_name: str,
        variants: List[MessageVariant],
        duration_days: int = 7
    ) -> str:
        """Create new A/B test"""
        test_id = f"test_{datetime.now().timestamp()}"
        
        await self.db.execute("""
            INSERT INTO ab_tests 
            (test_id, test_name, variants, start_date, end_date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            test_id,
            test_name,
            json.dumps([v.__dict__ for v in variants]),
            datetime.now(),
            datetime.now() + timedelta(days=duration_days)
        ))
        
        return test_id
    
    async def get_variant_for_user(
        self,
        test_id: str,
        user_id: int
    ) -> MessageVariant:
        """Get consistent variant for user"""
        # Check if user already has assignment
        existing = await self.db.execute("""
            SELECT variant_id FROM test_assignments
            WHERE test_id = ? AND user_id = ?
        """, (test_id, user_id))
        
        if row := existing.fetchone():
            variant_id = row['variant_id']
        else:
            # Assign new variant (weighted random)
            variants = await self.get_test_variants(test_id)
            variant = random.choice(variants)
            variant_id = variant.id
            
            # Save assignment
            await self.db.execute("""
                INSERT INTO test_assignments (test_id, user_id, variant_id)
                VALUES (?, ?, ?)
            """, (test_id, user_id, variant_id))
        
        return await self.get_variant(test_id, variant_id)
    
    async def track_impression(self, test_id: str, variant_id: str):
        """Track message impression"""
        await self.db.execute("""
            UPDATE ab_test_metrics
            SET impressions = impressions + 1
            WHERE test_id = ? AND variant_id = ?
        """, (test_id, variant_id))
    
    async def track_interaction(self, test_id: str, variant_id: str):
        """Track user interaction"""
        await self.db.execute("""
            UPDATE ab_test_metrics
            SET interactions = interactions + 1
            WHERE test_id = ? AND variant_id = ?
        """, (test_id, variant_id))
    
    async def get_test_results(self, test_id: str) -> Dict:
        """Analyze test results"""
        results = await self.db.execute("""
            SELECT 
                variant_id,
                impressions,
                interactions,
                (interactions * 1.0 / impressions) as conversion_rate
            FROM ab_test_metrics
            WHERE test_id = ?
            ORDER BY conversion_rate DESC
        """, (test_id,))
        
        return {
            'variants': [dict(row) for row in results.fetchall()],
            'winner': results.fetchone()['variant_id'] if results else None
        }
```

### 🔍 **Feature #5: Advanced User Behavior Analysis**

**Description:** ML-powered insights into user patterns

```python
# application/services/behavior_analysis_service.py
from sklearn.cluster import DBSCAN
import numpy as np

class BehaviorAnalysisService:
    """Analyze user behavior patterns"""
    
    async def analyze_activity_patterns(self, chat_id: int):
        """Identify activity patterns using clustering"""
        # Get user activity data
        activity_data = await self.get_activity_data(chat_id)
        
        # Feature engineering
        features = self.extract_features(activity_data)
        
        # Clustering
        clustering = DBSCAN(eps=0.3, min_samples=5)
        labels = clustering.fit_predict(features)
        
        # Identify patterns
        patterns = self.interpret_clusters(labels, activity_data)
        
        return patterns
    
    def extract_features(self, activity_data):
        """Extract features for ML model"""
        features = []
        for user in activity_data:
            features.append([
                user['messages_per_day'],
                user['avg_message_length'],
                user['active_hours'],
                user['reaction_rate'],
                user['response_time']
            ])
        return np.array(features)
    
    async def predict_churn(self, user_id: int) -> float:
        """Predict likelihood of user leaving group"""
        # Implementation using simple model
        recent_activity = await self.get_recent_activity(user_id)
        
        # Simple heuristic (replace with actual ML model)
        days_since_activity = recent_activity['days_since_last_message']
        prev_avg_frequency = recent_activity['avg_messages_per_week']
        
        if days_since_activity > 30:
            return 0.9  # 90% churn risk
        elif days_since_activity > 14:
            return 0.6  # 60% churn risk
        else:
            return 0.2  # 20% churn risk
```

### 🛡️ **Feature #6: Advanced Security Features**

```python
# application/services/security_service.py
from typing import Set, List
import re

class SecurityService:
    """Advanced security and anti-spam features"""
    
    def __init__(self):
        self.suspicious_patterns = [
            r'bit\.ly/\w+',  # Shortened URLs
            r'telegram\.me/joinchat',  # Invite links
            r'@\w+bot',  # Bot mentions
        ]
        self.rate_limiters = {}
    
    async def analyze_message_safety(self, text: str) -> Dict:
        """Analyze message for security threats"""
        threats = []
        
        # Check for suspicious URLs
        if self.has_suspicious_urls(text):
            threats.append("suspicious_url")
        
        # Check for spam patterns
        if self.is_spam(text):
            threats.append("spam")
        
        # Check for phishing
        if self.is_phishing(text):
            threats.append("phishing")
        
        return {
            'safe': len(threats) == 0,
            'threats': threats,
            'confidence': self.calculate_confidence(threats)
        }
    
    def has_suspicious_urls(self, text: str) -> bool:
        """Detect suspicious URL patterns"""
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def is_spam(self, text: str) -> bool:
        """Detect spam characteristics"""
        # Check for excessive caps
        if sum(1 for c in text if c.isupper()) / len(text) > 0.7:
            return True
        
        # Check for excessive emojis
        emoji_count = len(re.findall(r'[\U0001F300-\U0001F9FF]', text))
        if emoji_count > 10:
            return True
        
        # Check for repetitive content
        words = text.split()
        if len(words) != len(set(words)) and len(words) > 5:
            return True
        
        return False
    
    async def check_user_reputation(self, user_id: int) -> float:
        """Calculate user reputation score (0-1)"""
        # Factors:
        # - Account age
        # - Message count
        # - Reports against user
        # - Ban history
        
        account_age_days = await self.get_account_age(user_id)
        message_count = await self.get_message_count(user_id)
        reports = await self.get_reports_count(user_id)
        bans = await self.get_ban_count(user_id)
        
        # Weighted scoring
        score = 0.5  # Base score
        score += min(account_age_days / 365, 0.25)  # Up to 0.25 for age
        score += min(message_count / 1000, 0.25)  # Up to 0.25 for activity
        score -= reports * 0.1  # Penalty for reports
        score -= bans * 0.2  # Penalty for bans
        
        return max(0.0, min(1.0, score))
```

---

*Continued in next section...*


