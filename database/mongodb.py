import motor.motor_asyncio
from config import Config
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(Config.MONGO_URI)
            self.db = self.client[Config.DB_NAME]
            
            # Create indexes
            await self.db.users.create_index("user_id", unique=True)
            await self.db.premium.create_index("user_id", unique=True)
            await self.db.settings.create_index("user_id", unique=True)
            await self.db.daily_usage.create_index([("user_id", 1), ("date", 1)])
            
            logger.info("✅ Connected to MongoDB successfully!")
            return True
        except Exception as e:
            logger.error(f"❌ MongoDB connection error: {e}")
            return False
    
    async def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    # User Collection Methods
    async def add_user(self, user_id: int, username: str = None, first_name: str = None):
        """Add new user to database"""
        try:
            user_data = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "joined_date": datetime.utcnow(),
                "is_banned": False
            }
            await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    async def get_user(self, user_id: int):
        """Get user from database"""
        try:
            return await self.db.users.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    async def get_all_users(self):
        """Get all users"""
        try:
            return await self.db.users.find({}).to_list(length=None)
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    async def get_users_count(self):
        """Get total users count"""
        try:
            return await self.db.users.count_documents({})
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            return 0
    
    async def ban_user(self, user_id: int):
        """Ban a user"""
        try:
            await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": True}}
            )
            return True
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            return False
    
    async def unban_user(self, user_id: int):
        """Unban a user"""
        try:
            await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": False}}
            )
            return True
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            return False
    
    async def is_user_banned(self, user_id: int):
        """Check if user is banned"""
        try:
            user = await self.db.users.find_one({"user_id": user_id})
            return user.get("is_banned", False) if user else False
        except Exception as e:
            logger.error(f"Error checking ban status: {e}")
            return False
