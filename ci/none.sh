#!/usr/bin/env bash

function jobqueue_before_install {
  # Install miniconda
  ./ci/conda_setup.sh
  export PATH="$HOME/miniconda/bin:$PATH"
  export LD_LIBRARY_PATH="$HOME/miniconda/lib:$LD_LIBRARY_PATH"
  export CPATH="$HOME/miniconda/include:$CPATH"
  conda install --yes -c conda-forge python=$TRAVIS_PYTHON_VERSION flake8 black pytest pytest-asyncio codespell openmpi
  # also install OpenMPI and mpi4py
  conda install --yes -c conda-forge python=$TRAVIS_PYTHON_VERSION openmpi mpi4py
  # Would use the below to get the latest master of jobqueue
  # pip install git+https://github.com/dask/dask-jobqueue@master --upgrade --no-deps
}

function jobqueue_install {
  which python
  # Make sure requirements are met
  pip install -r requirements.txt
  pip install --no-deps -e .
}

function jobqueue_script {
  # flake8 -j auto jobqueue_features
  echo -e "\e[1mRunning black\e[0m"
  black --exclude versioneer.py --check .
  echo -e "\e[1mSuccess...running codespell\e[0m"
  codespell --quiet-level=2
  echo -e "\e[1mSuccess...running pip list\e[0m"
  pip list
  echo -e "\e[1mRunning pytest...\e[0m"
  OMPI_MCA_rmaps_base_oversubscribe=1 OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 pytest --verbose -s --cov=jobqueue_features
}

function jobqueue_after_script {
  echo "Done."
}