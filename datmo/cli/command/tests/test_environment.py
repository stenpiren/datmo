"""
Tests for EnvironmentCommand
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import glob
import uuid
import tempfile
import shutil
import platform
from argparse import ArgumentError
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

from datmo.cli.driver.helper import Helper
from datmo.cli.command.environment import EnvironmentCommand
from datmo.cli.command.project import ProjectCommand
from datmo.core.util.misc_functions import pytest_docker_environment_failed_instantiation
from datmo.config import Config
from datmo.core.util.exceptions import EnvironmentDoesNotExist

# provide mountable tmp directory for docker
tempfile.tempdir = "/tmp" if not platform.system() == "Windows" else None
test_datmo_dir = os.environ.get('TEST_DATMO_DIR', tempfile.gettempdir())


class TestEnvironmentCommand():
    def setup_class(self):
        self.temp_dir = tempfile.mkdtemp(dir=test_datmo_dir)
        self.cli_helper = Helper()
        Config().set_home(self.temp_dir)

    def teardown_class(self):
        pass

    def __set_variables(self):
        self.project_command = ProjectCommand(self.cli_helper)
        self.project_command.parse(
            ["init", "--name", "foobar", "--description", "test model"])

        @self.project_command.cli_helper.input("\n")
        def dummy(self):
            return self.project_command.execute()

        dummy(self)
        self.environment_command = EnvironmentCommand(self.cli_helper)

    def test_environment_setup_parameter(self):
        # Setup the environement by passing name
        self.__set_variables()
        definition_filepath = os.path.join(self.temp_dir, "datmo_environment",
                                           "Dockerfile")

        # Test pass with correct input
        test_name = "xgboost:cpu"
        self.environment_command.parse(
            ["environment", "setup", "--name", test_name])
        result = self.environment_command.execute()

        assert result
        assert os.path.isfile(definition_filepath)
        assert "FROM datmo/xgboost:cpu" in open(definition_filepath,
                                                "r").read()

        # Test fail with wrong input
        test_name = "random"
        self.environment_command.parse(
            ["environment", "setup", "--name", test_name])
        result = self.environment_command.execute()
        assert not result

    def test_environment_setup_prompt(self):
        # Setup the environement by passing name
        self.__set_variables()
        definition_filepath = os.path.join(self.temp_dir, "datmo_environment",
                                           "Dockerfile")

        # Test success with correct prompt input using numbers
        self.environment_command.parse(["environment", "setup"])

        @self.environment_command.cli_helper.input("1\n")
        def dummy(self):
            return self.environment_command.execute()

        result = dummy(self)

        assert result
        assert os.path.isfile(definition_filepath)
        assert "FROM datmo/xgboost:cpu" in open(definition_filepath,
                                                "r").read()

        # Test success with correct prompt input using string
        test_name = "xgboost:cpu"
        self.environment_command.parse(["environment", "setup"])

        @self.environment_command.cli_helper.input(test_name + "\n")
        def dummy(self):
            return self.environment_command.execute()

        result = dummy(self)

        assert result
        assert os.path.isfile(definition_filepath)
        assert "FROM datmo/xgboost:cpu" in open(definition_filepath,
                                                "r").read()

        # Test failure with prompt input number out of range
        self.environment_command.parse(["environment", "setup"])

        @self.environment_command.cli_helper.input("-1\n")
        def dummy(self):
            return self.environment_command.execute()

        result = dummy(self)

        assert not result

        # Test failure with prompt input string incorrect
        self.environment_command.parse(["environment", "setup"])

        @self.environment_command.cli_helper.input("random\n")
        def dummy(self):
            return self.environment_command.execute()

        result = dummy(self)

        assert not result

    def test_environment_create(self):
        # 1) Environment definition file in project environment directory (with name / description)
        # 2) Environment definition file passed as an option
        # 3) Environment definition file in root project folder
        # 4) Environment definition file in root project folder (should return the same environment)
        # 5) No environment definition file present
        # 6) No environment definition file present (should return the same environment)
        self.__set_variables()
        # Test option 1
        # Create environment definition in project environment directory
        definition_filepath = os.path.join(self.temp_dir, "datmo_environment",
                                           "Dockerfile")
        random_text = str(uuid.uuid1())
        with open(definition_filepath, "wb") as f:
            f.write(to_bytes("FROM python:3.5-alpine" + "\n"))
            f.write(to_bytes(str("RUN echo " + random_text)))

        self.environment_command.parse([
            "environment", "create", "--name", "test", "--description",
            "test description"
        ])
        result = self.environment_command.execute()

        assert result
        assert result.name == "test"
        assert result.description == "test description"

        # remove datmo_environment directory
        shutil.rmtree(os.path.join(self.temp_dir, "datmo_environment"))

        # Test option 2
        random_dir = os.path.join(self.temp_dir, "random_datmo_dir")
        os.makedirs(random_dir)

        definition_filepath = os.path.join(random_dir, "Dockerfile")
        random_text = str(uuid.uuid1())
        with open(definition_filepath, "wb") as f:
            f.write(to_bytes("FROM python:3.5-alpine" + "\n"))
            f.write(to_bytes(str("RUN echo " + random_text)))

        self.environment_command.parse(
            ["environment", "create", "--paths", definition_filepath])
        result = self.environment_command.execute()
        assert result

        # remove directory with Dockerfile
        shutil.rmtree(random_dir)

        # Test option 3
        definition_filepath = os.path.join(self.temp_dir, "Dockerfile")
        random_text = str(uuid.uuid1())
        with open(definition_filepath, "wb") as f:
            f.write(to_bytes("FROM python:3.5-alpine" + "\n"))
            f.write(to_bytes(str("RUN echo " + random_text)))

        self.environment_command.parse(["environment", "create"])
        result = self.environment_command.execute()
        assert result

        # Test option 4
        self.environment_command.parse(["environment", "create"])
        result_2 = self.environment_command.execute()
        assert result == result_2

        os.remove(definition_filepath)

        # Test option 5
        self.environment_command.parse(["environment", "create"])
        result = self.environment_command.execute()
        assert result

        # Test option 6
        self.environment_command.parse(["environment", "create"])
        result_2 = self.environment_command.execute()
        assert result == result_2

    def test_environment_update(self):
        self.__set_variables()
        self.environment_command.parse(["environment", "create"])
        environment_obj = self.environment_command.execute()

        # Test successful update (none given)
        self.environment_command.parse(
            ["environment", "update", environment_obj.id])
        result = self.environment_command.execute()
        assert result
        assert not result.name
        assert not result.description

        # Test successful update (name and description given)
        new_name = "test name"
        new_description = "test description"
        self.environment_command.parse([
            "environment", "update", environment_obj.id, "--name", new_name,
            "--description", new_description
        ])
        result = self.environment_command.execute()
        assert result
        assert result.name == new_name
        assert result.description == new_description

        # Test failed update (passing up error from controller)
        failed = False
        try:
            self.environment_command.parse(
                ["environment", "update", "random_id"])
            self.environment_command.execute()
        except EnvironmentDoesNotExist:
            failed = True
        assert failed

    @pytest_docker_environment_failed_instantiation(test_datmo_dir)
    def test_environment_delete(self):
        self.__set_variables()
        self.environment_command.parse(["environment", "create"])
        environment_obj = self.environment_command.execute()

        self.environment_command.parse(
            ["environment", "delete", environment_obj.id])
        result = self.environment_command.execute()

        assert result

    def test_environment_ls(self):
        self.__set_variables()
        self.environment_command.parse(["environment", "create"])
        created_environment_obj = self.environment_command.execute()

        # Test success (defaults)
        self.environment_command.parse(["environment", "ls"])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs

        # Test failure (format)
        failed = False
        try:
            self.environment_command.parse(["environment", "ls", "--format"])
        except ArgumentError:
            failed = True
        assert failed

        # Test success format csv
        self.environment_command.parse(
            ["environment", "ls", "--format", "csv"])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs

        # Test success format csv, download default
        self.environment_command.parse(
            ["environment", "ls", "--format", "csv", "--download"])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs
        test_wildcard = os.path.join(
            self.environment_command.environment_controller.home,
            "environment_ls_*")
        paths = [n for n in glob.glob(test_wildcard) if os.path.isfile(n)]
        assert paths
        assert open(paths[0], "r").read()
        os.remove(paths[0])

        # Test success format csv, download exact path
        test_path = os.path.join(self.temp_dir, "my_output")
        self.environment_command.parse([
            "environment", "ls", "--format", "csv", "--download",
            "--download-path", test_path
        ])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs
        assert os.path.isfile(test_path)
        assert open(test_path, "r").read()
        os.remove(test_path)

        # Test success format table
        self.environment_command.parse(["environment", "ls"])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs

        # Test success format table, download default
        self.environment_command.parse(["environment", "ls", "--download"])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs
        test_wildcard = os.path.join(
            self.environment_command.environment_controller.home,
            "environment_ls_*")
        paths = [n for n in glob.glob(test_wildcard) if os.path.isfile(n)]
        assert paths
        assert open(paths[0], "r").read()
        os.remove(paths[0])

        # Test success format table, download exact path
        test_path = os.path.join(self.temp_dir, "my_output")
        self.environment_command.parse(
            ["environment", "ls", "--download", "--download-path", test_path])
        environment_objs = self.environment_command.execute()
        assert created_environment_obj in environment_objs
        assert os.path.isfile(test_path)
        assert open(test_path, "r").read()
        os.remove(test_path)
