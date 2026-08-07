from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import redirect, session, url_for

SESSION_KEY = "authenticated"


def login_required[View: Callable[..., Any]](view: View) -> View:
    @wraps(view)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if not session.get(SESSION_KEY):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return cast(View, guarded)
