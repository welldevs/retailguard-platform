from erp.generators.customers import generate_customers
from erp.generators.suppliers import generate_suppliers
from erp.generators.inventory import generate_stock
from erp.generators.profiles import CUSTOMER_PROFILES, assign_profile, get_profile
from erp.generators.category_map import (
    CATEGORY_TO_GROUP,
    CATEGORY_GROUPS,
    get_group,
    group_products,
)

__all__ = [
    "generate_customers",
    "generate_suppliers",
    "generate_stock",
    "CUSTOMER_PROFILES",
    "assign_profile",
    "get_profile",
    "CATEGORY_TO_GROUP",
    "CATEGORY_GROUPS",
    "get_group",
    "group_products",
]
