from .appointment import make_appointment_handler
from .dealer_info import get_dealers_info_handler
from .product_info import get_products_info



tools= [
make_appointment_handler,
get_dealers_info_handler,
get_products_info,   
]


__all__ = ["tools"]

