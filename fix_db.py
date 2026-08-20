import asyncio
from app.db.session import engine
from app.models.chat import Base
import app.models.ticket
import app.knowledge.models

async def main():
    async with engine.begin() as conn:
        print("Dropping old tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Recreating tables with new schema (including 'priority' column)...")
        await conn.run_sync(Base.metadata.create_all)
    print("Done! Database is now up to date.")

if __name__ == "__main__":
    asyncio.run(main())