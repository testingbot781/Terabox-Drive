from database.mongodb import Database
from database.users import UserDatabase

# Create global instances
db = Database()
user_db = UserDatabase()

__all__ = ['db', 'user_db', 'Database', 'UserDatabase']
