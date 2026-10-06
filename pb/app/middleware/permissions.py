"""
Dependências de cargo prontas, pra não repetir verificar_cargo(...) em cada rota.
"""
from ..auth import verificar_cargo

apenas_admin = verificar_cargo("admin")
admin_ou_rh = verificar_cargo("admin", "rh")
admin_rh_ou_vice = verificar_cargo("admin", "rh", "Vice-lider")
