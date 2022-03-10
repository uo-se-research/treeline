cd src
tar -xf graphviz-2.47.0.tar.gz
cd graphviz-2.47.0
CXX=/home/git/perffuzz/afl-clang-fast++ CC=/home/git/perffuzz/afl-clang-fast ./configure
make
make install
cd ../../