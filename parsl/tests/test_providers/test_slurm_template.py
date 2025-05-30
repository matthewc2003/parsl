import logging
import random
from unittest import mock

import pytest

from parsl.providers import SlurmProvider


@pytest.mark.local
def test_submit_script_basic(tmp_path):
    """Test slurm resources table"""

    provider = SlurmProvider(
        partition="debug"
    )
    provider.script_dir = tmp_path
    job_id = str(random.randint(55000, 59000))
    provider.execute_wait = mock.MagicMock(spec=SlurmProvider.execute_wait)
    provider.execute_wait.return_value = (0, f"Submitted batch job {job_id}", "")
    result_job_id = provider.submit("test", tasks_per_node=1)
    assert job_id == result_job_id
    provider.execute_wait.assert_called()
    assert job_id in provider.resources

    job_info = provider.resources[job_id]
    assert "job_stdout_path" in job_info
    assert "job_stderr_path" in job_info
