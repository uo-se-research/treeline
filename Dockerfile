FROM debian:9.8

MAINTAINER Ziyad Alsaeed "zalsaeed@cs.uoregon.edu"

# adding the needed sources for the package manager
COPY resources/sources.list /etc/apt/

# all packages needed by all perffuzz glade, or us.
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
	build-essential \
	make \
	cmake \
	git \
	curl \
	rpm2cpio \
	cpio \
	vim \
	wget \
	libssl-dev \
	libssl-dev \
	libbz2-dev \
	libreadline-dev \
	libsqlite3-dev \
	libncurses5-dev \
	libncursesw5-dev \
	libgdbm-dev \
	libc6-dev \
	zlib1g-dev \
	libffi-dev \
	tk-dev \
	ca-certificates \ 
	libjpeg-dev \
	libpng-dev && \
	rm -rf /var/lib/apt/lists/*

# packages needed for flex (one of the benchmarks)
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
    bison \
    texinfo \
    help2man

# installing python3.8.11
WORKDIR /opt
RUN wget https://www.python.org/ftp/python/3.8.11/Python-3.8.11.tgz
# --no-check-certificate
RUN tar xzf Python-3.8.11.tgz
RUN rm Python-3.8.11.tgz
WORKDIR /opt/Python-3.8.11
RUN ./configure --enable-optimizations --enable-shared
RUN make altinstall

# special case for installing clang
RUN apt-get update
RUN apt-get install -y clang-3.8

# building some dependencies needed by perffuzz benchmarks
RUN apt-get update
RUN apt-get build-dep python-lxml -y

# updating the main compilers based on the newly installed clang version
RUN update-alternatives --install /usr/bin/cc cc /usr/bin/clang-3.8 100
RUN update-alternatives --install /usr/bin/c++ c++ /usr/bin/clang++-3.8 100
RUN update-alternatives --install /usr/bin/clang clang /usr/bin/clang-3.8 100
RUN update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-3.8 100

RUN update-alternatives --install /usr/bin/llvm-config llvm-config /usr/bin/llvm-config-3.8 100

# cloning, building, and installing perfffuz and its test subjects.
RUN mkdir /home/git
WORKDIR /home/git/

# cloning PerfFuzz then reset to the known working version of the repo (a commit on Feb 20, 2020)
RUN git clone https://github.com/carolemieux/perffuzz.git
WORKDIR /home/git/perffuzz/
RUN git reset --hard f937f370555d0c54f2109e3b1aa5763f8defe337

# compile origirnal fuzzer
WORKDIR /home/git/perffuzz/
RUN make
# compile instrumentor
WORKDIR /home/git/perffuzz/llvm_mode/
RUN make
# compile analyzer
WORKDIR /home/git/perffuzz/
RUN make afl-showmax

# Use our file before the build, the files we copy are edited versions of PerfFuzz to work with TreeLine
COPY resources/afl-fuzz.c .
COPY resources/afl-showmax.c .
RUN make clean all  # build edited PerfFuzz
RUN make afl-showmax  # build the edited analysis file.
WORKDIR /home/git/perffuzz/llvm_mode/
RUN make

# Copy the source of this repository (and all submodules) to build target_apps and be ready for runs
WORKDIR /home
RUN mkdir treeline
WORKDIR /home/treeline
COPY src ./src

# Install conda and all the other project dependecies in python
RUN curl -o ~/miniconda.sh -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh  && \
	chmod +x ~/miniconda.sh && \
	~/miniconda.sh -b -p /opt/conda && \
	rm ~/miniconda.sh && \
	/opt/conda/bin/conda clean -ya

ENV PATH $PATH:/home/git/perffuzz/:/opt/conda/bin

RUN conda install -c conda-forge matplotlib
RUN pip install --upgrade pip

# install python packages
RUN pip install pandas
RUN pip install sympy
RUN pip install psutil
RUN pip install graphviz
RUN pip install tdigest

# copy the target apps dir and build all the apps with AFL instrumenter
COPY target_apps ./target_apps

# build all target apps
WORKDIR /home/treeline/target_apps
RUN sh build_targets.sh

# make a result root diroctry (TODO: what is the for?)
RUN mkdir /home/results

# change the workdir to /home for convenience
WORKDIR /home

# ports we are exposing (6006: tensorboard, 2300: AFL socket)
# this is requiered only in case one would like to run TreeLine from a local machine while PerfFuzz (AFL) is running
# on this docker container.
EXPOSE 6006 2300
