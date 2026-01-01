from database.mongodb import Database
from config import Config
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class UserDatabase(Database):
    
    # Premium Methods
    async def add_premium(self, user_id: int, days: int):
        """Add premium to user"""
        try:
            expiry_date = datetime.utcnow() + timedelta(days=days)
            premium_data = {
                "user_id": user_id,
                "is_premium": True,
                "start_date": datetime.utcnow(),
                "expiry_date": expiry_date,
                "days": days
            }
            await self.db.premium.update_one(
                {"user_id": user_id},
                {"$set": premium_data},
                upsert=True
            )
            return True, expiry_date
        except Exception as e:
            logger.error(f"Error adding premium: {e}")
            return False, None
    
    async def remove_premium(self, user_id: int):
        """Remove premium from user"""
        try:
            await self.db.premium.delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Error removing premium: {e}")
            return False
    
    async def is_premium(self, user_id: int):
        """Check if user is premium"""
        try:
            # Check if owner
            if user_id in Config.OWNER_IDS:
                return True
            
            premium = await self.db.premium.find_one({"user_id": user_id})
            if not premium:
                return False
            
            # Check expiry
            if premium.get("expiry_date") and premium["expiry_date"] > datetime.utcnow():
                return True
            else:
                # Remove expired premium
                await self.remove_premium(user_id)
                return False
        except Exception as e:
            logger.error(f"Error checking premium: {e}")
            return False
    
    async def get_premium_info(self, user_id: int):
        """Get premium info"""
        try:
            return await self.db.premium.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error getting premium info: {e}")
            return None
    
    # Daily Usage Methods
    async def get_daily_usage(self, user_id: int):
        """Get user's daily usage"""
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            usage = await self.db.daily_usage.find_one({
                "user_id": user_id,
                "date": today
            })
            return usage.get("count", 0) if usage else 0
        except Exception as e:
            logger.error(f"Error getting daily usage: {e}")
            return 0
    
    async def increment_usage(self, user_id: int):
        """Increment user's daily usage"""
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            await self.db.daily_usage.update_one(
                {"user_id": user_id, "date": today},
                {"$inc": {"count": 1}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
            return False
    
    async def can_use_bot(self, user_id: int):
        """Check if user can use bot (within daily limit)"""
        try:
            # Check if premium or owner
            if await self.is_premium(user_id):
                return True, -1  # -1 means unlimited
            
            usage = await self.get_daily_usage(user_id)
            remaining = Config.FREE_DAILY_LIMIT - usage
            return remaining > 0, remaining
        except Exception as e:
            logger.error(f"Error checking usage: {e}")
            return False, 0
    
    async def get_max_size(self, user_id: int):
        """Get max file size for user"""
        try:
            if await self.is_premium(user_id):
                return Config.PREMIUM_MAX_SIZE, Config.PREMIUM_MAX_SIZE_MB
            return Config.FREE_MAX_SIZE, Config.FREE_MAX_SIZE_MB
        except Exception as e:
            logger.error(f"Error getting max size: {e}")
            return Config.FREE_MAX_SIZE, Config.FREE_MAX_SIZE_MB
    
    # Settings Methods
    async def get_settings(self, user_id: int):
        """Get user settings"""
        try:
            settings = await self.db.settings.find_one({"user_id": user_id})
            if not settings:
                return {
                    "user_id": user_id,
                    "chat_id": None,
                    "title": None,
                    "thumbnail": None
                }
            return settings
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {}
    
    async def set_chat_id(self, user_id: int, chat_id: int):
        """Set custom chat ID"""
        try:
            await self.db.settings.update_one(
                {"user_id": user_id},
                {"$set": {"chat_id": chat_id}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error setting chat ID: {e}")
            return False
    
    async def set_title(self, user_id: int, title: str):
        """Set custom title"""
        try:
            await self.db.settings.update_one(
                {"user_id": user_id},
                {"$set": {"title": title}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error setting title: {e}")
            return False
    
    async def set_thumbnail(self, user_id: int, thumbnail: str):
        """Set custom thumbnail"""
        try:
            await self.db.settings.update_one(
                {"user_id": user_id},
                {"$set": {"thumbnail": thumbnail}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error setting thumbnail: {e}")
            return False
    
    async def reset_settings(self, user_id: int):
        """Reset user settings"""
        try:
            await self.db.settings.delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Error resetting settings: {e}")
            return False
