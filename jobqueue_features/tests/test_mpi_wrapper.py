from __future__ import print_function

import shlex
from unittest import TestCase
import os
import subprocess
import pytest

from distributed import LocalCluster

from jobqueue_features import (
    mpi_wrap,
    MPIEXEC,
    MPICH,
    SRUN,
    OPENMPI,
    SUPPORTED_MPI_LAUNCHERS,
    on_cluster,
    mpi_task,
    which,
    get_task_mpi_comm,
    set_task_mpi_comm,
    serialize_function_and_args,
    deserialize_and_execute,
    mpi_deserialize_and_execute,
    verify_mpi_communicator,
    flush_and_abort,
)

from jobqueue_features.clusters_controller import (
    clusters_controller_singleton as controller,
)

# Use logging if there are hard to see issues in the CI

# import logging
# logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


class TestMPIWrap(TestCase):
    def setUp(self):
        # Kill any existing clusters
        controller._close()

        self.local_cluster = LocalCluster(name="test")
        self.executable = "python"
        self.script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "resources", "helloworld.py")
        )
        self.number_of_processes = 4

        @mpi_task(cluster_id="test")
        def mpi_wrap_task(**kwargs):
            return mpi_wrap(**kwargs)

        @on_cluster(cluster=self.local_cluster, cluster_id="test")
        def test_function(
            script_path,
            mpi_launcher=MPIEXEC,
            launcher_args=None,
            nodes=1,
            ntasks_per_node=4,
            cpus_per_task=1,
            return_wrapped_command=False,
        ):
            mpi_tasks = ntasks_per_node * nodes
            t = mpi_wrap_task(
                executable=self.executable,
                exec_args=script_path,
                mpi_launcher=mpi_launcher,
                launcher_args=launcher_args,
                mpi_tasks=mpi_tasks,
                cpus_per_task=cpus_per_task,
                ntasks_per_node=ntasks_per_node,
                nodes=nodes,
                return_wrapped_command=return_wrapped_command,
            )
            result = t.result()

            return result

        self.test_function = test_function

        def mpi_task1(task_name):
            comm = get_task_mpi_comm()
            size = comm.Get_size()
            # Since it is a return  value it will only get printed by root
            return "Running %d tasks of type %s." % (size, task_name)

        self.mpi_task1 = mpi_task1

        def string_task(string, kwarg_string=None):
            return " ".join([s for s in [string, kwarg_string] if s])

        self.string_task = string_task

    def tearDown(self):
        # Kill any existing clusters
        controller._close()

    def is_mpich(self):
        cmd = "mpicc -v"
        proc = subprocess.Popen(
            shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if b"mpich" in proc.stdout.read().lower():
            return True
        return False

    def test_which(self):
        # Check it finds a full path
        self.assertEqual(which(self.script_path), self.script_path)
        # Check it searches the PATH envvar
        os.environ["PATH"] += os.pathsep + os.path.dirname(self.script_path)
        self.assertEqual(which(os.path.basename(self.script_path)), self.script_path)
        # Check it returns None if the executable doesn't exist
        self.assertIsNone(which("not_an_executable"))
        # Check it returns None when a file is not executable
        self.assertIsNone(which(os.path.realpath(__file__)))

    def test_mpi_wrap_execution(self):
        # Only check the ones that work in CI
        if self.is_mpich():
            # Haven't implemented explicit MPICH support yet
            launchers = [MPICH, MPIEXEC]
        else:
            launchers = [OPENMPI, MPIEXEC]
        for launcher in launchers:
            # Include some (non-standard) OpenMPI options so that we can run this in CI
            launcher_args = "--allow-run-as-root --oversubscribe"
            if self.is_mpich():
                # In PBS we use mpich which doesn't require these
                launcher_args = ""

            if which(launcher["launcher"]) is None:
                print("Didn't find {}, skipping test".format(launcher))
                pass
            else:
                print("Found {} launcher in env, running MPI test".format(launcher))
                result = self.test_function(
                    self.script_path, mpi_launcher=launcher, launcher_args=launcher_args
                )
                for n in range(self.number_of_processes):
                    text = "Hello, World! I am process {} of {}".format(
                        n, self.number_of_processes
                    )
                    self.assertIn(text.encode(), result["out"])

    def test_mpi_wrap(self):
        # Test syntax of wrapped MPI launcher commands
        mpi_launchers = SUPPORTED_MPI_LAUNCHERS
        # specific example of 2 nodes and 3 processes
        expected_launcher_args = [
            "",
            "-n 6",
            "-np 6 --map-by ppr:3:node",
            "-n 6 -perhost 3",
            "-n 6 -ppn 3",
        ]
        # specific example of 2 nodes, 3 processes and 4 OpenMP threads
        hybrid_expected_launcher_args = [
            "",
            "-n 6",
            "-np 6 --map-by ppr:3:node:pe=4",
            "-n 6 -perhost 3 -env I_MPI_PIN_DOMAIN 4",
            "-n 6 -ppn 3 -genv OMP_NUM_THREADS 4 -bind-to core:4",
        ]
        for mpi_launcher, expected_launcher_opts, hybrid_expected_launcher_opts in zip(
            mpi_launchers, expected_launcher_args, hybrid_expected_launcher_args
        ):
            result = self.test_function(
                self.script_path,
                mpi_launcher=mpi_launcher,
                nodes=2,
                ntasks_per_node=3,
                return_wrapped_command=True,
            )
            _cmd = (
                mpi_launcher["launcher"],
                expected_launcher_opts,
                self.executable,
                self.script_path,
            )
            expected_result = " ".join(filter(len, map(str, _cmd)))
            self.assertEqual(result, expected_result)

            # Now check OpenMP threaded versions
            result = self.test_function(
                self.script_path,
                mpi_launcher=mpi_launcher,
                nodes=2,
                ntasks_per_node=3,
                cpus_per_task=4,
                return_wrapped_command=True,
            )
            _cmd = (
                mpi_launcher["launcher"],
                hybrid_expected_launcher_opts,
                self.executable,
                self.script_path,
            )
            expected_result = " ".join(filter(len, map(str, _cmd)))
            self.assertEqual(result, expected_result)

    # Test the MPI wrapper in isolation for srun (which we assume doesn't exist):
    def test_mpi_srun_wrapper(self):
        if which(SRUN["launcher"]) is None:
            print(
                "Didn't find {}, running OSError test for no available launcher".format(
                    SRUN
                )
            )
            with self.assertRaises(OSError) as context:
                mpi_wrap(
                    executable="python",
                    exec_args=self.script_path,
                    mpi_launcher=SRUN,
                    mpi_tasks=self.number_of_processes,
                )
            self.assertTrue(
                "OS error caused by constructed command" in str(context.exception)
            )
        else:
            pass

    # Test our serialisation method
    def test_serialize_function_and_args(self):
        # First check elements in our dict
        serialized_object = serialize_function_and_args(self.string_task)
        for key in serialized_object.keys():
            self.assertIn(key, ["header", "frames"])
        serialized_object = serialize_function_and_args(self.string_task, "chicken")
        for key in serialized_object.keys():
            self.assertIn(key, ["header", "frames", "args_header", "args_frames"])
        serialized_object = serialize_function_and_args(
            self.string_task, kwarg_string="dog"
        )
        for key in serialized_object.keys():
            self.assertIn(key, ["header", "frames", "kwargs_header", "kwargs_frames"])
        serialized_object = serialize_function_and_args(
            self.string_task, "chicken", kwarg_string="dog"
        )
        for key in serialized_object.keys():
            self.assertIn(
                key,
                [
                    "header",
                    "frames",
                    "args_header",
                    "args_frames",
                    "kwargs_header",
                    "kwargs_frames",
                ],
            )

    def test_deserialize_and_execute(self):
        serialized_object = serialize_function_and_args(
            self.string_task, "chicken", kwarg_string="dog"
        )
        self.assertEqual("chicken dog", deserialize_and_execute(serialized_object))

    def test_verify_mpi_communicator_raise(self):
        with self.assertRaises(SystemExit) as cm:
            verify_mpi_communicator("Not a communicator", mpi_abort=False)
        self.assertEqual(cm.exception.code, 1)

    def test_mpi_deserialize_and_execute_raise(self):
        trivial = "trivial"
        serialized_object = serialize_function_and_args(self.mpi_task1, trivial)
        # For the deserializer to work we need to first set the task MPI communicator
        with self.assertRaises(AttributeError):
            mpi_deserialize_and_execute(serialized_object)

    def test_flush_and_abort(self):
        with self.assertRaises(SystemExit) as cm:
            flush_and_abort(mpi_abort=False)
        self.assertEqual(cm.exception.code, 1)
        with self.assertRaises(SystemExit) as cm:
            flush_and_abort(error_code=2, mpi_abort=False)
        self.assertEqual(cm.exception.code, 2)

    # Since this test initialises an MPI environment in the test context, it needs to
    # be run last as it interferes with other tests above
    @pytest.mark.last
    def test_mpi_deserialize_and_execute(self):
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        self.assertTrue(verify_mpi_communicator(comm, mpi_abort=False))
        # The test framework is not started with an MPI launcher so we have
        # a single task
        set_task_mpi_comm(parent_comm=comm)
        trivial = "trivial"
        serialized_object = serialize_function_and_args(self.mpi_task1, trivial)
        expected_string = "Running 1 tasks of type {}.".format(trivial)
        return_value = mpi_deserialize_and_execute(serialized_object)
        self.assertEqual(expected_string, return_value)
