FROM daskdev/dask-jobqueue:slurm

# Some customisation on jobqueue base images
# Remove the previous conda installation and use our own, also installing OpenMPI and mpi4py
RUN rm -r /opt/anaconda
RUN curl -o miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && \
    bash miniconda.sh -f -b -p /opt/anaconda && \
    /opt/anaconda/bin/conda clean -tipy && \
    rm -f miniconda.sh
ENV PATH /opt/anaconda/bin:$PATH
RUN conda install --yes -c conda-forge python=3.8 dask distributed flake8 pytest pytest-asyncio
RUN conda install --yes -c conda-forge openmpi mpi4py
RUN git clone https://github.com/E-CAM/jobqueue_features.git
RUN pip install -r jobqueue_features/requirements.txt
# Add scope to use a LAMMPS example
RUN conda install --yes -c conda-forge lammps
RUN curl -o jobqueue_features/tutorial/docker_config/slurm/tutorial_tasks/in.melt https://raw.githubusercontent.com/lammps/lammps/master/examples/melt/in.melt
COPY slurm.conf /etc/slurm/slurm.conf
COPY jobqueue_features_slurm.yaml /jobqueue_features/jobqueue_features/jobqueue_features.yaml
