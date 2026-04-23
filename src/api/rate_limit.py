"""Limiter compartilhado entre a app principal e os routers.

Mantemos uma única instância do `slowapi.Limiter` para que `app.state.limiter`
e os decoradores dos endpoints conversem. Importar daqui evita import circular
entre `main.py` e os módulos de router em `src/api/`.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])
