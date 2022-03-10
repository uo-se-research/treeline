cd src
tar -xvf libxml2-2.9.7.tar.gz
cd libxml2-2.9.7
CC=/home/git/perffuzz/afl-clang-fast ./configure --disable-shared
make
cd ../../
