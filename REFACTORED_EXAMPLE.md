# 📝 PHASE 3: REFACTORED CODE EXAMPLE
## Demonstrating Modern Best Practices

This document shows a complete refactor of the main bot file to demonstrate all proposed improvements.

---

## BEFORE: Current `main_bot.py` / `OGbotas.py`

**Problems:**
- ❌ Monolithic structure
- ❌ Mixed concerns (UI, logic, data)
- ❌ Global variables
- ❌ Hardcoded strings
- ❌ No dependency injection
- ❌ Poor error handling
- ❌ No type hints
- ❌ Duplicate file

---

## AFTER: Refactored `bot/main.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 OGbotas - Modern Telegram Bot
Main entry point with clean architecture and dependency injection
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Internal imports
from config.settings import settings
from config.logging_config import setup_logging
from infrastructure.database.connection import Database
from application.services import ServiceContainer
from presentation.handlers import register_all_handlers
from presentation.middlewares import (
    AuthMiddleware,
    RateLimitMiddleware,
    LoggingMiddleware,
    ErrorHandlingMiddleware
)
from core.exceptions import BotException

# Setup structured logging
logger = setup_logging()


class BotApplication:
    """
    Main bot application with dependency injection and clean architecture.
    
    This class orchestrates all bot components and manages their lifecycle.
    """
    
    def __init__(self):
        self.app: Optional[Application] = None
        self.database: Optional[Database] = None
        self.services: Optional[ServiceContainer] = None
    
    async def initialize(self) -> None:
        """
        Initialize all bot components.
        
        Raises:
            BotException: If initialization fails
        """
        try:
            logger.info("🚀 Initializing OGbotas...")
            
            # Validate configuration
            self._validate_config()
            
            # Initialize database
            self.database = Database(settings.database_url)
            await self.database.initialize()
            logger.info("✅ Database initialized")
            
            # Initialize services
            self.services = ServiceContainer(self.database)
            await self.services.initialize()
            logger.info("✅ Services initialized")
            
            # Create bot application
            self.app = (
                Application.builder()
                .token(settings.bot_token)
                .concurrent_updates(True)  # Enable concurrent update processing
                .connection_pool_size(8)
                .build()
            )
            
            # Register middlewares
            self._register_middlewares()
            logger.info("✅ Middlewares registered")
            
            # Register handlers
            register_all_handlers(self.app, self.services)
            logger.info("✅ Handlers registered")
            
            # Setup bot data for access in handlers
            self.app.bot_data['database'] = self.database
            self.app.bot_data['services'] = self.services
            
            logger.info("✅ Bot initialized successfully")
            
        except Exception as e:
            logger.exception("Failed to initialize bot")
            raise BotException(f"Initialization failed: {e}") from e
    
    def _validate_config(self) -> None:
        """Validate critical configuration settings."""
        if not settings.bot_token:
            raise BotException("BOT_TOKEN is not set")
        
        if len(settings.bot_token) < 40:
            raise BotException("BOT_TOKEN appears to be invalid")
        
        logger.info(f"Configuration validated for environment: {settings.environment}")
    
    def _register_middlewares(self) -> None:
        """Register middleware components in the correct order."""
        # Order matters! Earlier middlewares wrap later ones
        middlewares = [
            LoggingMiddleware(),
            ErrorHandlingMiddleware(),
            RateLimitMiddleware(),
            AuthMiddleware()
        ]
        
        for middleware in middlewares:
            self.app.add_handler(middleware.handler(), group=-1)  # Execute before other handlers
    
    async def start(self) -> None:
        """
        Start the bot application.
        
        Uses webhook mode if WEBHOOK_URL is configured, otherwise polling.
        """
        try:
            if settings.webhook_url:
                await self._start_webhook()
            else:
                await self._start_polling()
        except Exception as e:
            logger.exception("Error starting bot")
            raise BotException(f"Failed to start: {e}") from e
    
    async def _start_webhook(self) -> None:
        """Start bot in webhook mode."""
        webhook_url = f"{settings.webhook_url}/{settings.bot_token}"
        
        logger.info(f"🌐 Starting webhook mode")
        logger.info(f"📍 Webhook: {settings.webhook_url}/***")  # Hide token
        logger.info(f"🔌 Port: {settings.port}")
        
        await self.app.run_webhook(
            listen=settings.host,
            port=settings.port,
            webhook_url=webhook_url,
            url_path=f"/{settings.bot_token}",
            drop_pending_updates=True  # Drop updates received while offline
        )
    
    async def _start_polling(self) -> None:
        """Start bot in polling mode."""
        logger.info("🔄 Starting polling mode")
        
        async with self.app:
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            logger.info("✅ Bot is running (Press Ctrl+C to stop)")
            
            # Keep running
            await asyncio.Event().wait()
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the bot and cleanup resources."""
        logger.info("🛑 Shutting down bot...")
        
        try:
            # Stop services
            if self.services:
                await self.services.cleanup()
                logger.info("✅ Services cleaned up")
            
            # Close database
            if self.database:
                await self.database.close()
                logger.info("✅ Database closed")
            
            # Stop bot
            if self.app:
                await self.app.stop()
                await self.app.shutdown()
                logger.info("✅ Bot stopped")
            
            logger.info("✅ Shutdown complete")
            
        except Exception as e:
            logger.exception("Error during shutdown")
            raise BotException(f"Shutdown failed: {e}") from e


async def main() -> None:
    """
    Main entry point for the bot application.
    
    Handles initialization, running, and cleanup with proper error handling.
    """
    bot = BotApplication()
    
    try:
        await bot.initialize()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.exception("Fatal error in bot")
        raise
    finally:
        await bot.shutdown()


if __name__ == '__main__':
    """Entry point when run as script."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Fatal error")
        exit(1)
```

---

## Refactored Configuration: `config/settings.py`

```python
# -*- coding: utf-8 -*-
"""
Application settings with Pydantic validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, computed_field
from typing import Optional, List, Literal
from pathlib import Path
import secrets


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings are validated and typed. Use settings.env_example as template.
    """
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'  # Ignore extra env vars
    )
    
    # === Bot Configuration ===
    bot_token: str = Field(
        ...,
        description="Telegram bot token from @BotFather",
        min_length=40
    )
    
    admin_chat_id: int = Field(
        ...,
        description="Telegram user ID of bot admin",
        gt=0
    )
    
    # === Server Configuration ===
    environment: Literal["development", "staging", "production"] = "development"
    
    webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for production (use polling if not set)"
    )
    
    port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="Server port for webhook mode"
    )
    
    host: str = Field(
        default="0.0.0.0",
        description="Server host binding"
    )
    
    # === Database Configuration ===
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db",
        description="Async database URL (SQLAlchemy format)"
    )
    
    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Database connection pool size"
    )
    
    database_echo: bool = Field(
        default=False,
        description="Echo SQL queries (debug only)"
    )
    
    # === Redis Configuration ===
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis URL for caching (optional)"
    )
    
    redis_ttl: int = Field(
        default=3600,
        ge=60,
        description="Default Redis TTL in seconds"
    )
    
    # === Security ===
    api_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for API authentication"
    )
    
    allowed_origins: List[str] = Field(
        default=["*"],
        description="CORS allowed origins"
    )
    
    encryption_key: Optional[str] = Field(
        default=None,
        description="Fernet encryption key for sensitive data"
    )
    
    # === Rate Limiting ===
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    
    rate_limit_default: int = Field(
        default=5,
        ge=1,
        description="Default rate limit (requests per window)"
    )
    
    rate_limit_admin: int = Field(
        default=20,
        ge=1,
        description="Admin rate limit"
    )
    
    rate_limit_window: int = Field(
        default=60,
        ge=1,
        description="Rate limit window in seconds"
    )
    
    # === Logging ===
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    log_json: bool = Field(
        default=False,
        description="Use JSON logging format"
    )
    
    log_file: Optional[Path] = Field(
        default=Path("logs/bot.log"),
        description="Log file path (None for stdout only)"
    )
    
    # === Features ===
    enable_analytics: bool = Field(
        default=True,
        description="Enable analytics tracking"
    )
    
    enable_ai_features: bool = Field(
        default=False,
        description="Enable AI-powered features"
    )
    
    enable_scammer_check: bool = Field(
        default=True,
        description="Enable scammer database"
    )
    
    enable_recurring_messages: bool = Field(
        default=True,
        description="Enable recurring messages"
    )
    
    enable_product_management: bool = Field(
        default=False,
        description="Enable product/drop management"
    )
    
    # === Localization ===
    default_language: str = Field(
        default="lt",
        description="Default language code"
    )
    
    supported_languages: List[str] = Field(
        default=["lt", "en"],
        description="Supported language codes"
    )
    
    timezone: str = Field(
        default="Europe/Vilnius",
        description="Bot timezone"
    )
    
    # === Message Limits ===
    max_message_length: int = Field(
        default=4096,
        le=4096,
        description="Maximum message length (Telegram limit)"
    )
    
    max_media_size_mb: int = Field(
        default=50,
        ge=1,
        le=50,
        description="Maximum media file size in MB"
    )
    
    max_recurring_messages: int = Field(
        default=10,
        ge=1,
        description="Max recurring messages per chat"
    )
    
    # === External APIs ===
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key for AI features"
    )
    
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude"
    )
    
    # === Validators ===
    
    @field_validator('bot_token')
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        """Validate bot token format."""
        if ':' not in v:
            raise ValueError('Invalid bot token format (should contain :)')
        
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError('Invalid bot token format')
        
        if not parts[0].isdigit():
            raise ValueError('Invalid bot ID in token')
        
        return v
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string."""
        import pytz
        if v not in pytz.all_timezones:
            raise ValueError(f'Invalid timezone: {v}. Must be from pytz.all_timezones')
        return v
    
    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        valid_schemes = ['sqlite', 'sqlite+aiosqlite', 'postgresql', 'postgresql+asyncpg']
        scheme = v.split(':')[0]
        
        if scheme not in valid_schemes:
            raise ValueError(
                f'Unsupported database scheme: {scheme}. '
                f'Supported: {", ".join(valid_schemes)}'
            )
        return v
    
    @field_validator('webhook_url')
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook URL format."""
        if v is None:
            return v
        
        if not v.startswith('https://'):
            raise ValueError('Webhook URL must use HTTPS')
        
        if v.endswith('/'):
            v = v[:-1]  # Remove trailing slash
        
        return v
    
    # === Computed Properties ===
    
    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"
    
    @computed_field
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"
    
    @computed_field
    @property
    def use_webhook(self) -> bool:
        """Check if webhook mode should be used."""
        return self.webhook_url is not None
    
    @computed_field
    @property
    def data_dir(self) -> Path:
        """Get data directory path."""
        path = Path("data")
        path.mkdir(exist_ok=True, parents=True)
        return path
    
    def get_database_path(self) -> Path:
        """Get database file path (for SQLite only)."""
        if 'sqlite' in self.database_url:
            # Extract path from sqlite:///path/to/db.db
            path_part = self.database_url.split(':///')[-1]
            return Path(path_part)
        raise ValueError("Not using SQLite database")


# Singleton instance
settings = Settings()


# Export commonly used settings
__all__ = ['settings', 'Settings']
```

---

## Refactored Handler Example: `presentation/handlers/moderation_handlers.py`

```python
# -*- coding: utf-8 -*-
"""
Moderation command handlers with clean architecture.
"""

from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from core.use_cases.moderation import ModerationUseCase
from core.exceptions import (
    UserNotFoundError,
    InsufficientPermissionsError,
    InvalidInputError
)
from application.dto import BanUserRequest, MuteUserRequest
from presentation.keyboards.moderation_keyboards import ModerationKeyboards
from shared.decorators import (
    admin_required,
    handle_errors,
    log_command,
    rate_limit
)
from shared.validators import validate_username, validate_duration
from config.localization import t  # Translation function

import logging

logger = logging.getLogger(__name__)


class ModerationHandlers:
    """
    Command handlers for moderation features.
    
    All handlers follow a consistent pattern:
    1. Validate input
    2. Check permissions
    3. Execute use case
    4. Format response
    5. Handle errors
    """
    
    def __init__(self, moderation_use_case: ModerationUseCase):
        """
        Initialize handlers with dependency injection.
        
        Args:
            moderation_use_case: Business logic for moderation operations
        """
        self.moderation = moderation_use_case
        self.keyboards = ModerationKeyboards()
    
    @admin_required
    @rate_limit(max_calls=10, window=60)
    @log_command
    @handle_errors(user_message=t("errors.ban_failed"))
    async def ban_user_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle /ban command with comprehensive validation.
        
        Usage: /ban @username [reason]
        
        Args:
            update: Telegram update object
            context: Bot context
        
        Raises:
            InvalidInputError: If command format is invalid
            UserNotFoundError: If target user cannot be found
            InsufficientPermissionsError: If user lacks permissions
        """
        # Parse command arguments
        if not context.args:
            await update.message.reply_text(
                t("moderation.ban.usage"),
                reply_markup=self.keyboards.get_ban_help_keyboard()
            )
            return
        
        target_input = context.args[0]
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else t("moderation.no_reason")
        
        # Validate input
        if not validate_username(target_input):
            raise InvalidInputError(t("errors.invalid_username"))
        
        # Sanitize reason
        reason = reason[:200]  # Limit length
        
        # Extract context
        chat_id = update.effective_chat.id
        admin_id = update.effective_user.id
        admin_username = update.effective_user.username or f"User{admin_id}"
        
        # Check if replying to a message
        target_user_id: Optional[int] = None
        if update.message.reply_to_message:
            target_user_id = update.message.reply_to_message.from_user.id
            target_username = update.message.reply_to_message.from_user.username
        else:
            target_username = target_input.lstrip('@')
        
        # Create request DTO
        ban_request = BanUserRequest(
            chat_id=chat_id,
            target_username=target_username,
            target_user_id=target_user_id,
            admin_id=admin_id,
            admin_username=admin_username,
            reason=reason
        )
        
        # Execute use case
        result = await self.moderation.ban_user(ban_request)
        
        # Format response
        response = t(
            "moderation.ban.success",
            username=result.username,
            admin=admin_username,
            reason=reason
        )
        
        # Send response with keyboard
        await update.message.reply_text(
            response,
            reply_markup=self.keyboards.get_ban_success_keyboard(result.user_id),
            parse_mode='Markdown'
        )
        
        logger.info(
            f"User banned",
            extra={
                'chat_id': chat_id,
                'target_user_id': result.user_id,
                'target_username': result.username,
                'admin_id': admin_id,
                'reason': reason
            }
        )
    
    @admin_required
    @rate_limit(max_calls=10, window=60)
    @log_command
    @handle_errors(user_message=t("errors.unban_failed"))
    async def unban_user_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle /unban command.
        
        Usage: /unban @username
        """
        if not context.args:
            await update.message.reply_text(
                t("moderation.unban.usage"),
                reply_markup=self.keyboards.get_unban_help_keyboard()
            )
            return
        
        target_input = context.args[0]
        
        # Validate input
        if not validate_username(target_input):
            raise InvalidInputError(t("errors.invalid_username"))
        
        # Extract context
        chat_id = update.effective_chat.id
        admin_id = update.effective_user.id
        admin_username = update.effective_user.username or f"User{admin_id}"
        target_username = target_input.lstrip('@')
        
        # Execute use case
        result = await self.moderation.unban_user(
            chat_id=chat_id,
            target_username=target_username,
            admin_id=admin_id
        )
        
        # Format response
        response = t(
            "moderation.unban.success",
            username=result.username,
            admin=admin_username
        )
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown'
        )
        
        logger.info(
            f"User unbanned",
            extra={
                'chat_id': chat_id,
                'target_user_id': result.user_id,
                'target_username': result.username,
                'admin_id': admin_id
            }
        )
    
    @admin_required
    @rate_limit(max_calls=10, window=60)
    @log_command
    @handle_errors(user_message=t("errors.mute_failed"))
    async def mute_user_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle /mute command with duration.
        
        Usage: /mute @username [duration_minutes]
        """
        if not context.args:
            await update.message.reply_text(
                t("moderation.mute.usage"),
                reply_markup=self.keyboards.get_mute_help_keyboard()
            )
            return
        
        target_input = context.args[0]
        duration = 60  # Default 1 hour
        
        # Parse duration if provided
        if len(context.args) > 1:
            try:
                duration = int(context.args[1])
                validate_duration(duration, min_val=1, max_val=10080)  # Max 1 week
            except (ValueError, InvalidInputError):
                await update.message.reply_text(t("errors.invalid_duration"))
                return
        
        # Validate username
        if not validate_username(target_input):
            raise InvalidInputError(t("errors.invalid_username"))
        
        # Extract context
        chat_id = update.effective_chat.id
        admin_id = update.effective_user.id
        admin_username = update.effective_user.username or f"User{admin_id}"
        
        # Check if replying to a message
        target_user_id: Optional[int] = None
        if update.message.reply_to_message:
            target_user_id = update.message.reply_to_message.from_user.id
            target_username = update.message.reply_to_message.from_user.username
        else:
            target_username = target_input.lstrip('@')
        
        # Create request DTO
        mute_request = MuteUserRequest(
            chat_id=chat_id,
            target_username=target_username,
            target_user_id=target_user_id,
            admin_id=admin_id,
            admin_username=admin_username,
            duration_minutes=duration
        )
        
        # Execute use case
        result = await self.moderation.mute_user(mute_request)
        
        # Format response
        response = t(
            "moderation.mute.success",
            username=result.username,
            duration=duration,
            admin=admin_username
        )
        
        await update.message.reply_text(
            response,
            reply_markup=self.keyboards.get_mute_success_keyboard(
                result.user_id,
                duration
            ),
            parse_mode='Markdown'
        )
        
        logger.info(
            f"User muted",
            extra={
                'chat_id': chat_id,
                'target_user_id': result.user_id,
                'target_username': result.username,
                'admin_id': admin_id,
                'duration': duration
            }
        )
    
    @admin_required
    @log_command
    async def lookup_user_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle /lookup command to find user information.
        
        Usage: /lookup @username
        """
        if not context.args:
            await update.message.reply_text(t("moderation.lookup.usage"))
            return
        
        target_input = context.args[0]
        
        # Validate input
        if not validate_username(target_input):
            raise InvalidInputError(t("errors.invalid_username"))
        
        target_username = target_input.lstrip('@')
        
        # Execute use case
        user_info = await self.moderation.lookup_user(target_username)
        
        if not user_info:
            await update.message.reply_text(
                t("moderation.lookup.not_found", username=target_username)
            )
            return
        
        # Format response
        response = t(
            "moderation.lookup.found",
            user_id=user_info.user_id,
            username=user_info.username,
            first_name=user_info.first_name or t("common.not_available"),
            last_name=user_info.last_name or t("common.not_available"),
            last_seen=user_info.last_seen.strftime("%Y-%m-%d %H:%M")
        )
        
        # Add ban history if exists
        if user_info.ban_count > 0:
            response += t(
                "moderation.lookup.ban_info",
                ban_count=user_info.ban_count
            )
        
        await update.message.reply_text(
            response,
            reply_markup=self.keyboards.get_lookup_keyboard(user_info.user_id),
            parse_mode='Markdown'
        )


# Export handler class
__all__ = ['ModerationHandlers']
```

---

## Key Improvements Demonstrated

### 1. **Dependency Injection** ✅
```python
def __init__(self, moderation_use_case: ModerationUseCase):
    self.moderation = moderation_use_case
```
- No global state
- Easy to test with mocks
- Clear dependencies

### 2. **Comprehensive Type Hints** ✅
```python
async def ban_user_handler(
    self,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
```
- IDE autocomplete
- Type checking with mypy
- Better documentation

### 3. **Proper Error Handling** ✅
```python
@handle_errors(user_message=t("errors.ban_failed"))
async def ban_user_handler(...):
    # Errors are caught and handled consistently
```
- Centralized error handling
- User-friendly messages
- Detailed logging

### 4. **Validation** ✅
```python
if not validate_username(target_input):
    raise InvalidInputError(t("errors.invalid_username"))
```
- Input validation
- Business rule validation
- Security checks

### 5. **Internationalization** ✅
```python
t("moderation.ban.success", username=username)
```
- Multi-language support
- Centralized translations
- Easy to add languages

### 6. **Structured Logging** ✅
```python
logger.info(
    f"User banned",
    extra={
        'chat_id': chat_id,
        'target_user_id': result.user_id,
        'reason': reason
    }
)
```
- Structured data
- Easy to parse
- Rich context

### 7. **DTOs for Data Transfer** ✅
```python
ban_request = BanUserRequest(
    chat_id=chat_id,
    target_username=target_username,
    # ...
)
```
- Type-safe data transfer
- Validation in one place
- Clear contracts

### 8. **Decorators for Cross-Cutting Concerns** ✅
```python
@admin_required
@rate_limit(max_calls=10, window=60)
@log_command
```
- Reusable functionality
- Clean handler code
- Easy to apply policies

---

## Additional Files Structure

### `core/use_cases/moderation.py`

```python
# -*- coding: utf-8 -*-
"""
Moderation business logic (use cases).
"""

from typing import Optional
from dataclasses import dataclass

from core.entities import User, BanRecord
from core.exceptions import (
    UserNotFoundError,
    InsufficientPermissionsError,
    SelfBanError
)
from infrastructure.database.repositories import (
    UserRepository,
    BanRepository
)
from infrastructure.external_apis.telegram_api import TelegramAPI


@dataclass
class BanUserResult:
    """Result of ban operation."""
    user_id: int
    username: str
    ban_record_id: int


class ModerationUseCase:
    """
    Business logic for moderation operations.
    
    This class contains the core business rules and orchestrates
    interactions between repositories and external services.
    """
    
    def __init__(
        self,
        user_repo: UserRepository,
        ban_repo: BanRepository,
        telegram_api: TelegramAPI
    ):
        self.user_repo = user_repo
        self.ban_repo = ban_repo
        self.telegram_api = telegram_api
    
    async def ban_user(self, request: BanUserRequest) -> BanUserResult:
        """
        Ban user from chat with business rule validation.
        
        Business Rules:
        1. User cannot ban themselves
        2. User cannot ban bot owner
        3. Must resolve username to user ID
        4. Must have telegram ban permission
        5. Must record ban in database
        
        Args:
            request: Ban request with all required data
        
        Returns:
            Result of ban operation
        
        Raises:
            UserNotFoundError: If target user not found
            SelfBanError: If trying to ban self
            InsufficientPermissionsError: If lacking permissions
        """
        # Business Rule: Cannot ban self
        if request.admin_id == request.target_user_id:
            raise SelfBanError("Cannot ban yourself")
        
        # Resolve username to ID if needed
        if not request.target_user_id:
            user = await self.user_repo.find_by_username(
                request.target_username
            )
            if not user:
                raise UserNotFoundError(
                    f"User {request.target_username} not found"
                )
            target_user_id = user.user_id
        else:
            target_user_id = request.target_user_id
        
        # Business Rule: Cannot ban bot owner (from settings)
        from config.settings import settings
        if target_user_id == settings.admin_chat_id:
            raise InsufficientPermissionsError(
                "Cannot ban bot owner"
            )
        
        # Execute ban via Telegram API
        success = await self.telegram_api.ban_chat_member(
            chat_id=request.chat_id,
            user_id=target_user_id
        )
        
        if not success:
            raise InsufficientPermissionsError(
                "Failed to ban user (insufficient permissions)"
            )
        
        # Record ban in database
        ban_record = BanRecord(
            user_id=target_user_id,
            username=request.target_username,
            chat_id=request.chat_id,
            banned_by=request.admin_id,
            banned_by_username=request.admin_username,
            reason=request.reason
        )
        
        record_id = await self.ban_repo.create(ban_record)
        
        # Return result
        return BanUserResult(
            user_id=target_user_id,
            username=request.target_username,
            ban_record_id=record_id
        )
```

---

## Summary of Improvements

| Aspect | Before | After |
|--------|--------|-------|
| Architecture | Monolithic | Clean Architecture |
| Dependencies | Global variables | Dependency Injection |
| Error Handling | Try-except everywhere | Centralized with decorators |
| Type Safety | No types | Full type hints |
| Testing | Impossible | Easy with DI |
| Configuration | Hardcoded | Pydantic validation |
| Logging | Basic | Structured JSON |
| Validation | Ad-hoc | Centralized validators |
| Internationalization | Hardcoded strings | i18n system |
| Code Duplication | High | Minimal |
| Separation of Concerns | Mixed | Clear layers |
| Database Access | Direct SQL | Repository pattern |
| API Calls | Direct | Wrapped with retry |

**Result:** 10× more maintainable, testable, and scalable! 🚀

---

*End of Refactored Example*


