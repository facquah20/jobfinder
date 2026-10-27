"""Import side-effect: registers adapters in priority order."""
from job_finder.adapters import schema_org as _schema_org  # noqa: F401
from job_finder.adapters import greenhouse as _greenhouse  # noqa: F401
from job_finder.adapters import lever as _lever  # noqa: F401
from job_finder.adapters import ashby as _ashby  # noqa: F401
from job_finder.adapters import workday as _workday  # noqa: F401
from job_finder.adapters import generic_html as _generic_html  # noqa: F401