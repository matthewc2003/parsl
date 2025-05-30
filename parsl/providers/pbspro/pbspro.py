import json
import logging
import os
import time

from parsl.jobs.states import JobState, JobStatus
from parsl.launchers import SingleNodeLauncher
from parsl.providers.errors import SubmitException
from parsl.providers.pbspro.template import template_string
from parsl.providers.torque.torque import TorqueProvider, translate_table

logger = logging.getLogger(__name__)


class PBSProProvider(TorqueProvider):
    """PBS Pro Execution Provider

    Parameters
    ----------
    account : str
        Account the job will be charged against.
    queue : str
        Queue to request blocks from.
    nodes_per_block : int
        Nodes to provision per block.
    cpus_per_node : int
        CPUs to provision per node.
    init_blocks : int
        Number of blocks to provision at the start of the run. Default is 1.
    min_blocks : int
        Minimum number of blocks to maintain. Default is 0.
    max_blocks : int
        Maximum number of blocks to maintain.
    parallelism : float
        Ratio of provisioned task slots to active tasks. A parallelism value of 1 represents aggressive
        scaling where as many resources as possible are used; parallelism close to 0 represents
        the opposite situation in which as few resources as possible (i.e., min_blocks) are used.
    walltime : str
        Walltime requested per block in HH:MM:SS.
    scheduler_options : str
        String to prepend to the #PBS blocks in the submit script to the scheduler.
    select_options : str
        String to append to the #PBS -l select block in the submit script to the scheduler. This can be used to
        specify ngpus.
    worker_init : str
        Command to be run before starting a worker, such as 'module load Anaconda; source activate env'.
    launcher : Launcher
        Launcher for this provider. The default is
        :class:`~parsl.launchers.SingleNodeLauncher`.
    """
    def __init__(self,
                 account=None,
                 queue=None,
                 scheduler_options='',
                 select_options='',
                 worker_init='',
                 nodes_per_block=1,
                 cpus_per_node=1,
                 init_blocks=1,
                 min_blocks=0,
                 max_blocks=1,
                 parallelism=1,
                 launcher=SingleNodeLauncher(),
                 walltime="00:20:00",
                 cmd_timeout=120):
        super().__init__(account,
                         queue,
                         scheduler_options,
                         worker_init,
                         nodes_per_block,
                         init_blocks,
                         min_blocks,
                         max_blocks,
                         parallelism,
                         launcher,
                         walltime,
                         cmd_timeout=cmd_timeout)

        self.template_string = template_string
        self._label = 'pbspro'
        self.cpus_per_node = cpus_per_node
        self.select_options = select_options

    def _status(self):
        '''Returns the status list for a list of job_ids

        Args:
              self

        Returns:
              [status...] : Status list of all jobs
        '''

        job_ids = list(self.resources.keys())
        job_id_list = ' '.join(self.resources.keys())

        jobs_missing = list(self.resources.keys())

        retcode, stdout, stderr = self.execute_wait("qstat -f -F json {0}".format(job_id_list))

        # If qstat failed do not update job state
        if retcode != 0:
            logger.warning("qstat failed with retcode:%s STDOUT:%s STDERR:%s",
                           retcode,
                           stdout.strip(),
                           stderr.strip())
            return

        job_statuses = json.loads(stdout)

        if 'Jobs' in job_statuses:
            for job_id, job in job_statuses['Jobs'].items():
                for long_job_id in job_ids:
                    if long_job_id.startswith(job_id):
                        logger.debug('coerced job_id %s -> %s', job_id, long_job_id)
                        job_id = long_job_id
                        break

                job_state = job.get('job_state', JobState.UNKNOWN)
                state = translate_table.get(job_state, JobState.UNKNOWN)
                self.resources[job_id]['status'] = JobStatus(state,
                                                             stdout_path=self.resources[job_id]['job_stdout_path'],
                                                             stderr_path=self.resources[job_id]['job_stderr_path'])
                jobs_missing.remove(job_id)

        # squeue does not report on jobs that are not running. So we are filling in the
        # blanks for missing jobs, we might lose some information about why the jobs failed.
        for missing_job in jobs_missing:
            self.resources[missing_job]['status'] = JobStatus(JobState.COMPLETED,
                                                              stdout_path=self.resources[missing_job]['job_stdout_path'],
                                                              stderr_path=self.resources[missing_job]['job_stderr_path'])

    def submit(self, command, tasks_per_node, job_name="parsl"):
        """Submits the command job.

        Parameters
        ----------
        command : str
            Command to be executed on the remote side.
        tasks_per_node : int
            Command invocations to be launched per node.
        job_name : str
            Identifier for job.

        Returns
        -------
        None
            If at capacity and cannot provision more
        job_id : str
            Identifier for the job
        """

        job_name = "{0}.{1}".format(job_name, time.time())

        assert self.script_dir, "Expected script_dir to be set"
        script_path = os.path.join(self.script_dir, job_name)
        script_path = os.path.abspath(script_path)
        job_stdout_path = script_path + ".stdout"
        job_stderr_path = script_path + ".stderr"

        logger.debug("Requesting {} nodes_per_block, {} tasks_per_node".format(
            self.nodes_per_block, tasks_per_node)
        )

        job_config = {}
        job_config["submit_script_dir"] = self.script_dir
        job_config["nodes_per_block"] = self.nodes_per_block
        job_config["ncpus"] = self.cpus_per_node
        job_config["walltime"] = self.walltime
        job_config["scheduler_options"] = self.scheduler_options
        job_config["worker_init"] = self.worker_init
        job_config["user_script"] = command
        job_config["job_stdout_path"] = job_stdout_path
        job_config["job_stderr_path"] = job_stderr_path

        # Add a colon to select_options if one isn't included
        if self.select_options and not self.select_options.startswith(":"):
            self.select_options = ":" + self.select_options

        job_config["select_options"] = self.select_options

        # Wrap the command
        job_config["user_script"] = self.launcher(command,
                                                  tasks_per_node,
                                                  self.nodes_per_block)

        logger.debug("Writing submit script")
        self._write_submit_script(self.template_string, script_path, job_name, job_config)

        submit_options = ''
        if self.queue is not None:
            submit_options = '{0} -q {1}'.format(submit_options, self.queue)
        if self.account is not None:
            submit_options = '{0} -A {1}'.format(submit_options, self.account)

        launch_cmd = "qsub {0} {1}".format(submit_options, script_path)
        retcode, stdout, stderr = self.execute_wait(launch_cmd)

        job_id = None
        if retcode == 0:
            for line in stdout.split('\n'):
                if line.strip():
                    job_id = line.strip()
                    self.resources[job_id] = {'job_id': job_id,
                                              'status': JobStatus(JobState.PENDING),
                                              'job_stdout_path': job_stdout_path,
                                              'job_stderr_path': job_stderr_path,
                                              }
        else:
            message = f"Submit command '{launch_cmd}' failed"
            logger.error(
                f"{message}\n"
                f" Return code: {retcode}\n"
                f" STDOUT: {stdout.strip()}\n"
                f" STDERR: {stderr.strip()}"
            )
            raise SubmitException(
                job_name=job_name,
                message=message,
                stdout=stdout,
                stderr=stderr,
            )

        return job_id

    @property
    def status_polling_interval(self):
        return 60
