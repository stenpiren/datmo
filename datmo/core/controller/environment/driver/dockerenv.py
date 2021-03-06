import ast
import os
import json
import subprocess
import platform
from io import open
try:
    to_unicode = unicode
except NameError:
    to_unicode = str
try:

    def to_bytes(val):
        return bytes(val)

    to_bytes("test")
except TypeError:

    def to_bytes(val):
        return bytes(val, "utf-8")

    to_bytes("test")
from docker import DockerClient
from docker import errors

from datmo.core.util.i18n import get as __
from datmo.core.util.exceptions import (
    PathDoesNotExist, EnvironmentInitFailed, EnvironmentExecutionError,
    FileAlreadyExistsError, EnvironmentRequirementsCreateError,
    EnvironmentImageNotFound, EnvironmentContainerNotFound,
    GPUSupportNotEnabled, EnvironmentDoesNotExist)
from datmo.core.controller.environment.driver import EnvironmentDriver

docker_config_filepath = os.path.join(
    os.path.split(__file__)[0], "config", "docker.json")


class DockerEnvironmentDriver(EnvironmentDriver):
    """
    This EnvironmentDriver handles environment management in the project using docker

    Parameters
    ----------
    filepath : str, optional
        home filepath for project
        (default is empty)
    docker_execpath : str, optional
        execution path for docker
        (default is "docker" which defers to system)
    docker_socket : str, optional
        socket path to docker daemon to connect
        (default is None, this takes the default path for the system)

    Attributes
    ----------
    filepath : str
        home filepath for project
    docker_execpath : str
        docker execution path for the system
    docker_socket : str
        specific socket for docker
        (default is None, which means system default is used by docker)
    client : DockerClient
        docker python api client
    cpu_prefix : list
        list of strings for the prefix command for all docker commands
    info : dict
        information about the docker daemon connection
    is_connected : bool
        True if connected to daemon else False
    type : str
        type of EnvironmentDriver
    """

    def __init__(self,
                 filepath="",
                 docker_execpath="docker",
                 docker_socket=None):
        super(DockerEnvironmentDriver, self).__init__()
        if not docker_socket:
            if platform.system() != "Windows":
                docker_socket = "unix:///var/run/docker.sock"
        self.filepath = filepath
        # Check if filepath exists
        if not os.path.exists(self.filepath):
            raise PathDoesNotExist(
                __("error",
                   "controller.environment.driver.docker.__init__.dne",
                   filepath))
        self.docker_execpath = docker_execpath
        self.docker_socket = docker_socket
        if self.docker_socket:
            self.client = DockerClient(base_url=self.docker_socket)
            self.prefix = [self.docker_execpath, "-H", self.docker_socket]
        else:
            self.client = DockerClient()
            self.prefix = [self.docker_execpath]
        self.is_connected = False
        self._is_initialized = self.is_initialized
        self.type = "docker"
        with open(docker_config_filepath) as f:
            self.docker_config = json.load(f)

    @property
    def is_initialized(self):
        # TODO: Check if Docker is up and running
        if self.is_connected:
            self._is_initialized = True
            return self._is_initialized
        self._is_initialized = False
        return self._is_initialized

    # running daemon needed
    def init(self):
        # TODO: Fill in to start up Docker
        # Startup Docker
        try:
            pass
        except Exception as e:
            raise EnvironmentExecutionError(
                __("error", "controller.environment.driver.docker.init",
                   str(e)))
        # Initiate Docker execution
        try:
            self.info = self.client.info()
            self.is_connected = True if self.info["Images"] != None else False
        except Exception:
            raise EnvironmentInitFailed(
                __("error", "controller.environment.driver.docker.__init__",
                   platform.system()))
        return True

    def get_supported_environments(self):
        # To get the current environments
        return self.docker_config["supported_environments"]

    def setup(self, options, definition_path):
        name = options.get("name", None)
        available_environments = self.get_supported_environments()
        # Validate that the name exists
        if not name or name not in [n for n, _ in available_environments]:
            raise EnvironmentDoesNotExist(
                __("error", "controller.environment.driver.docker.setup.dne",
                   name))

        # Validate the given definition path exists
        if not os.path.isdir(definition_path):
            raise PathDoesNotExist()
        # To setup the environment definition file
        definition_filepath = os.path.join(definition_path, "Dockerfile")
        with open(definition_filepath, "wb") as f:
            f.write(to_bytes("FROM datmo/%s\n\n" % name))
        return True

    def create(self, path=None, output_path=None):
        if not path:
            path = os.path.join(self.filepath, "Dockerfile")
        if not output_path:
            directory, filename = os.path.split(path)
            output_path = os.path.join(directory, "datmo" + filename)
        if not os.path.isfile(path):
            raise EnvironmentDoesNotExist(
                __("error", "controller.environment.driver.docker.create.dne",
                   path))
        if os.path.isfile(output_path):
            raise FileAlreadyExistsError(
                __("error",
                   "controller.environment.driver.docker.create.exists",
                   output_path))
        success = self.create_datmo_definition(
            input_definition_path=path, output_definition_path=output_path)

        return success, path, output_path

    # running daemon needed
    def build(self, name, path):
        return self.build_image(name, path)

    # running daemon needed
    def run(self, name, options, log_filepath):
        if "gpu" in options:
            gpu_ready = self.gpu_enabled()
            if options["gpu"] is True:
                if not gpu_ready:
                    raise GPUSupportNotEnabled('nvidia')
                else:
                    options['runtime'] = 'nvidia'
            options.pop("gpu", None)
        run_return_code, run_id = self.run_container(
            image_name=name, **options)

        log_return_code, logs = self.log_container(
            run_id, filepath=log_filepath)

        final_return_code = run_return_code and log_return_code
        return final_return_code, run_id, logs

    # running daemon needed
    def stop(self, run_id, force=False):
        stop_result = self.stop_container(run_id)
        remove_run_result = self.remove_container(run_id, force=force)
        return stop_result and remove_run_result

    # running daemon needed
    def remove(self, name, force=False):
        stop_and_remove_containers_result = \
            self.stop_remove_containers_by_term(name, force=force)
        try:
            self.get_image(name)
            remove_image_result = self.remove_image(name, force=force)
        except EnvironmentImageNotFound:
            remove_image_result = True
        return stop_and_remove_containers_result and \
               remove_image_result

    def gpu_enabled(self):
        # test if this images works
        # docker run --runtime=nvidia --rm nvidia/cuda nvidia-smi
        process = subprocess.Popen(
            [
                "docker",
                "run",
                "--runtime=nvidia",
                "--rm",
                "nvidia/cuda",
                "nvidia-smi",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        stderr = stderr.decode("utf-8")
        if "Unknown runtime specified nvidia" in stderr:
            return False
        if "OCI runtime create failed" in stderr:
            return False
        if len(stderr) > 2:
            raise GPUSupportNotEnabled(stderr)

        # this may mean we're good to go.   Untested though.
        return True

    # running daemon needed
    def get_tags_for_docker_repository(self, repo_name):
        # TODO: Use more common CLI command (e.g. curl instead of wget)
        """Method to get tags for docker repositories

        Parameters
        ----------
        repo_name: str
            Docker repository name

        Returns
        -------
        list
            List of tags available for that docker repo
        """
        docker_repository_tag_cmd = "wget -q https://registry.hub.docker.com/v1/repositories/" + repo_name + "/tags -O -"
        try:
            process = subprocess.Popen(
                docker_repository_tag_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode > 0:
                raise EnvironmentExecutionError(
                    __("error",
                       "controller.environment.driver.docker.get_tags",
                       str(stderr)))
            string_repository_tags = stdout.decode().strip()
        except subprocess.CalledProcessError as e:
            raise EnvironmentExecutionError(
                __("error", "controller.environment.driver.docker.get_tags",
                   str(e)))
        repository_tags = ast.literal_eval(string_repository_tags)
        list_tag_names = []
        for repository_tag in repository_tags:
            list_tag_names.append(repository_tag["name"])
        return list_tag_names

    # running daemon needed
    def build_image(self, tag, definition_path="Dockerfile"):
        """Builds docker image

        Parameters
        ----------
        tag : str
            name to tag image with
        definition_path : str
            absolute file path to the definition

        Returns
        -------
        bool
            True if success

        Raises
        ------
        EnvironmentExecutionError

        """
        try:
            docker_shell_cmd_list = list(self.prefix)
            docker_shell_cmd_list.append("build")

            # Passing tag name for the image
            docker_shell_cmd_list.append("-t")
            docker_shell_cmd_list.append(tag)

            # Passing path of Dockerfile
            docker_shell_cmd_list.append("-f")
            docker_shell_cmd_list.append(definition_path)
            dockerfile_dirpath = os.path.split(definition_path)[0]
            docker_shell_cmd_list.append(str(dockerfile_dirpath))

            # Remove intermediate containers after a successful build
            docker_shell_cmd_list.append("--rm")
            process_returncode = subprocess.Popen(docker_shell_cmd_list).wait()
            if process_returncode == 0:
                return True
            elif process_returncode == 1:
                raise EnvironmentExecutionError(
                    __("error",
                       "controller.environment.driver.docker.build_image",
                       "Docker subprocess failed"))
        except Exception as e:
            raise EnvironmentExecutionError(
                __("error", "controller.environment.driver.docker.build_image",
                   str(e)))

    # running daemon needed
    def get_image(self, image_name):
        try:
            return self.client.images.get(image_name)
        except errors.ImageNotFound:
            raise EnvironmentImageNotFound()

    # running daemon needed
    def list_images(self, name=None, all_images=False, filters=None):
        return self.client.images.list(
            name=name, all=all_images, filters=filters)

    # running daemon needed
    def search_images(self, term):
        return self.client.images.search(term=term)

    # running daemon needed
    def remove_image(self, image_id_or_name, force=False):
        try:
            if force:
                docker_image_remove_cmd = list(self.prefix)
                docker_image_remove_cmd.extend(["rmi", "-f", image_id_or_name])
            else:
                docker_image_remove_cmd = list(self.prefix)
                docker_image_remove_cmd.extend(["rmi", image_id_or_name])
            process = subprocess.Popen(
                docker_image_remove_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode > 0:
                raise EnvironmentExecutionError(
                    __("error",
                       "controller.environment.driver.docker.remove_image",
                       str(stderr)))
        except subprocess.CalledProcessError as e:
            raise EnvironmentExecutionError(
                __("error",
                   "controller.environment.driver.docker.remove_image",
                   str(e)))
        return True

    # running daemon needed
    def remove_images(self, name=None, all=False, filters=None, force=False):
        """Remove multiple images
        """
        try:
            images = self.list_images(
                name=name, all_images=all, filters=filters)
            for image in images:
                self.remove_image(image.id, force=force)
        except Exception as e:
            raise EnvironmentExecutionError(
                __("error",
                   "controller.environment.driver.docker.remove_images",
                   str(e)))
        return True

    # running daemon needed
    def run_container(self,
                      image_name,
                      command=None,
                      ports=None,
                      name=None,
                      volumes=None,
                      mem_limit=None,
                      runtime=None,
                      detach=False,
                      stdin_open=False,
                      tty=False,
                      api=False):
        """Run Docker container with parameters given as defined below
        Parameters
        ----------
        image_name : str
            Docker image name
        command : list, optional
            List with complete user-given command (e.g. ["python3", "cool.py"])
        ports : list, optional
            Here are some example ports used for common applications.
               *  "jupyter notebook" - 8888
               *  flask API - 5000
               *  tensorboard - 6006
            An example input for the above would be ["8888:8888", "5000:5000", "6006:6006"]
            which maps the running host port (right) to that of the environment (left)
        name : str, optional
            User given name for container
        volumes : dict, optional
            Includes storage volumes for docker
            (e.g. { outsidepath1 : {"bind", containerpath2, "mode", MODE} })
        mem_limit : str, optional
            maximum amount of memory the container can use
            (these options take a positive integer, followed by a suffix of b, k, m, g, to indicate bytes, kilobytes,
            megabytes, or gigabytes. memory limit is contrained by total memory of the VM in which docker runs)
        detach : bool, optional
            True if container is to be detached else False
        stdin_open : bool, optional
            True if stdin is open else False
        tty : bool, optional
            True to connect pseudo-terminal with stdin / stdout else False
        api : bool, optional
            True if Docker python client should be used else use subprocess
        Returns
        -------
        if api=False:
        return_code: int
            integer success code of command
        container_id: str
            output container id
        if api=True & if detach=True:
        container_obj: Container
            object from Docker python api with details about container
        if api=True & if detach=False:
        logs: str
            output logs for the run function
        Raises
        ------
        EnvironmentExecutionError
             error in running the environment command
        """
        try:
            container_id = None
            if api:  # calling the docker client via the API
                # TODO: Test this out for the API (need to verify ports work)
                if detach:
                    command = " ".join(command) if command else command
                    container = \
                        self.client.containers.run(image_name, command, ports=ports,
                                                   name=name, volumes=volumes,
                                                   mem_limit=mem_limit,
                                                   detach=detach, stdin_open=stdin_open)
                    return container
                else:
                    command = " ".join(command) if command else command
                    logs = self.client.containers.run(
                        image_name,
                        command,
                        ports=ports,
                        name=name,
                        volumes=volumes,
                        mem_limit=mem_limit,
                        detach=detach,
                        stdin_open=stdin_open)
                    return logs.decode()
            else:  # if calling run function with the shell commands
                docker_shell_cmd_list = list(self.prefix)
                docker_shell_cmd_list.append("run")

                if name:
                    docker_shell_cmd_list.append("--name")
                    docker_shell_cmd_list.append(name)

                if runtime:
                    docker_shell_cmd_list.append("--runtime")
                    docker_shell_cmd_list.append(runtime)

                if mem_limit:
                    docker_shell_cmd_list.append("-m")
                    docker_shell_cmd_list.append(mem_limit)
                    docker_shell_cmd_list.append("--memory-swap")
                    docker_shell_cmd_list.append("-1")

                if stdin_open:
                    docker_shell_cmd_list.append("-i")

                if tty:
                    docker_shell_cmd_list.append("-t")

                if detach:
                    docker_shell_cmd_list.append("-d")

                # Volume
                if volumes:
                    # Mounting volumes
                    for key in list(volumes):
                        docker_shell_cmd_list.append("-v")
                        volume_mount = key + ":" + volumes[key]["bind"] + ":" + \
                                       volumes[key]["mode"]
                        docker_shell_cmd_list.append(volume_mount)

                if ports:
                    # Mapping ports
                    for mapping in ports:
                        docker_shell_cmd_list.append("-p")
                        docker_shell_cmd_list.append(mapping)

                docker_shell_cmd_list.append(image_name)
                if command:
                    docker_shell_cmd_list.extend(command)
                return_code = subprocess.call(docker_shell_cmd_list)
                if return_code != 0:
                    raise EnvironmentExecutionError(
                        __("error",
                           "controller.environment.driver.docker.run_container",
                           str(docker_shell_cmd_list)))
                list_process_cmd = list(self.prefix)
                list_process_cmd.extend(["ps", "-q", "-l"])
                process = subprocess.Popen(
                    list_process_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                stdout, stderr = process.communicate()
                if process.returncode > 0:
                    raise EnvironmentExecutionError(
                        __("error",
                           "controller.environment.driver.docker.run_container",
                           str(stderr)))
                container_id = stdout.decode().strip()
        except subprocess.CalledProcessError as e:
            raise EnvironmentExecutionError(
                __("error",
                   "controller.environment.driver.docker.run_container",
                   str(e)))
        return return_code, container_id

    # running daemon needed
    def get_container(self, container_id):
        try:
            return self.client.containers.get(container_id)
        except errors.NotFound:
            raise EnvironmentContainerNotFound()

    # running daemon needed
    def list_containers(self,
                        all=False,
                        before=None,
                        filters=None,
                        limit=-1,
                        since=None):
        return self.client.containers.list(
            all=all, before=before, filters=filters, limit=limit, since=since)

    # running daemon needed
    def stop_container(self, container_id):
        try:
            docker_container_stop_cmd = list(self.prefix)
            docker_container_stop_cmd.extend(["stop", container_id])
            process = subprocess.Popen(
                docker_container_stop_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode > 0:
                raise EnvironmentExecutionError(
                    __("error",
                       "controller.environment.driver.docker.stop_container",
                       str(stderr)))
        except subprocess.CalledProcessError as e:
            raise EnvironmentExecutionError(
                __("error",
                   "controller.environment.driver.docker.stop_container",
                   str(e)))
        return True

    # running daemon needed
    def remove_container(self, container_id, force=False):
        try:
            docker_container_remove_cmd_list = list(self.prefix)
            if force:
                docker_container_remove_cmd_list.extend(
                    ["rm", "-f", container_id])
            else:
                docker_container_remove_cmd_list.extend(["rm", container_id])
            process = subprocess.Popen(
                docker_container_remove_cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode > 0:
                raise EnvironmentExecutionError(
                    __("error",
                       "controller.environment.driver.docker.remove_container",
                       str(stderr)))
        except subprocess.CalledProcessError as e:
            raise EnvironmentExecutionError(
                __("error",
                   "controller.environment.driver.docker.remove_container",
                   str(e)))
        return True

    # running daemon needed
    def log_container(self, container_id, filepath, api=False, follow=True):
        """Log capture at a particular point `docker logs`. Can also use `--follow` for real time logs

        Parameters
        ----------
        container_id : str
            Docker container id
        filepath : str
            Filepath to store log file
        api : bool
            True to use the docker python api
        follow : bool
            Tail the output

        Returns
        -------
        return_code : str
            Process return code for the container
        logs : str
            Output logs read into a string format
        """
        # TODO: Fix function to better accomodate all logs in the same way
        if api:  # calling the docker client via the API
            with open(filepath, "wb") as log_file:
                for line in self.client.containers.get(container_id).logs(
                        stream=True):
                    log_file.write(to_bytes(line.strip() + "\n"))
        else:
            command = list(self.prefix)
            if follow:
                command.extend(["logs", "--follow", str(container_id)])
            else:
                command.extend(["logs", str(container_id)])
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, universal_newlines=True)
            with open(filepath, "wb") as log_file:
                while True:
                    output = process.stdout.readline()
                    if output == "" and process.poll() is not None:
                        break
                    if output:
                        printable_output = output.strip().replace("\x08", " ")
                        log_file.write(to_bytes(printable_output + "\n"))
            return_code = process.poll()
            with open(filepath, "rb") as log_file:
                logs = log_file.read()
                if type(logs) != str:  # handle for python 3x
                    logs = logs.decode("utf-8")
            return return_code, logs

    # running daemon needed
    def stop_remove_containers_by_term(self, term, force=False):
        """Stops and removes containers by term
        """
        # TODO: split out the find containers function from stop / remove
        try:
            running_docker_container_cmd_list = list(self.prefix)
            running_docker_container_cmd_list.extend([
                "ps", "-a", "|", "grep",
                "'%s'" % term, "|", "awk '{print $1}'"
            ])

            running_docker_container_cmd_str = str(
                " ".join(running_docker_container_cmd_list))
            process = subprocess.Popen(
                running_docker_container_cmd_str,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            out_list_cmd, err_list_cmd = process.communicate()
            if process.returncode > 0:
                raise EnvironmentExecutionError(
                    __("error",
                       "controller.environment.driver.docker.stop_remove_containers_by_term",
                       str(err_list_cmd)))
            # checking for running container id before stopping any
            if out_list_cmd:
                docker_container_stop_cmd_list = list(self.prefix)
                docker_container_stop_cmd_list = docker_container_stop_cmd_list + \
                                                 ["stop", "$("] + running_docker_container_cmd_list + \
                                                 [")"]
                docker_container_stop_cmd_str = str(
                    " ".join(docker_container_stop_cmd_list))
                process = subprocess.Popen(
                    docker_container_stop_cmd_str,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                _, _ = process.communicate()
                # rechecking for container id after stopping them to ensure no errors
                process = subprocess.Popen(
                    running_docker_container_cmd_str,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                out_list_cmd, err_list_cmd = process.communicate()
                if process.returncode > 0:
                    raise EnvironmentExecutionError(
                        __("error",
                           "controller.environment.driver.docker.stop_remove_containers_by_term",
                           str(err_list_cmd)))
                if out_list_cmd:
                    docker_container_remove_cmd_list = list(self.prefix)
                    if force:
                        docker_container_remove_cmd_list = docker_container_remove_cmd_list + \
                                                           ["rm", "-f", "$("] + running_docker_container_cmd_list + \
                                                           [")"]
                    else:
                        docker_container_remove_cmd_list = docker_container_remove_cmd_list + \
                                                           ["rm", "$("] + running_docker_container_cmd_list + \
                                                           [")"]
                    docker_container_remove_cmd_str = str(
                        " ".join(docker_container_remove_cmd_list))
                    process = subprocess.Popen(
                        docker_container_remove_cmd_str,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
                    _, err_list_cmd = process.communicate()
                    if process.returncode > 0:
                        raise EnvironmentExecutionError(
                            __("error",
                               "controller.environment.driver.docker.stop_remove_containers_by_term",
                               str(err_list_cmd)))
        except subprocess.CalledProcessError as e:
            raise EnvironmentExecutionError(
                __("error",
                   "controller.environment.driver.docker.stop_remove_containers_by_term",
                   str(e)))
        return True

    def create_requirements_file(self, package_manager="pip"):
        """Create python requirements txt file for the project

        Parameters
        ----------
        package_manager : str, optional
            the package manager being used during the snapshot creation

        Returns
        -------
        str
            absolute filepath for requirements file

        Raises
        ------
        EnvironmentRequirementsCreateError
            error in running package manager command to extract environment requirements
        """
        if package_manager == "pip":
            try:
                requirements_filepath = os.path.join(self.filepath,
                                                     "datmorequirements.txt")
                outfile_requirements = open(requirements_filepath, "wb")
                process = subprocess.Popen(
                    ["pip", "freeze"],
                    cwd=self.filepath,
                    stdout=outfile_requirements,
                    stderr=subprocess.PIPE)
                stdout, stderr = process.communicate()
                if process.returncode > 0:
                    raise EnvironmentRequirementsCreateError(
                        __("error",
                           "controller.environment.requirements.create",
                           str(stderr)))
            except Exception as e:
                raise EnvironmentRequirementsCreateError(
                    __("error", "controller.environment.requirements.create",
                       str(e)))
            if not os.path.isfile(requirements_filepath):
                return None
            return requirements_filepath
        else:
            raise EnvironmentRequirementsCreateError(
                __("error", "controller.environment.requirements.create",
                   "no such package manager"))

    @staticmethod
    def create_default_definition(directory, language="python3"):
        language_dockerfile = "%sDockerfile" % language
        default_dockerfile_filepath = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates",
            language_dockerfile)

        destination_dockerfile = os.path.join(directory, "Dockerfile")
        with open(default_dockerfile_filepath, "rb") as input_file:
            with open(destination_dockerfile, "wb") as output_file:
                for line in input_file:
                    if to_bytes(os.linesep) in line:
                        output_file.write(line.strip() + to_bytes("\n"))
                    else:
                        output_file.write(line.strip())
        return destination_dockerfile

    def get_default_definition_filename(self):
        return "Dockerfile"

    def get_datmo_definition_filenames(self):
        return ["datmoDockerfile", "hardware_info"]

    def get_hardware_info(self):
        # Extract hardware info of the container (currently taking from system platform)
        # TODO: extract hardware information directly from the container
        (system, node, release, version, machine, processor) = platform.uname()
        return {
            'system': system,
            'node': node,
            'release': release,
            'version': version,
            'machine': machine,
            'processor': processor
        }

    @staticmethod
    def create_datmo_definition(input_definition_path, output_definition_path):
        """
        Creates a datmo dockerfiles to run at the output path specified
        """
        datmo_base_dockerfile_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates",
            "baseDockerfile")

        # Combine dockerfiles
        with open(input_definition_path, "rb") as input_file:
            with open(datmo_base_dockerfile_path, "rb") as datmo_base_file:
                with open(output_definition_path, "wb") as output_file:
                    for line in input_file:
                        if to_bytes(os.linesep) in line:
                            output_file.write(line.strip() + to_bytes("\n"))
                        else:
                            output_file.write(line.strip())
                    for line in datmo_base_file:
                        if to_bytes(os.linesep) in line:
                            output_file.write(line.strip() + to_bytes("\n"))
                        else:
                            output_file.write(line.strip())
        return True
