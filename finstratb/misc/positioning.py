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
    
    

if __name__ == "__main__":
    pp = PyramidPositioning(asset_id = "TSLA", asset_initial_price=10, asset_total_target_pct=0.2, step_pct_increase=0.01, n_steps=5)
    print(pp._pct_queue)
    print(pp.get_allocation(asset_current_price = 11))
    print(pp._pct_queue)
    pp.update_target_price(current_price=11)
    print(pp.asset_target_price)
    print(pp.get_allocation(asset_current_price = 12))
    pp.update_target_price(current_price=12)
    print(pp.asset_target_price)
    print(pp._pct_queue)
    print(pp.get_allocation(asset_current_price = 15))
    print(pp.get_allocation(asset_current_price = 17))
    print(pp.get_allocation(asset_current_price = 20))
    print(pp.get_allocation(asset_current_price = 25))
    
