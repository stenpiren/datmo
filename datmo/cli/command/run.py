from __future__ import print_function

import os
import shlex
import platform
from datetime import datetime
# https://stackoverflow.com/questions/11301138/how-to-check-if-variable-is-string-with-python-2-and-3-compatibility/11301392?utm_medium=organic&utm_source=google_rich_qa&utm_campaign=google_rich_qa
try:
    basestring
except NameError:
    basestring = str

from datmo.core.util.i18n import get as __
from datmo.core.util.misc_functions import mutually_exclusive, printable_object
from datmo.cli.command.project import ProjectCommand
from datmo.core.controller.task import TaskController
from datmo.core.controller.snapshot import SnapshotController
from datmo.cli.driver.helper import Helper
from datmo.core.entity.task import Task as CoreTask
from datmo.core.util.exceptions import InvalidArgumentType
from datmo.core.util.misc_functions import prettify_datetime, format_table


class RunObject():
    """Run is an object to enable user access to properties

    Parameters
    ----------
    task_entity : datmo.core.entity.task.Task
        core task entity to reference

    Attributes
    ----------
    id : str
        the id of task associated with run
    model_id : str
        the parent model id for the entity
    session_id : str
        id of session associated with run
    before_snapshot_id : str
        id of snapshot associated before the run
    after_snapshot_id : str
        id of snapshot associated after the run
    command : str
        command that is used by the run
    status : str or None
        status of the current run
    start_time : datetime.datetime or None
        timestamp for the beginning time of the run
    end_time : datetime.datetime or None
        timestamp for the end time of the run
    duration : float or None
        delta in seconds between start and end times
    logs : str or None
        string output of logs
    config : dict
        dictionary containing input or output configs from the run
    results : dict
        dictionary containing output results from the run
    files : list
        returns list of file objects for the run in read mode

    Methods
    -------
    get_files(mode="r")
        Returns a list of file objects for the run

    Raises
    ------
    InvalidArgumentType
    """

    def __init__(self, task_entity):
        if not isinstance(task_entity, CoreTask):
            raise InvalidArgumentType()

        self._core_task = task_entity

        self.id = self._core_task.id
        self.model_id = self._core_task.model_id
        self.session_id = self._core_task.session_id
        self.created_at = self._core_task.created_at
        self.before_snapshot_id = task_entity.before_snapshot_id
        self.after_snapshot_id = task_entity.after_snapshot_id

        # Execution definition
        self.command = self._core_task.command
        self._config = {}

        # Run parameters
        self._status = self._core_task.status
        self._start_time = self._core_task.start_time
        self._end_time = self._core_task.end_time
        self._duration = self._core_task.duration

        # Outputs
        self._logs = self._core_task.logs
        self._results = {}
        self._files = None

    @property
    def status(self):
        self._core_task = self.__get_core_task()
        self._status = self._core_task.status
        return self._status

    @property
    def start_time(self):
        self._core_task = self.__get_core_task()
        self._start_time = self._core_task.start_time
        return self._start_time

    @property
    def end_time(self):
        self._core_task = self.__get_core_task()
        self._end_time = self._core_task.end_time
        return self._end_time

    @property
    def duration(self):
        self._core_task = self.__get_core_task()
        self._duration = self._core_task.duration
        return self._duration

    @property
    def logs(self):
        self._core_task = self.__get_core_task()
        self._logs = self._core_task.logs
        return self._logs

    @property
    def config(self):
        self._core_snapshot = self.__get_core_snapshot()
        self._config = self._core_snapshot.config
        return self._config

    @property
    def results(self):
        self._core_task = self.__get_core_task()
        self._results = {}
        if self._core_task.results is not None:
            self._results = self._core_task.results
        return self._results

    @property
    def files(self):
        self._files = self.get_files()
        return self._files

    def __get_core_task(self):
        """Returns the latest core task object for id

        Returns
        -------
        datmo.core.entity.task.Task
            core task object fo the task
        """
        task_controller = TaskController()
        return task_controller.get(self.id)

    def __get_core_snapshot(self):
        """Returns the latest core snapshot object for id

        Returns
        -------
        datmo.core.entity.snapshot.Snapshot
            core snapshot object for the Snapshot
        """
        snapshot_controller = SnapshotController()
        snapshot_id = self.after_snapshot_id if self.after_snapshot_id else self.before_snapshot_id
        snapshot_obj = snapshot_controller.get(snapshot_id)
        return snapshot_obj

    def get_files(self, mode="r"):
        """Returns a list of file objects for the task

        Parameters
        ----------
        mode : str
            file object mode
            (default is "r" which signifies read mode)

        Returns
        -------
        list
            list of file objects associated with the task
        """
        snapshot_controller = SnapshotController()
        self._core_snapshot = self.__get_core_snapshot()
        return snapshot_controller.get_files(self._core_snapshot.id, mode=mode)

    def __eq__(self, other):
        return self.id == other.id if other else False

    def __str__(self):
        final_str = '\033[94m' + "run " + self.id + "\n" + '\033[0m'
        table_data = []
        if self.session_id:
            table_data.append(["Session", "-> " + self.session_id])
        if self.status:
            table_data.append(["Status", "-> " + self.status])
        if self.start_time:
            table_data.append(
                ["Start Time", "-> " + prettify_datetime(self.start_time)])
        if self.end_time:
            table_data.append(
                ["End Time", "-> " + prettify_datetime(self.end_time)])
        if self.duration:
            table_data.append(
                ["Duration", "-> " + str(self.duration) + " seconds"])
        # Outputs
        if self.logs:
            table_data.append(
                ["Logs", "-> Use task log to view or download logs"])
        if self.config:
            table_data.append(["Config", "-> " + str(self.config)])
        if self.results:
            table_data.append(["Results", "-> " + str(self.results)])
        if not self.files:
            table_data.append(["Files", "-> None"])
        else:
            table_data.append(["Files", "-> " + self.files[0].name])
            if len(list(self.files)) > 1:
                for f in self.files[1:]:
                    table_data.append(["     ", "-> " + f.name])
        final_str = final_str + format_table(table_data)
        final_str = final_str + "\n" + "    " + self.command + "\n" + "\n"
        return final_str

    def __repr__(self):
        return self.__str__()


class RunCommand(ProjectCommand):
    def __init__(self, cli_helper):
        super(RunCommand, self).__init__(cli_helper)

    @Helper.notify_environment_active(TaskController)
    @Helper.notify_no_project_found
    def run(self, **kwargs):
        self.cli_helper.echo(__("info", "cli.task.run"))
        # Create controllers
        self.task_controller = TaskController()
        self.snapshot_controller = SnapshotController()
        # Create input dictionaries
        snapshot_dict = {}

        # Environment
        if kwargs.get("environment_id", None) or kwargs.get(
                "environment_paths", None):
            mutually_exclusive_args = ["environment_id", "environment_paths"]
            mutually_exclusive(mutually_exclusive_args, kwargs, snapshot_dict)
        task_dict = {
            "ports": kwargs['ports'],
            "interactive": kwargs['interactive'],
            "mem_limit": kwargs['mem_limit']
        }
        if not isinstance(kwargs['cmd'], list):
            if platform.system() == "Windows":
                task_dict['command'] = kwargs['cmd']
            elif isinstance(kwargs['cmd'], basestring):
                task_dict['command_list'] = shlex.split(kwargs['cmd'])
        else:
            task_dict['command_list'] = kwargs['cmd']

        # Create the task object
        task_obj = self.task_controller.create()
        try:
            # Pass in the task to run
            updated_task_obj = self.task_controller.run(
                task_obj.id, snapshot_dict=snapshot_dict, task_dict=task_dict)
        except Exception as e:
            self.logger.error("%s %s" % (e, task_dict))
            self.cli_helper.echo("%s" % e)
            self.cli_helper.echo(__("error", "cli.task.run", task_obj.id))
            return False

        self.cli_helper.echo(
            __("info", "cli.task.run.complete", updated_task_obj.id))
        return updated_task_obj

    @Helper.notify_no_project_found
    def ls(self, **kwargs):
        # Create controllers
        self.task_controller = TaskController()
        self.snapshot_controller = SnapshotController()
        session_id = kwargs.get('session_id',
                                self.task_controller.current_session.id)
        print_format = kwargs.get('format', "table")
        download = kwargs.get('download', None)
        download_path = kwargs.get('download_path', None)
        # Get all task meta information
        task_objs = self.task_controller.list(
            session_id, sort_key="created_at", sort_order="descending")
        header_list = [
            "id", "command", "status", "config", "results", "created at"
        ]
        item_dict_list = []
        run_obj_list = []
        for task_obj in task_objs:
            # Create a new Run Object from Task Object
            run_obj = RunObject(task_obj)
            task_results_printable = printable_object(str(run_obj.results))
            snapshot_config_printable = printable_object(str(run_obj.config))
            item_dict_list.append({
                "id": run_obj.id,
                "command": run_obj.command,
                "status": run_obj.status,
                "config": snapshot_config_printable,
                "results": task_results_printable,
                "created at": prettify_datetime(run_obj.created_at)
            })
            run_obj_list.append(run_obj)
        if download:
            if not download_path:
                # download to current working directory with timestamp
                current_time = datetime.utcnow()
                epoch_time = datetime.utcfromtimestamp(0)
                current_time_unix_time_ms = (
                    current_time - epoch_time).total_seconds() * 1000.0
                download_path = os.path.join(
                    os.getcwd(), "run_ls_" + str(current_time_unix_time_ms))
            self.cli_helper.print_items(
                header_list,
                item_dict_list,
                print_format=print_format,
                output_path=download_path)
            return task_objs
        self.cli_helper.print_items(
            header_list, item_dict_list, print_format=print_format)
        return run_obj_list
