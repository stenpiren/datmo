from datmo.core.util.i18n import get as __
from datmo.cli.command.project import ProjectCommand
from datmo.core.util.spinner import Spinner
from datmo.core.util.misc_functions import mutually_exclusive
from datmo.cli.driver.helper import Helper
from datmo.core.controller.task import TaskController


class WorkspaceCommand(ProjectCommand):
    def __init__(self, cli_helper):
        super(WorkspaceCommand, self).__init__(cli_helper)
        self.spinner = Spinner()

    @Helper.notify_environment_active(TaskController)
    @Helper.notify_no_project_found
    def notebook(self, **kwargs):
        self.task_controller = TaskController()
        self.cli_helper.echo(__("info", "cli.workspace.notebook"))
        # Creating input dictionaries
        snapshot_dict = {}

        # Environment
        if kwargs.get("environment_id", None) or kwargs.get(
                "environment_paths", None):
            mutually_exclusive_args = ["environment_id", "environment_paths"]
            mutually_exclusive(mutually_exclusive_args, kwargs, snapshot_dict)

        task_dict = {
            "ports": ["8888:8888"],
            "command_list": ["jupyter", "notebook"],
            "mem_limit": kwargs["mem_limit"]
        }

        # Pass in the task
        try:
            self.spinner.start()
            # Create the task object
            task_obj = self.task_controller.create()
            updated_task_obj = self.task_controller.run(
                task_obj.id, snapshot_dict=snapshot_dict, task_dict=task_dict)
        except Exception as e:
            self.logger.error("%s %s" % (e, task_dict))
            self.cli_helper.echo(
                __("error", "cli.workspace.notebook", task_obj.id))
            return False
        finally:
            self.spinner.stop()

        self.cli_helper.echo(
            "Ran notebook with task id: %s" % updated_task_obj.id)

        return updated_task_obj