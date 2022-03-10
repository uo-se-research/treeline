cd src
tar -xvf wf-0.41.tar
cd wf-0.41
CC=/home/git/perffuzz/afl-clang-fast ./configure
make
cd ../../
