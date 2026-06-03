"""
Price Fetcher - Background thread for fetching WM prices
"""

import json
import time
import traceback
import socket
import urllib.request
import urllib.error
from threading import Lock
from PyQt6.QtCore import QThread, pyqtSignal


class PriceFetcher(QThread):
    """Background thread for fetching prices from warframe.market"""
    
    progress_update = pyqtSignal(int, str)  # (progress_percent, status_text)
    order_received = pyqtSignal(dict)  # Single order data
    finished = pyqtSignal(bool, str)  # (success, message)
    
    _WM_API_BASE = 'https://api.warframe.market/v2'
    _STATUS_PRIORITY = {'ingame': 0, 'online': 1, 'away': 2, 'offline': 3}
    
    def __init__(self, slug, en_name):
        super().__init__()
        self._slug = slug
        self._en_name = en_name
        self._lock = Lock()
        self._stop_flag = False
    
    def stop(self):
        """Thread-safe stop"""
        with self._lock:
            self._stop_flag = True
    
    def _is_stopped(self):
        """Thread-safe stop check"""
        with self._lock:
            return self._stop_flag
    
    def run(self):
        """Main fetch loop"""
        _prev_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(30)
            self.progress_update.emit(10, "正在连接 warframe.market...")
            
            if self._is_stopped():
                return
            
            # Fetch orders
            url = f"{self._WM_API_BASE}/orders/item/{self._slug}"
            req = urllib.request.Request(url, headers={
                'Accept': 'application/json',
                'User-Agent': 'WARFRAME-RELIC Test'
            })
            
            self.progress_update.emit(30, "获取订单数据中...")
            
            print(f"[性能] 开始请求订单数据: {url}")
            request_start = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            request_time = time.time() - request_start
            print(f"[性能] 订单数据请求完成 (耗时 {request_time:.2f}s)")
            
            # Parse orders
            orders_data = data.get('data', [])
            if isinstance(orders_data, list):
                orders = orders_data
            elif isinstance(orders_data, dict):
                orders = orders_data.get('orders', [])
            else:
                orders = []
            
            sell_orders = [o for o in orders if isinstance(o, dict) and o.get('type') == 'sell']
            
            self.progress_update.emit(50, "处理卖家信息...")
            
            # Sort: in-game first, then by price
            sell_orders.sort(key=lambda x: (
                self._STATUS_PRIORITY.get(x.get('user', {}).get('status'), 4),
                self._safe_int(x.get('platinum', 0))
            ))
            
            # Limit: all ingame/online + max 50 offline
            online_orders = [o for o in sell_orders
                           if o.get('user', {}).get('status') in ('ingame', 'online')]
            offline_orders = [o for o in sell_orders
                            if o.get('user', {}).get('status') not in ('ingame', 'online')]
            limited_orders = online_orders + offline_orders[:50]
            
            self.progress_update.emit(70, "输出结果...")
            
            total = len(limited_orders)
            if total == 0:
                self.progress_update.emit(100, "无匹配订单")
                self.finished.emit(True, "未找到卖家")
                return
            
            for i, order in enumerate(limited_orders):
                if self._is_stopped():
                    return
                
                order_data = self._parse_order(order)
                self.order_received.emit(order_data)
                
                progress = 70 + int((i + 1) / total * 25)
                self.progress_update.emit(progress, f"已加载 {i + 1}/{total}")
            
            self.progress_update.emit(100, "完成")
            self.finished.emit(True, f"共找到 {total} 个卖家")
            
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.finished.emit(False, "该物品不存在于市场")
            else:
                self.finished.emit(False, f"HTTP 错误 {e.code}: {e.reason}")
            print(f"[WM实时查询] HTTPError: {e}", flush=True)
        except urllib.error.URLError as e:
            print(f"[WM实时查询] URLError: {e}", flush=True)
            self.finished.emit(False, f"网络错误: {str(e)}")
        except TimeoutError as e:
            print(f"[WM实时查询] TimeoutError: {e}", flush=True)
            self.finished.emit(False, f"网络超时: {str(e)}")
        except json.JSONDecodeError:
            print(f"[WM实时查询] JSONDecodeError", flush=True)
            self.finished.emit(False, "数据解析错误")
        except Exception as e:
            print(f"[WM实时查询] 未知异常: {type(e).__name__}: {e}", flush=True)
            print(f"  物品: {self._en_name}, Slug: {self._slug}")
            print(traceback.format_exc())
            self.finished.emit(False, f"未知错误: {type(e).__name__}: {e}")
        finally:
            socket.setdefaulttimeout(_prev_timeout)
    
    def _parse_order(self, order):
        """Parse a single order dict into a flat dict"""
        user_data = order.get('user', {})
        item_raw = order.get('item')
        
        # Reputation - can be int or dict
        reputation = user_data.get('reputation', 0)
        if isinstance(reputation, dict):
            reputation = reputation.get('level', 0)
        
        # Username
        username = user_data.get('ingame_name') or user_data.get('ingameName', 'Unknown')
        
        # Item level - try multiple sources
        item_level = 0
        if isinstance(item_raw, dict):
            item_level = self._safe_int(item_raw.get('mod_rank', item_raw.get('modRank', 0)))
        if item_level == 0:
            item_level = self._safe_int(order.get('mod_rank', order.get('modRank', 0)))
        if item_level == 0:
            item_level = self._safe_int(order.get('rank', 0))
        
        return {
            'username': str(username),
            'status': str(user_data.get('status', 'offline')),
            'platinum': self._safe_int(order.get('platinum', 0)),
            'quantity': self._safe_int(order.get('quantity', 1)),
            'item_level': item_level,
            'reputation': self._safe_int(reputation),
            'en_name': str(self._en_name)
        }
    
    @staticmethod
    def _safe_int(value, default=0):
        """Safely convert to int, returning default on failure"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default