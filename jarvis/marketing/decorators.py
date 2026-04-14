"""Marketing permission decorators."""
from core.roles.decorators import v2_permission_required


def mkt_permission_required(entity, action):
    """Marketing V2 permission check. Delegates to v2_permission_required."""
    return v2_permission_required('marketing', entity, action)
