import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app import config
from app.api.trasy import router

_security = HTTPBasic()


def verify(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    # Puste dane w .env nie mogą znaczyć „wpuść każdego" — porównanie dwóch
    # pustych napisów przechodzi, więc najpierw sprawdzamy, czy hasło jest.
    if not (config.AUTH_USERNAME and config.AUTH_PASSWORD):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brak AUTH_USERNAME / AUTH_PASSWORD w .env")
    ok_user = secrets.compare_digest(credentials.username, config.AUTH_USERNAME)
    ok_pass = secrets.compare_digest(credentials.password, config.AUTH_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Błędny login lub hasło",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


app = FastAPI(title="Ogrodnik", dependencies=[Depends(verify)])
app.include_router(router)
