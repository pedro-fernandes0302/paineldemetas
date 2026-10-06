"""
Validação do usuário logado via JWT do Supabase, com cargo e equipe (vindos do BigQuery).
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .bigquery_client import get_colaborador_por_email, ColaboradorNaoEncontrado, BigQueryError

_bearer = HTTPBearer(auto_error=True)

_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    if supabase_url not in _jwks_clients:
        jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
        _jwks_clients[supabase_url] = jwt.PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_clients[supabase_url]


class UsuarioLogado(dict):
    """dict com: sub, email, cargo, equipe, digisac_user_id"""

    @property
    def sub(self) -> str:
        return self["sub"]

    @property
    def email(self) -> str:
        return self["email"]

    @property
    def cargo(self) -> str:
        return self.get("cargo", "colaborador")

    @property
    def equipe(self) -> str | None:
        return self.get("equipe")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UsuarioLogado:
    token = credentials.credentials
    settings = get_settings()

    try:
        jwks_client = _get_jwks_client(settings.supabase_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        ) from exc

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sem usuário ou e-mail.")

    try:
        colaborador = get_colaborador_por_email(
            email=email,
            project_id=settings.bq_project_id,
            dataset=settings.bq_dataset,
            table=settings.bq_table_colaboradores,
        )
    except ColaboradorNaoEncontrado:
        raise HTTPException(status_code=403, detail="Usuário não encontrado na base de colaboradores.")
    except BigQueryError as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar dados do usuário: {exc}")

    return UsuarioLogado(
        sub=user_id,
        email=email,
        cargo=colaborador["cargo"],
        equipe=colaborador["equipe"],
    )


def verificar_cargo(*cargos_permitidos: str):
    """
    Dependency factory: bloqueia a rota se o cargo do usuário não estiver na lista.

    Exemplo:
        @router.get("/admin/colaboradores")
        def listar(usuario: UsuarioLogado = Depends(verificar_cargo("admin", "rh"))):
            ...
    """

    def checker(usuario: UsuarioLogado = Depends(get_current_user)) -> UsuarioLogado:
        if usuario.cargo.lower() not in {c.lower() for c in cargos_permitidos}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Cargos permitidos: {', '.join(cargos_permitidos)}",
            )
        return usuario

    return checker