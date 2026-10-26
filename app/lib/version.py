"""The one version constant, and what identifies a build.

Everything that names a version derives it from here rather than repeating a
literal: FastAPI passes it to `/docs` and `/openapi.json`, `/metadata` and
`/status` report it, and the Docker image tag is built from it, so a version
literal in several places cannot drift and the running build can always be
told.

`build_id` is the other half of that. It is read from the environment
rather than baked in, so a rebuild of the same source is distinguishable
from a redeploy of the same image -- `deploy.sh` sets it from the git sha.
"""

from __future__ import annotations

import os

__version__ = '0.3.2'


def build_id() -> str:
    """The build this process is running, or 'dev'.

    Deliberately not derived from git at runtime: the image has no
    repository in it, and a call that shells out on a request path is a
    call that can hang.
    """
    return os.environ.get('GEOSERVICES_BUILD_ID') or 'dev'
