import numpy as np

from collections import deque

class EmptyPositionQueueException(Exception):
    pass

class PyramidPositioning:
    def __init__(self, asset_id,  asset_initial_price: float, asset_total_target_pct: float,
                 step_pct_increase: float = 0.01, n_steps: int = 5) -> None:
        self.asset_id = asset_id
        self.asset_initial_price = asset_initial_price
        self.asset_total_target_pct = asset_total_target_pct
        self.step_pct_increase = step_pct_increase
        self.n_steps = n_steps

        # Generate target price for first buy
        self.asset_target_price = self._get_new_target_price(
            asset_initial_price)
        
        self._pct_queue = deque(np.linspace(0, asset_total_target_pct, n_steps+1)[1:]) 

    def get_allocation(self, asset_current_price: float) -> float:
        if len(self._pct_queue) == 0:
            raise EmptyPositionQueueException("No allocation budget left.")
            
        if asset_current_price >= self.asset_target_price:
            return self._pct_queue.popleft()
        return 0.0

    def update_target_price(self, current_price: float) -> None:
        self.asset_target_price = self._get_new_target_price(
            current_price)

    def _get_new_target_price(self, current_price: float) -> float:
        return current_price * (1.0 + self.step_pct_increase)
    
    
class PyramidDownPositioning:
    def __init__(self, asset_id, buy_price: float, full_allocation_pct, upside_start_sell_pct =50, upside_finish_sell_pct = 10, steps_down = 5):
        trigger_pct = np.linspace(buy_price * (1+ upside_start_sell_pct/100.0),buy_price * (1+ upside_finish_sell_pct/100.0), steps_down+1)[:-1]
        allocation_pct = (np.linspace(1, 0, steps_down+1)*full_allocation_pct)[1:]
        
        # print(trigger_pct)
        # print(allocation_pct)
        self.asset_id = asset_id

        self.is_triggered = False
        self.full_allocation_pct = full_allocation_pct
        self.upside_start_sell_pct = upside_start_sell_pct
        self.buy_price = buy_price
        self._pct_queue =[(t,a) for t,a in zip(trigger_pct, allocation_pct)][::-1]
        
        
    def update_allocation(self, asset_current_price: float) -> float:
        
        # Trigger is not set yet, but price exceeded the minimum threshold to start selling on way down
        if (not self.is_triggered) and (asset_current_price > self.buy_price*(1+self.upside_start_sell_pct/100.0)):
            self.is_triggered = True
            return -1.0 # no need to sell yet, just a trigger
        
        if not self._pct_queue:
            return -1.0
        
        threshold, allocation = self._pct_queue[-1]
        if self.is_triggered and asset_current_price < threshold:
            self._pct_queue.pop()
            return allocation
        
        return -1.0
            
        
        
    
        
        
    
        
    
    

if __name__ == "__main__":
    pp = PyramidDownPositioning(asset_id = "TSLA", buy_price = 10, full_allocation_pct = 0.5)
    print(pp._pct_queue)
    
    print(pp.update_allocation(asset_current_price=11))
    print(pp.update_allocation(asset_current_price=17))
    print(pp.update_allocation(asset_current_price=15))
    print(pp.update_allocation(asset_current_price=14))
    print(pp.update_allocation(asset_current_price=15))
    print(pp.update_allocation(asset_current_price=12))
    print(pp.update_allocation(asset_current_price=11))
    print(pp.update_allocation(asset_current_price=10))
    
    # pp = PyramidPositioning(asset_id = "TSLA", asset_initial_price=10, asset_total_target_pct=0.2, step_pct_increase=0.01, n_steps=5)
    # print(pp._pct_queue)
    # print(pp.get_allocation(asset_current_price = 11))
    # print(pp._pct_queue)
    # pp.update_target_price(current_price=11)
    # print(pp.asset_target_price)
    # print(pp.get_allocation(asset_current_price = 12))
    # pp.update_target_price(current_price=12)
    # print(pp.asset_target_price)
    # print(pp._pct_queue)
    # print(pp.get_allocation(asset_current_price = 15))
    # print(pp.get_allocation(asset_current_price = 17))
    # print(pp.get_allocation(asset_current_price = 20))
    # print(pp.get_allocation(asset_current_price = 25))
    
