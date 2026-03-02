import os
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import httpx

# Azure AD Configuration (from .env)
TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
ALGORITHMS = ["RS256"]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_azure_public_keys():
    """Fetch public keys from Microsoft for JWT verification."""
    jwks_url = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        return response.json()["keys"]

async def verify_microsoft_sso(token: str = Depends(oauth2_scheme)):
    """
    Validate the Microsoft Azure AD token.
    In a production app, verify:
    - Token issuer (iss)
    - Audience (aud == CLIENT_ID)
    - Expiration (exp)
    - Signature using public keys
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate Microsoft SSO credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Note: In a real enterprise setup, use python-jose to verify against JWKS keys.
        # This is a template for the validation flow.
        unverified_claims = jwt.get_unverified_claims(token)
        
        # In mock/development mode, we extract user info without full JWKS validation.
        # Ensure full RS256 validation is implemented for production.
        user_id = unverified_claims.get("oid") or unverified_claims.get("sub")
        email = unverified_claims.get("preferred_username") or unverified_claims.get("email")
        
        if user_id is None:
            raise credentials_exception
            
        return {"user_id": user_id, "email": email}
        
    except JWTError:
        raise credentials_exception
