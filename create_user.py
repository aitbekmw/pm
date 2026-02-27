import asyncio
import argparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.base import import_all_models
import_all_models()  # Ensure all models are registered before any queries

from src.core.security import get_password_hash
from src.db.session import AsyncSessionLocal
from src.users.models import User
from src.companies.models import Company

async def create_user(company: str, name: str, lastname: str, admin_password: str):
    async with AsyncSessionLocal() as session:
        # Find company
        stmt = select(Company).where(Company.name == company)
        result = await session.execute(stmt)
        company_obj = result.scalars().first()
        
        if not company_obj:
            print(f"Error: Company '{company}' not found in the database.")
            return

        hashed_password = get_password_hash(admin_password)
        
        # We need an ad_account since it's unique and not nullable.
        ad_account = f"{name.lower()}.{lastname.lower()}"

        new_user = User(
            ad_account=ad_account,
            first_name=name,
            last_name=lastname,
            role="Admin",  # Setting role as Admin assuming this script creates admins
            admin_password=hashed_password,
            company_id=company_obj.id,
            is_active=True
        )

        session.add(new_user)
        try:
            await session.commit()
            print(f"Successfully created user '{name} {lastname}' at '{company}'.")
            print(f"Generated AD Account (username): {ad_account}")
        except Exception as e:
            await session.rollback()
            print(f"Failed to create user: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new user")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--name", required=True, help="User's first name")
    parser.add_argument("--lastname", required=True, help="User's last name")
    parser.add_argument("--password", dest="admin_password", required=True, help="User's password")
    
    args = parser.parse_args()
    
    asyncio.run(create_user(args.company, args.name, args.lastname, args.admin_password))
