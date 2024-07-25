import copy
import random
from typing import Dict, List

from parsl.executors.high_throughput.manager_record import ManagerRecord


class ManagerSelectorBase:

    def sort_managers(self, ready_managers: Dict[bytes, ManagerRecord], manager_list: List[bytes]) -> List[bytes]:
        raise NotImplementedError


class ManagerSelectorRandom(ManagerSelectorBase):

    def __init__(self):
        pass

    def sort_managers(self, ready_managers: Dict[bytes, ManagerRecord], manager_list: List[bytes]) -> List[bytes]:
        c_manager_list = copy.copy(manager_list)
        random.shuffle(c_manager_list)
        return c_manager_list


class ManagerSelectorByBlockId(ManagerSelectorBase):

    def __init_(self):
        pass

    def sort_managers(self, ready_managers: Dict[bytes, ManagerRecord], manager_list: List[bytes]) -> List[bytes]:
        def get_block_id(m: bytes) -> str:
            temp = ready_managers[m]['block_id']
            return temp if temp is not None else ""

        return sorted(copy.copy(manager_list), key=get_block_id, reverse=True)
