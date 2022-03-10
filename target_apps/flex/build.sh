cd src
tar -xvf flex-2.6.4.tar.gz
cd flex-2.6.4
apt-get install -y flex
./autogen.sh
CXX=/home/git/perffuzz/afl-clang-fast++ CC=/home/git/perffuzz/afl-clang-fast ./configure
make
apt-get remove -y flex
./src/flex --version
cd ../../