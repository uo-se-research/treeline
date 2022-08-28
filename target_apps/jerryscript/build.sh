cd src
tar -xvf jerryscript-2.4.0-modified.tar.gz
cd jerryscript-2.4.0
CC=/home/git/perffuzz/afl-clang-fast python tools/build.py --clean --jerry-cmdline=on --jerry-cmdline-snapshot=on --lto=off
cd ../../
