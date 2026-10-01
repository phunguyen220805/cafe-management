def get_demo_dashboard():
    return {
        "is_demo": True,
        "stats": [
            {"label": "Doanh thu hôm nay", "value": "4.820.000 đ", "icon": "revenue"},
            {"label": "Đơn hàng hôm nay", "value": "38", "icon": "orders"},
            {"label": "Số món", "value": "24", "icon": "menu"},
            {"label": "Số bàn", "value": "12", "icon": "tables"},
        ],
        "recent_orders": [
            {"code": "DH-0281", "items": "Bạc xỉu, Croissant", "time": "10:42", "table": "Bàn 04", "total": "115.000 đ", "status": "Hoàn tất"},
            {"code": "DH-0280", "items": "Cold brew, Tiramisu", "time": "10:36", "table": "Mang đi", "total": "142.000 đ", "status": "Đang pha chế"},
            {"code": "DH-0279", "items": "Latte x2", "time": "10:21", "table": "Bàn 08", "total": "120.000 đ", "status": "Hoàn tất"},
            {"code": "DH-0278", "items": "Espresso, Trà đào", "time": "10:08", "table": "Bàn 02", "total": "98.000 đ", "status": "Chờ thanh toán"},
        ],
        "top_items": [
            {"name": "Bạc xỉu", "category": "Cà phê", "sold": 42, "image": "https://images.unsplash.com/photo-1461023058943-07fcbe16d735?auto=format&fit=crop&w=160&q=80"},
            {"name": "Latte đá", "category": "Cà phê", "sold": 36, "image": "https://images.unsplash.com/photo-1461023058943-07fcbe16d735?auto=format&fit=crop&w=160&q=80"},
            {"name": "Cold brew", "category": "Ủ lạnh", "sold": 28, "image": "https://images.unsplash.com/photo-1517701604599-bb29b565090c?auto=format&fit=crop&w=160&q=80"},
        ],
    }