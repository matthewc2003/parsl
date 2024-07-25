import pytest

import parsl
from parsl.app.app import bash_app, python_app
from parsl.channels import LocalChannel
from parsl.config import Config
from parsl.configs.local_threads import config
from parsl.executors import HighThroughputExecutor
from parsl.executors.high_throughput.manager_selector import (
    ManagerSelectorBase,
    ManagerSelectorRandom,
)
from parsl.providers import LocalProvider
from parsl.usage_tracking.levels import LEVEL_1


def local_config():
    return Config(
        executors=[
            HighThroughputExecutor(
                label="htex_local",
                max_workers_per_node=1,
                manager_selector=ManagerSelectorRandom(),
                provider=LocalProvider(
                    channel=LocalChannel(),
                    init_blocks=4,
                    max_blocks=4,
                    min_blocks=4
                ),
            )
        ],
        usage_tracking=LEVEL_1,
    )


@parsl.python_app
def get_worker_pid():
    import os
    return os.getpid()


@pytest.mark.local
def test_random_selection():
    pids = []
    for i in range(10):
        future = get_worker_pid()
        pids.append(future.result())
        print(future.result())

    assert len(set(pids)) != 1
